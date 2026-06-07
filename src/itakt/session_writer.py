"""Session state writer — appends events to traces/ for the web dashboard.

ALL writes are wrapped in try/except and can NEVER raise or slow the agent.
The dashboard reads these files; if they are absent it shows an empty state.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_STATE_FILE = Path("traces/session_state.json")
_EVENTS_FILE = Path("traces/events.jsonl")


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def _write_state(state: dict) -> None:
    """Overwrite session_state.json atomically."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, default=str))
        tmp.replace(_STATE_FILE)
    except Exception:
        pass


def _append_event(event: dict) -> None:
    """Append one JSON line to events.jsonl."""
    try:
        _EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with open(_EVENTS_FILE, "a") as fh:
                fh.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API — called from orchestrator / monitor / compaction
# ---------------------------------------------------------------------------

def record_session_state(
    total_tokens: int,
    total_cost: float,
    budget_tokens: int,
    budget_usd: float,
    agents: dict[str, Any],
    steps: int,
) -> None:
    state = {
        "ts": _now(),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "budget_tokens": budget_tokens,
        "budget_usd": budget_usd,
        "agents": agents,
        "steps": steps,
    }
    _write_state(state)


def event_agent_spawn(agent_name: str, model: str, role: str, t_offset: float) -> None:
    _append_event({
        "ts": _now(), "type": "agent_spawn",
        "agent": agent_name, "model": model, "role": role, "t_offset": round(t_offset, 2),
    })


def event_agent_return(
    agent_name: str, tokens: int, cost: float, t_offset: float
) -> None:
    _append_event({
        "ts": _now(), "type": "agent_return",
        "agent": agent_name, "tokens": tokens, "cost": round(cost, 6), "t_offset": round(t_offset, 2),
    })


def event_tool_call(
    agent_name: str, tool: str, classification: str, outcome: str, summary: str
) -> None:
    _append_event({
        "ts": _now(), "type": "tool_call",
        "agent": agent_name, "tool": tool,
        "classification": classification, "outcome": outcome, "summary": summary[:80],
    })


def event_compaction(
    agent_name: str, before_tokens: int, after_tokens: int, trace_file: str
) -> None:
    _append_event({
        "ts": _now(), "type": "compaction",
        "agent": agent_name,
        "before": before_tokens, "after": after_tokens,
        "pct": round((1 - after_tokens / max(before_tokens, 1)) * 100),
        "trace": trace_file,
    })


def event_budget_warning(level: str) -> None:
    _append_event({"ts": _now(), "type": "budget_warning", "level": level})


def event_budget_cap(total_tokens: int, total_cost: float) -> None:
    _append_event({
        "ts": _now(), "type": "budget_cap",
        "total_tokens": total_tokens, "total_cost": round(total_cost, 6),
    })


def reset_session() -> None:
    """Clear event log and state at the start of a new session."""
    try:
        if _EVENTS_FILE.exists():
            _EVENTS_FILE.unlink()
        if _STATE_FILE.exists():
            _STATE_FILE.unlink()
    except Exception:
        pass
