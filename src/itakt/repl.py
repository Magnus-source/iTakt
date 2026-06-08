"""Minimal terminal REPL — prompt-toolkit input, runs the agent loop."""
from __future__ import annotations

import asyncio
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from .compaction import compact_messages, estimate_tokens
from .config import load_config
from .dashboard import render_dashboard
from .monitor import TokenMonitor
from .orchestrator import ConversationAgent, ORCHESTRATOR_SYSTEM
from .provider import AnthropicProvider
from .safety import SafetyLayer
from .tools import ToolRegistry


BANNER = """\
╔══════════════════════════════════════╗
║  iTakt — AI coding agent  v0.1.0    ║
║  Type a task, or:                   ║
║    /compact  force context compact  ║
║    exit      quit                   ║
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

    # Single agent instance that persists across the whole REPL session.
    # Its .messages list accumulates every turn so the agent remembers context.
    agent = ConversationAgent(config, provider, monitor, safety)

    print(BANNER)
    print()

    session: PromptSession = PromptSession(history=InMemoryHistory())

    while True:
        try:
            raw = (await session.prompt_async("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[iTakt] Goodbye.")
            break

        if not raw:
            continue
        if raw.lower() in ("exit", "quit", "q"):
            print("[iTakt] Goodbye.")
            break

        # /compact command — compact the live conversation history
        if raw.lower() == "/compact":
            if not agent.messages:
                print("[context] No session history to compact yet.")
                continue
            before = estimate_tokens(agent.messages)
            print(f"[context] Forcing compaction of session history ({before:,} est. tokens)…")
            agent.messages = await compact_messages(
                messages=agent.messages,
                system=ORCHESTRATOR_SYSTEM,
                context_cfg=config.context,
                provider=provider,
                model_cfg=config.models.compaction,
                agent_name="repl-session",
                traces_dir="traces",
            )
            after = estimate_tokens(agent.messages)
            print(f"[context] History: {before:,} → {after:,} tokens")
            print(f"  {monitor.status_line()}")
            continue

        print()
        result = await agent.run_turn(raw)
        print()
        print(result)
        print()

        render_dashboard(monitor)
        print()
