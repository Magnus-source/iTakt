"""Rich token dashboard — renders a live cost panel and handles budget warnings.

Spec (FEATURES.md F4):
  - Session tokens + cost, budget bar with %, per-agent breakdown.
  - 70% → yellow warning; 90% → red warning.
  - Hard cap → stops session with budget summary.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .monitor import TokenMonitor

console = Console()


# ---------------------------------------------------------------------------
# Dashboard panel
# ---------------------------------------------------------------------------

def render_dashboard(monitor: TokenMonitor) -> None:
    """Print a Rich token-usage panel to the terminal."""
    total_tok = monitor.total_tokens()
    total_usd = monitor.total_cost()
    budget = monitor._budget
    pct = monitor.budget_fraction() * 100

    cap_tok = budget.hard_cap_tokens
    cap_usd = budget.hard_cap_usd

    # Budget bar (20 chars wide)
    filled = min(20, int(pct / 5))
    bar_filled = "█" * filled
    bar_empty = "░" * (20 - filled)
    if pct >= 90:
        bar_color = "red"
    elif pct >= 70:
        bar_color = "yellow"
    else:
        bar_color = "green"

    # Per-agent table
    agents = monitor.agents_usage()

    grid = Table.grid(padding=(0, 1))
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_column(justify="right")

    grid.add_row(
        Text("Session:", style="bold"),
        Text(f"{total_tok:,} tok", style="cyan"),
        Text(f"${total_usd:.4f}", style="cyan"),
    )
    grid.add_row(
        Text("Budget:", style="bold"),
        Text(f"{cap_tok:,} tok", style="dim"),
        Text(f"${cap_usd:.2f}", style="dim"),
    )
    grid.add_row(
        Text(f"[{bar_color}]{bar_filled}{bar_empty}[/{bar_color}]  {pct:.1f}%"),
        Text(""),
        Text(""),
    )

    if agents:
        grid.add_row(Text(""), Text(""), Text(""))
        grid.add_row(
            Text("Active Agents:", style="bold"),
            Text("tokens", style="dim"),
            Text("cost", style="dim"),
        )
        for name, usage in agents.items():
            tok = usage.input_tokens + usage.output_tokens
            grid.add_row(
                Text(f"  ● {name}"),
                Text(f"{tok:,}"),
                Text(f"${usage.cost_usd:.4f}"),
            )

    console.print(Panel(grid, title="Token Usage", border_style="blue"))


# ---------------------------------------------------------------------------
# Budget warnings
# ---------------------------------------------------------------------------

def print_budget_warning(level: str) -> None:
    """Print a 70% or 90% warning banner."""
    if level == "90":
        console.print(
            Panel(
                "[bold red]⚠  Budget at 90% — agents should wrap up now.[/bold red]",
                border_style="red",
            )
        )
    elif level == "70":
        console.print(
            Panel(
                "[bold yellow]⚠  Budget at 70%.[/bold yellow]",
                border_style="yellow",
            )
        )


def budget_summary(monitor: TokenMonitor) -> str:
    """Return a plain-text budget-cap summary (printed when hard cap is hit)."""
    lines = [
        "╔══════════════════════════════════════╗",
        "║   iTakt — Budget Cap Reached         ║",
        "╚══════════════════════════════════════╝",
        "",
        monitor.status_line(),
        "",
        "Per-agent breakdown:",
    ]
    for name, usage in monitor.agents_usage().items():
        tok = usage.input_tokens + usage.output_tokens
        lines.append(f"  {name:20s}  {tok:>8,} tok  ${usage.cost_usd:.4f}")
    lines.append("")
    lines.append("Session stopped. Start a new session to continue.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Warning check helper (called from orchestrator/agent loops)
# ---------------------------------------------------------------------------

def check_and_print_warnings(monitor: TokenMonitor) -> bool:
    """Check for newly-crossed thresholds and print warnings. Returns True if over budget."""
    level = monitor.check_thresholds()
    if level:
        print_budget_warning(level)
    return monitor.is_over_budget()
