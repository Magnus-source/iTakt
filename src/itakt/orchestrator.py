"""Orchestrator — multi-agent decision loop with parallel sub-agent spawning."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from .agent import _content_to_dicts
from .config import Config
from .monitor import TokenMonitor
from .provider import AnthropicProvider
from .safety import SafetyLayer
from .subagent import run_sub_agent
from .tools import TOOL_SCHEMAS, YIELD_TO_USER_SCHEMA

# ---------------------------------------------------------------------------
# spawn_sub_agent tool schema (orchestrator-only)
# ---------------------------------------------------------------------------

SPAWN_SUB_AGENT_SCHEMA: dict = {
    "name": "spawn_sub_agent",
    "description": (
        "Spawn a focused sub-agent to work on a specific sub-task. "
        "For complex tasks that need both code changes AND tests, call spawn_sub_agent "
        "multiple times in a SINGLE response — they run in parallel. "
        "Simple tasks (single file read, quick question, one small change) can be "
        "handled directly with the standard tools instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": ["planner", "coder", "reviewer", "tester"],
                "description": "Specialization of the sub-agent.",
            },
            "task": {
                "type": "string",
                "description": "Focused, self-contained task description for this sub-agent.",
            },
            "context": {
                "type": "string",
                "description": (
                    "Relevant context the sub-agent needs: file contents, "
                    "requirements, existing code snippets."
                ),
            },
        },
        "required": ["role", "task"],
    },
}

ORCHESTRATOR_SYSTEM = """\
You are iTakt, an AI orchestrator that manages a team of specialised sub-agents \
for software engineering tasks.

ROUTING RULES:
- SIMPLE task (read a file, answer a question, one small change) → handle directly \
with your standard tools (read_file, list_directory, write_file, edit_file, bash).
- COMPLEX task (code changes + tests, multiple files, multi-step refactor) → \
decompose and delegate. Call spawn_sub_agent multiple times in a SINGLE response \
so the agents run IN PARALLEL. Never spawn sequentially when parallel is possible.

Sub-agent roles: planner (analyse/plan), coder (write/edit code), \
reviewer (review changes), tester (write/run tests).

After all sub-agents complete, synthesise their results, run any needed verification \
(e.g. pytest), then call yield_to_user with a clear summary.
Always call yield_to_user when done."""

ORCHESTRATOR_TOOLS = TOOL_SCHEMAS + [SPAWN_SUB_AGENT_SCHEMA, YIELD_TO_USER_SCHEMA]


# ---------------------------------------------------------------------------
# Orchestrator loop
# ---------------------------------------------------------------------------

async def run_orchestrator(
    task: str,
    config: Config,
    provider: AnthropicProvider,
    monitor: TokenMonitor,
    safety: SafetyLayer,
) -> str:
    """Orchestrator loop: handles spawn_sub_agent calls in parallel batches."""
    messages: list[dict] = [{"role": "user", "content": task}]
    model_cfg = config.models.orchestrator
    agent_name = "orchestrator"
    semaphore = asyncio.Semaphore(config.agents.max_parallel)
    role_counters: dict[str, int] = defaultdict(int)
    t0 = time.monotonic()

    print(f"[agent] orchestrator ({model_cfg.model}) started")

    for iteration in range(config.agents.max_iterations):
        if monitor.is_over_budget():
            return f"[iTakt] Budget cap reached.\n{monitor.status_line()}"

        response = await provider.complete(
            system=ORCHESTRATOR_SYSTEM,
            messages=messages,
            tools=ORCHESTRATOR_TOOLS,
            model_cfg=model_cfg,
        )

        monitor.record(
            agent_name=agent_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider=model_cfg.provider,
            model=model_cfg.model,
        )

        messages.append({"role": "assistant", "content": _content_to_dicts(response.content)})

        # No more tool calls — extract text response
        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    return block.text
            return "(orchestrator finished with no text)"

        # Scan for yield_to_user (always handled first)
        for block in response.content:
            if block.type == "tool_use" and block.name == "yield_to_user":
                return block.input.get("message", "(no message)")

        # Partition all tool calls
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        spawn_calls = [tc for tc in tool_calls if tc.name == "spawn_sub_agent"]
        regular_calls = [tc for tc in tool_calls if tc.name != "spawn_sub_agent"]

        # Collect results keyed by tool_use_id (preserve order later)
        results: dict[str, str] = {}

        # Regular tools: sequential sync execution
        for tc in regular_calls:
            results[tc.id] = safety.execute(tc.name, tc.input, agent_name)

        # spawn_sub_agent: parallel async execution
        if spawn_calls:
            async def _spawn_one(tc: object) -> tuple[str, str]:
                role: str = tc.input["role"]
                role_counters[role] += 1
                sub_name = f"{role}-{role_counters[role]}"
                async with semaphore:
                    summary = await run_sub_agent(
                        role=role,
                        task=tc.input["task"],
                        context=tc.input.get("context", ""),
                        config=config,
                        provider=provider,
                        monitor=monitor,
                        safety=safety,
                        agent_name=sub_name,
                        t0=t0,
                    )
                return tc.id, summary

            gathered = await asyncio.gather(*[_spawn_one(tc) for tc in spawn_calls])
            for tool_id, summary in gathered:
                results[tool_id] = summary

            n = len(spawn_calls)
            print(
                f"[agent] {n} sub-agent{'s' if n > 1 else ''} ran in parallel"
                + (" (overlap confirmed)" if n > 1 else "")
            )

        # Build ordered tool results for the next LLM turn
        ordered: list[dict] = [
            {"type": "tool_result", "tool_use_id": tc.id, "content": results[tc.id]}
            for tc in tool_calls
            if tc.id in results
        ]
        messages.append({"role": "user", "content": ordered})

    return "[iTakt] Max iterations reached."
