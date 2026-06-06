"""Standalone Demo 1 runner — calls run_agent() directly, no REPL."""
import asyncio
import sys

from itakt.config import load_config
from itakt.provider import AnthropicProvider
from itakt.monitor import TokenMonitor
from itakt.safety import SafetyLayer
from itakt.tools import ToolRegistry
from itakt.agent import run_agent


async def main() -> None:
    config = load_config()
    provider = AnthropicProvider(api_key=config.anthropic_api_key)
    monitor = TokenMonitor(budget=config.budget)
    registry = ToolRegistry(max_tool_result_tokens=config.context.max_tool_result_tokens)
    safety = SafetyLayer(
        safety_cfg=config.safety,
        registry=registry,
        audit_log_path="./itakt_audit.log",
    )

    task = "Read the README.md and tell me what this project does"
    print(f"[Demo 1] Task: {task!r}")
    print()

    result = await run_agent(
        task=task,
        config=config,
        provider=provider,
        monitor=monitor,
        safety=safety,
    )
    print(result)
    print()
    print(monitor.status_line())


if __name__ == "__main__":
    asyncio.run(main())
