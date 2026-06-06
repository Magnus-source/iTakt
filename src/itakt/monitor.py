"""Token Monitor — records usage per agent, exposes session totals and status line."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import BudgetConfig, PricingEntry


@dataclass
class AgentUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


class TokenMonitor:
    def __init__(self, budget: BudgetConfig) -> None:
        self._budget = budget
        self._agents: dict[str, AgentUsage] = {}
        self._total_input: int = 0
        self._total_output: int = 0
        self._total_cost: float = 0.0
        self._steps: int = 0
        self._warned_thresholds: set[float] = set()

    def record(
        self,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
        provider: str,
        model: str,
    ) -> None:
        cost = self._calc_cost(input_tokens, output_tokens, provider, model)

        if agent_name not in self._agents:
            self._agents[agent_name] = AgentUsage()
        ag = self._agents[agent_name]
        ag.input_tokens += input_tokens
        ag.output_tokens += output_tokens
        ag.cost_usd += cost
        ag.calls += 1

        self._total_input += input_tokens
        self._total_output += output_tokens
        self._total_cost += cost
        self._steps += 1

    def _calc_cost(
        self, input_tokens: int, output_tokens: int, provider: str, model: str
    ) -> float:
        try:
            entry: PricingEntry = self._budget.pricing[provider][model]
            return (input_tokens / 1_000_000) * entry.input + (
                output_tokens / 1_000_000
            ) * entry.output
        except KeyError:
            return 0.0

    def total_tokens(self) -> int:
        return self._total_input + self._total_output

    def total_cost(self) -> float:
        return self._total_cost

    def is_over_budget(self) -> bool:
        if self.total_tokens() >= self._budget.hard_cap_tokens:
            return True
        if self._total_cost >= self._budget.hard_cap_usd:
            return True
        return False

    def budget_fraction(self) -> float:
        tok_frac = self.total_tokens() / max(self._budget.hard_cap_tokens, 1)
        usd_frac = self._total_cost / max(self._budget.hard_cap_usd, 0.001)
        return max(tok_frac, usd_frac)

    def agents_usage(self) -> dict[str, AgentUsage]:
        return dict(self._agents)

    def check_thresholds(self) -> Optional[str]:
        """Return newly-crossed threshold level ('70' or '90') or None."""
        frac = self.budget_fraction()
        for threshold in sorted(self._budget.warning_thresholds):
            if frac >= threshold and threshold not in self._warned_thresholds:
                self._warned_thresholds.add(threshold)
                return str(int(threshold * 100))
        return None

    def status_line(self) -> str:
        pct = self.budget_fraction() * 100
        return (
            f"ctx {self.total_tokens():,} tok"
            f" | ${self._total_cost:.4f}"
            f" | steps {self._steps}"
            f" | budget {pct:.1f}%"
        )
