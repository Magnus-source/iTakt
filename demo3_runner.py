"""Demo 3 — Token Dashboard & Budget Cap.

Sets hard_cap_tokens=1000 so the first API call (which uses ~2000+ tokens)
immediately hits the cap and the session stops with a budget summary.
"""
import asyncio

from itakt.config import load_config, BudgetConfig
from itakt.dashboard import render_dashboard
from itakt.monitor import TokenMonitor
from itakt.orchestrator import run_orchestrator
from itakt.provider import AnthropicProvider
from itakt.safety import SafetyLayer, SafetyConfig
from itakt.tools import ToolRegistry


async def main() -> None:
    config = load_config()

    # Override budget to a very low cap to demonstrate hard stop
    low_budget = BudgetConfig(
        hard_cap_tokens=1000,
        hard_cap_usd=99.00,
        warning_thresholds=[0.70, 0.90],
        pricing=config.budget.pricing,
    )
    config.budget = low_budget

    provider = AnthropicProvider(api_key=config.anthropic_api_key)
    monitor = TokenMonitor(budget=low_budget)
    registry = ToolRegistry(max_tool_result_tokens=config.context.max_tool_result_tokens)
    safety = SafetyLayer(
        safety_cfg=SafetyConfig(auto_approve_writes=True),
        registry=registry,
        audit_log_path="./itakt_audit.log",
    )

    print("=" * 60)
    print("Demo 3: Token Dashboard & Budget Cap")
    print(f"  hard_cap_tokens = {low_budget.hard_cap_tokens:,}")
    print("=" * 60)
    print()

    task = "Refactor the entire codebase to use best practices."

    print(f"Task: {task!r}")
    print()

    result = await run_orchestrator(
        task=task,
        config=config,
        provider=provider,
        monitor=monitor,
        safety=safety,
    )

    print()
    print(result)
    print()
    print("Dashboard at session end:")
    render_dashboard(monitor)


if __name__ == "__main__":
    asyncio.run(main())
