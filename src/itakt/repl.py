"""Minimal terminal REPL — prompt-toolkit input, runs the agent loop."""
from __future__ import annotations

import asyncio
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from .agent import run_agent
from .config import load_config
from .monitor import TokenMonitor
from .provider import AnthropicProvider
from .safety import SafetyLayer
from .tools import ToolRegistry


BANNER = """\
╔══════════════════════════════════════╗
║  iTakt — AI coding agent  v0.1.0    ║
║  Type your task, or 'exit' to quit. ║
╚══════════════════════════════════════╝"""


async def run_repl() -> None:
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"[iTakt] Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    provider = AnthropicProvider(api_key=config.anthropic_api_key)
    monitor = TokenMonitor(budget=config.budget)
    registry = ToolRegistry(max_tool_result_tokens=config.context.max_tool_result_tokens)
    safety = SafetyLayer(
        safety_cfg=config.safety,
        registry=registry,
        audit_log_path=config.logging.file.replace(".log", "_audit.log"),
    )

    print(BANNER)
    print()

    session: PromptSession = PromptSession(history=InMemoryHistory())

    while True:
        try:
            task = (await session.prompt_async("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[iTakt] Goodbye.")
            break

        if not task:
            continue
        if task.lower() in ("exit", "quit", "q"):
            print("[iTakt] Goodbye.")
            break

        print()
        result = await run_agent(
            task=task,
            config=config,
            provider=provider,
            monitor=monitor,
            safety=safety,
        )
        print()
        print(result)
        print()
        print(f"  {monitor.status_line()}")
        print()
