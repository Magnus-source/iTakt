"""Config Manager — loads itakt.yaml + .env, validates with pydantic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ModelConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3


class ModelsConfig(BaseModel):
    orchestrator: ModelConfig = Field(default_factory=ModelConfig)
    sub_agents: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            model="claude-haiku-4-20250414", max_tokens=2048, temperature=0.2
        )
    )
    compaction: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            model="claude-haiku-4-20250414", max_tokens=1024, temperature=0.1
        )
    )


class PricingEntry(BaseModel):
    input: float = 3.00   # $ per million input tokens
    output: float = 15.00  # $ per million output tokens


class BudgetConfig(BaseModel):
    hard_cap_tokens: int = 500_000
    hard_cap_usd: float = 5.00
    warning_thresholds: list[float] = [0.70, 0.90]
    pricing: dict[str, dict[str, PricingEntry]] = Field(default_factory=dict)


class ContextConfig(BaseModel):
    compaction_threshold: float = 0.6
    preserve_recent: int = 4
    max_tool_result_tokens: int = 2000
    truncation_strategy: str = "head_tail"
    context_window_tokens: int = 200_000  # assumed model context window for threshold calc


class AgentsConfig(BaseModel):
    max_parallel: int = 3
    max_iterations: int = 20
    roles: list[str] = ["planner", "coder", "reviewer", "tester"]


class AllowlistEntry(BaseModel):
    pattern: str
    classification: str = "safe"


class BlocklistEntry(BaseModel):
    pattern: str
    classification: str = "blocked"
    reason: str = "Not allowed"


class SafetyConfig(BaseModel):
    block_sudo: bool = True
    auto_approve_writes: bool = False
    max_write_size: int = 1_048_576
    allowlist: list[AllowlistEntry] = Field(default_factory=list)
    blocklist: list[BlocklistEntry] = Field(default_factory=list)


class UIConfig(BaseModel):
    show_agent_activity: bool = True
    show_token_dashboard: bool = True
    theme: str = "dark"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "./itakt.log"
    log_tool_calls: bool = True
    log_token_usage: bool = True


class Config(BaseModel):
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    anthropic_api_key: Optional[str] = None

    @model_validator(mode="after")
    def _pull_api_key(self) -> "Config":
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        return self


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_dotenv(dotenv_path: Path) -> None:
    """Minimal .env parser — sets env vars that are not already set."""
    if not dotenv_path.exists():
        return
    with open(dotenv_path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value


def load_config(config_path: Optional[str] = None) -> Config:
    """Load and validate configuration.

    Search order for config file:
      1. ``config_path`` argument
      2. ``ITAKT_CONFIG`` environment variable
      3. ``./itakt.yaml``

    .env is always loaded from the current working directory first.
    """
    _load_dotenv(Path(".env"))

    path_str = config_path or os.environ.get("ITAKT_CONFIG") or "itakt.yaml"
    path = Path(path_str)

    raw: dict = {}
    if path.exists():
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}

    config = Config.model_validate(raw)

    if not config.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )

    return config
