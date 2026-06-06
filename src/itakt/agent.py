"""Single-agent decision loop."""
from __future__ import annotations

from typing import AsyncIterator

from .config import Config
from .monitor import TokenMonitor
from .provider import AnthropicProvider
from .safety import SafetyLayer
from .tools import TOOL_SCHEMAS, YIELD_TO_USER_SCHEMA

SYSTEM_PROMPT = """\
You are iTakt, a terminal-based AI coding agent. You help users with software \
engineering tasks by reading files, editing code, running commands, and \
synthesising results.

You have tools available: read_file, list_directory, write_file, edit_file, \
bash, and yield_to_user.

Work autonomously to complete the user's task. When you have finished or need \
user input, always call yield_to_user with your response. Do not stop without \
calling yield_to_user."""

ALL_TOOLS = TOOL_SCHEMAS + [YIELD_TO_USER_SCHEMA]


def _content_to_dicts(content: list) -> list[dict]:
    """Convert SDK content blocks to plain dicts for the message history."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return result


async def run_agent(
    task: str,
    config: Config,
    provider: AnthropicProvider,
    monitor: TokenMonitor,
    safety: SafetyLayer,
) -> str:
    """Run the single-agent loop. Returns the final message to the user."""
    messages: list[dict] = [{"role": "user", "content": task}]
    model_cfg = config.models.orchestrator
    agent_name = "orchestrator"

    for iteration in range(config.agents.max_iterations):
        if monitor.is_over_budget():
            return (
                f"[iTakt] Budget cap reached — session stopped.\n"
                f"{monitor.status_line()}"
            )

        response = await provider.complete(
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=ALL_TOOLS,
            model_cfg=model_cfg,
        )

        monitor.record(
            agent_name=agent_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider=model_cfg.provider,
            model=model_cfg.model,
        )

        # Append assistant turn (as plain dicts so message list stays serialisable)
        assistant_content = _content_to_dicts(response.content)
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "tool_use":
            tool_results: list[dict] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                # yield_to_user is a meta-tool handled here, not by the registry
                if block.name == "yield_to_user":
                    return block.input.get("message", "(no message)")

                tool_result = safety.execute(block.name, block.input, agent_name)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        else:
            # end_turn or max_tokens — extract text
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    return block.text
            return "(agent finished with no text response)"

    return f"[iTakt] Max iterations ({config.agents.max_iterations}) reached."
