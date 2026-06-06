"""Tests for the token dashboard and budget warning logic."""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from itakt.config import BudgetConfig, PricingEntry
from itakt.dashboard import (
    budget_summary,
    check_and_print_warnings,
    print_budget_warning,
    render_dashboard,
)
from itakt.monitor import TokenMonitor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_monitor(
    hard_cap_tokens: int = 10_000,
    hard_cap_usd: float = 1.00,
    thresholds: list[float] | None = None,
) -> TokenMonitor:
    pricing: dict = {
        "anthropic": {
            "claude-sonnet-4-6": PricingEntry(input=3.00, output=15.00),
            "claude-haiku-4-5-20251001": PricingEntry(input=0.80, output=4.00),
        }
    }
    budget = BudgetConfig(
        hard_cap_tokens=hard_cap_tokens,
        hard_cap_usd=hard_cap_usd,
        warning_thresholds=thresholds or [0.70, 0.90],
        pricing=pricing,
    )
    return TokenMonitor(budget=budget)


# ---------------------------------------------------------------------------
# render_dashboard — smoke tests (just check it doesn't crash and has content)
# ---------------------------------------------------------------------------

def test_render_dashboard_no_crash():
    monitor = make_monitor()
    # Should not raise
    render_dashboard(monitor)


def test_render_dashboard_with_agents(capsys):
    monitor = make_monitor()
    monitor.record("orchestrator", 1000, 200, "anthropic", "claude-sonnet-4-6")
    monitor.record("coder-1", 500, 100, "anthropic", "claude-haiku-4-5-20251001")
    render_dashboard(monitor)
    captured = capsys.readouterr()
    assert "1,200" in captured.out or "orchestrator" in captured.out


def test_render_dashboard_shows_budget_pct(capsys):
    monitor = make_monitor(hard_cap_tokens=1000)
    monitor.record("orchestrator", 500, 0, "anthropic", "claude-sonnet-4-6")
    render_dashboard(monitor)
    captured = capsys.readouterr()
    # 500/1000 = 50%
    assert "50.0" in captured.out or "50" in captured.out


# ---------------------------------------------------------------------------
# budget_summary
# ---------------------------------------------------------------------------

def test_budget_summary_contains_status_line():
    monitor = make_monitor()
    monitor.record("orchestrator", 100, 50, "anthropic", "claude-sonnet-4-6")
    summary = budget_summary(monitor)
    assert "Budget Cap" in summary or "budget" in summary.lower()
    assert "orchestrator" in summary


def test_budget_summary_contains_all_agents():
    monitor = make_monitor()
    monitor.record("orchestrator", 100, 50, "anthropic", "claude-sonnet-4-6")
    monitor.record("coder-1", 200, 80, "anthropic", "claude-haiku-4-5-20251001")
    summary = budget_summary(monitor)
    assert "orchestrator" in summary
    assert "coder-1" in summary


# ---------------------------------------------------------------------------
# Budget threshold warnings
# ---------------------------------------------------------------------------

def test_check_thresholds_none_below_70(capsys):
    monitor = make_monitor(hard_cap_tokens=10_000)
    monitor.record("orchestrator", 100, 50, "anthropic", "claude-sonnet-4-6")
    # 150/10000 = 1.5%, well below 70%
    result = monitor.check_thresholds()
    assert result is None


def test_check_thresholds_warns_at_70():
    monitor = make_monitor(hard_cap_tokens=1000, thresholds=[0.70, 0.90])
    monitor.record("orchestrator", 700, 0, "anthropic", "claude-sonnet-4-6")
    result = monitor.check_thresholds()
    assert result == "70"


def test_check_thresholds_warns_at_90():
    monitor = make_monitor(hard_cap_tokens=1000, thresholds=[0.70, 0.90])
    monitor.record("orchestrator", 900, 0, "anthropic", "claude-sonnet-4-6")
    # 90% usage crosses both 70% and 90%; sorted order: 70 fires first
    first = monitor.check_thresholds()
    second = monitor.check_thresholds()
    assert first == "70"
    assert second == "90"


def test_check_thresholds_not_repeated():
    """Each threshold fires at most once per session."""
    monitor = make_monitor(hard_cap_tokens=1000, thresholds=[0.70, 0.90])
    monitor.record("orchestrator", 750, 0, "anthropic", "claude-sonnet-4-6")
    first = monitor.check_thresholds()
    second = monitor.check_thresholds()
    assert first == "70"
    assert second is None  # already warned


def test_check_thresholds_70_before_90():
    """70% must fire before 90% even if usage jumps past both."""
    monitor = make_monitor(hard_cap_tokens=1000, thresholds=[0.70, 0.90])
    monitor.record("orchestrator", 950, 0, "anthropic", "claude-sonnet-4-6")
    first = monitor.check_thresholds()
    second = monitor.check_thresholds()
    # 70% fires first (sorted order), then 90%
    assert first == "70"
    assert second == "90"


def test_is_over_budget_token_cap():
    monitor = make_monitor(hard_cap_tokens=100, hard_cap_usd=99.99)
    monitor.record("orchestrator", 101, 0, "anthropic", "claude-sonnet-4-6")
    assert monitor.is_over_budget() is True


def test_is_over_budget_usd_cap():
    monitor = make_monitor(hard_cap_tokens=9_999_999, hard_cap_usd=0.001)
    monitor.record("orchestrator", 1000, 0, "anthropic", "claude-sonnet-4-6")
    # cost = 1000/1M * 3.00 = 0.003, > 0.001 → over budget
    assert monitor.is_over_budget() is True


def test_check_and_print_warnings_over_budget():
    monitor = make_monitor(hard_cap_tokens=100)
    monitor.record("orchestrator", 200, 0, "anthropic", "claude-sonnet-4-6")
    assert check_and_print_warnings(monitor) is True
