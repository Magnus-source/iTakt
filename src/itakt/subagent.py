"""Sub-agent runner — focused single-agent loop with role-specific prompts."""
from __future__ import annotations

import time

from .agent import _content_to_dicts
from .compaction import compact_messages, should_compact
from .config import Config
from .monitor import TokenMonitor
from .provider import AnthropicProvider
from .safety import SafetyLayer
from .tools import TOOL_SCHEMAS, YIELD_TO_USER_SCHEMA

# ---------------------------------------------------------------------------
# Role-specific system prompts
# ---------------------------------------------------------------------------

ROLE_PROMPTS: dict[str, str] = {
    "planner": (
        "You are an expert software planner sub-agent. Your job is to analyse a codebase "
        "and produce a clear, actionable implementation plan.\n"
        "Use read_file and list_directory to understand the code. "
        "When you have a complete plan, call yield_to_user with your analysis and plan."
    ),
    "coder": (
        "You are an expert software coder sub-agent. Your job is to implement the requested "
        "code changes precisely and correctly.\n"
        "Use read_file to understand existing code before editing. "
        "Use edit_file for surgical changes to existing files, write_file for new files. "
        "When your changes are complete, call yield_to_user with a summary of exactly what you changed."
    ),
    "reviewer": (
        "You are an expert code reviewer sub-agent. Your job is to review code changes for "
        "correctness, quality, and potential issues.\n"
        "Use read_file to examine the code. "
        "When done, call yield_to_user with your review findings, listing any issues found."
    ),
    "tester": (
        "You are an expert software tester sub-agent. Your job is to write thorough, correct tests.\n"
        "Use read_file to understand the code being tested before writing tests. "
        "Use write_file to create test files. "
        "When done, call yield_to_user with a summary of the tests you wrote."
    ),
}

SUB_AGENT_TOOLS = TOOL_SCHEMAS + [YIELD_TO_USER_SCHEMA]


# ---------------------------------------------------------------------------
# Result compression
# ---------------------------------------------------------------------------

def compress_result(
    role: str,
    agent_name: str,
    task: str,
    result: str,
    input_tokens: int,
    output_tokens: int,
    model: str,
    status: str = "success",
) -> str:
    """Format sub-agent output as the compressed summary returned to orchestrator."""
    total = input_tokens + output_tokens
    return (
        f"Sub-Agent: {agent_name} ({role}) | Model: {model} | "
        f"Status: {status} | Tokens: {total}\n"
        f"Task: {task}\n"
        f"Result: {result}"
    )


# ---------------------------------------------------------------------------
# Sub-agent loop
# ---------------------------------------------------------------------------

async def run_sub_agent(
    role: str,
    task: str,
    context: str,
    config: Config,
    provider: AnthropicProvider,
    monitor: TokenMonitor,
    safety: SafetyLayer,
    agent_name: str,
    t0: float,
) -> str:
    """Run a focused sub-agent and return a compressed summary for the orchestrator."""
    model_cfg = config.models.sub_agents

    elapsed = time.monotonic() - t0
    print(f"[agent] spawn {agent_name} ({model_cfg.model}) t+{elapsed:.1f}s")

    system = ROLE_PROMPTS.get(role, ROLE_PROMPTS["coder"])

    # Build initial message — prepend context if provided
    if context:
        initial = f"Context:\n{context}\n\nTask:\n{task}"
    else:
        initial = task

    messages: list[dict] = [{"role": "user", "content": initial}]

    agent_input = 0
    agent_output = 0
    final_message = "(sub-agent produced no output)"
    status = "success"
    last_compacted_at: int = -2

    for iteration in range(config.agents.max_iterations):
        if monitor.is_over_budget():
            final_message = "[stopped: budget cap reached]"
            status = "budget_cap"
            break

        # Auto-compact when sub-agent history gets long;
        # never re-compact the iteration immediately after a compaction.
        if (iteration > 0
                and iteration != last_compacted_at + 1
                and should_compact(messages, config.context)):
            messages = await compact_messages(
                messages=messages,
                system=system,
                context_cfg=config.context,
                provider=provider,
                model_cfg=config.models.compaction,
                agent_name=agent_name,
                traces_dir="traces",
            )
            last_compacted_at = iteration

        response = await provider.complete(
            system=system,
            messages=messages,
            tools=SUB_AGENT_TOOLS,
            model_cfg=model_cfg,
        )

        monitor.record(
            agent_name=agent_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider=model_cfg.provider,
            model=model_cfg.model,
        )
        agent_input += response.usage.input_tokens
        agent_output += response.usage.output_tokens

        messages.append({"role": "assistant", "content": _content_to_dicts(response.content)})

        if response.stop_reason == "tool_use":
            tool_results: list[dict] = []
            done = False

            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name == "yield_to_user":
                    final_message = block.input.get("message", "(no message)")
                    done = True
                    break
                result = safety.execute(block.name, block.input, agent_name)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )

            if done:
                break
            messages.append({"role": "user", "content": tool_results})

        else:
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    final_message = block.text
                    break
            break

    elapsed = time.monotonic() - t0
    print(
        f"[agent] return {agent_name}"
        f" tokens={agent_input + agent_output}"
        f" usd=${(agent_input + agent_output) / 1_000_000 * 0.80:.4f}"  # haiku estimate
        f" t+{elapsed:.1f}s"
    )

    return compress_result(
        role=role,
        agent_name=agent_name,
        task=task,
        result=final_message,
        input_tokens=agent_input,
        output_tokens=agent_output,
        model=model_cfg.model,
        status=status,
    )
