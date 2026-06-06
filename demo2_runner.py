"""Demo 2 runner — calls run_orchestrator() directly (no REPL/TTY needed).

Uses auto_approve_writes=True so file edits/writes are approved automatically,
matching the Demo 2 flow: coder edits app.py, tester writes test_health.py,
orchestrator verifies with pytest.
"""
import asyncio

from itakt.config import load_config, SafetyConfig
from itakt.orchestrator import run_orchestrator
from itakt.monitor import TokenMonitor
from itakt.provider import AnthropicProvider
from itakt.safety import SafetyLayer
from itakt.tools import ToolRegistry


DEMO2_TASK = (
    "Add a /health endpoint to demo/app.py that returns JSON "
    "{\"status\": \"ok\", \"timestamp\": <current UTC time as ISO string>}, "
    "and write a pytest test for it in demo/test_health.py. "
    "Use a coder sub-agent to add the endpoint and a tester sub-agent to write the test "
    "— spawn both in parallel. After they finish, run the tests to verify everything works."
)


async def main() -> None:
    config = load_config()

    # Auto-approve writes so the demo runs non-interactively
    auto_cfg = SafetyConfig(
        block_sudo=config.safety.block_sudo,
        auto_approve_writes=True,
        max_write_size=config.safety.max_write_size,
        allowlist=config.safety.allowlist,
        blocklist=config.safety.blocklist,
    )

    provider = AnthropicProvider(api_key=config.anthropic_api_key)
    monitor = TokenMonitor(budget=config.budget)
    registry = ToolRegistry(max_tool_result_tokens=config.context.max_tool_result_tokens)
    safety = SafetyLayer(
        safety_cfg=auto_cfg,
        registry=registry,
        audit_log_path="./itakt_audit.log",
    )

    print("=" * 60)
    print("Demo 2: Multi-Agent Orchestration")
    print("=" * 60)
    print(f"Task: {DEMO2_TASK}")
    print("=" * 60)
    print()

    result = await run_orchestrator(
        task=DEMO2_TASK,
        config=config,
        provider=provider,
        monitor=monitor,
        safety=safety,
    )

    print()
    print("=" * 60)
    print("Orchestrator response:")
    print("=" * 60)
    print(result)
    print()
    print(monitor.status_line())


if __name__ == "__main__":
    asyncio.run(main())
