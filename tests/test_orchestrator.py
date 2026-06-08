"""Tests for orchestrator: spawn_sub_agent schema, parallel execution,
model routing, and result compression."""
from __future__ import annotations

import asyncio
import time

import pytest

from itakt.config import Config
from itakt.orchestrator import SPAWN_SUB_AGENT_SCHEMA, ORCHESTRATOR_TOOLS
from itakt.subagent import compress_result, ROLE_PROMPTS


# ---------------------------------------------------------------------------
# spawn_sub_agent schema
# ---------------------------------------------------------------------------

def test_spawn_sub_agent_schema_name():
    assert SPAWN_SUB_AGENT_SCHEMA["name"] == "spawn_sub_agent"


def test_spawn_sub_agent_schema_required_fields():
    props = SPAWN_SUB_AGENT_SCHEMA["input_schema"]["properties"]
    assert "role" in props
    assert "task" in props
    assert "context" in props


def test_spawn_sub_agent_schema_required_list():
    required = SPAWN_SUB_AGENT_SCHEMA["input_schema"]["required"]
    assert "role" in required
    assert "task" in required
    # context is optional
    assert "context" not in required


def test_spawn_sub_agent_schema_role_enum():
    role_prop = SPAWN_SUB_AGENT_SCHEMA["input_schema"]["properties"]["role"]
    assert "enum" in role_prop
    for r in ("planner", "coder", "reviewer", "tester"):
        assert r in role_prop["enum"]


def test_orchestrator_tools_includes_spawn():
    names = [t["name"] for t in ORCHESTRATOR_TOOLS]
    assert "spawn_sub_agent" in names
    assert "yield_to_user" in names
    assert "read_file" in names
    assert "bash" in names


# ---------------------------------------------------------------------------
# Parallel execution via asyncio.gather
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parallel_execution_is_concurrent():
    """Two 0.3 s tasks via gather complete in <0.5 s total (proving concurrency)."""
    start_times: dict[str, float] = {}
    end_times: dict[str, float] = {}

    async def fake_agent(name: str, delay: float) -> str:
        start_times[name] = time.monotonic()
        await asyncio.sleep(delay)
        end_times[name] = time.monotonic()
        return f"result-{name}"

    wall_start = time.monotonic()
    results = await asyncio.gather(
        fake_agent("a", 0.3),
        fake_agent("b", 0.3),
    )
    wall_elapsed = time.monotonic() - wall_start

    # Parallel: total elapsed is much less than the sum of individual delays
    assert wall_elapsed < 0.55, f"Elapsed {wall_elapsed:.2f}s — tasks ran sequentially"
    # Both tasks started before either finished (overlap)
    assert start_times["a"] < end_times["b"]
    assert start_times["b"] < end_times["a"]
    assert results == ["result-a", "result-b"]


@pytest.mark.asyncio
async def test_semaphore_caps_concurrency():
    """asyncio.Semaphore(1) forces sequential execution."""
    sem = asyncio.Semaphore(1)
    order: list[str] = []

    async def task(name: str) -> None:
        async with sem:
            order.append(f"start-{name}")
            await asyncio.sleep(0.05)
            order.append(f"end-{name}")

    await asyncio.gather(task("a"), task("b"))
    # With concurrency=1, a must fully complete before b starts
    assert order.index("end-a") < order.index("start-b") or \
           order.index("end-b") < order.index("start-a")


@pytest.mark.asyncio
async def test_gather_preserves_result_order():
    """asyncio.gather returns results in call order, not completion order."""
    async def slow(val: int) -> int:
        await asyncio.sleep(0.05 * (3 - val))  # val=3 fastest, val=1 slowest
        return val

    results = await asyncio.gather(slow(1), slow(2), slow(3))
    assert results == [1, 2, 3]


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------

def test_orchestrator_uses_sonnet_by_default():
    config = Config()
    # Default model IDs contain 'sonnet' for orchestrator, 'haiku' for sub_agents
    assert "sonnet" in config.models.orchestrator.model.lower()


def test_sub_agents_use_haiku_by_default():
    config = Config()
    assert "haiku" in config.models.sub_agents.model.lower()


def test_orchestrator_and_sub_agents_use_different_models():
    config = Config()
    assert config.models.orchestrator.model != config.models.sub_agents.model


def test_model_routing_from_yaml(tmp_path):
    """Config loaded from yaml correctly maps orchestrator vs sub_agent models."""
    import yaml
    from itakt.config import load_config

    cfg_data = {
        "models": {
            "orchestrator": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "sub_agents": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        }
    }
    cfg_file = tmp_path / "itakt.yaml"
    cfg_file.write_text(yaml.dump(cfg_data))

    import os
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    config = load_config(str(cfg_file))
    os.environ.pop("ANTHROPIC_API_KEY", None)

    assert config.models.orchestrator.model == "claude-sonnet-4-6"
    assert config.models.sub_agents.model == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Result compression
# ---------------------------------------------------------------------------

def test_compress_result_includes_role():
    s = compress_result("coder", "coder-1", "Add health endpoint", "Done", 100, 50, "haiku")
    assert "coder" in s


def test_compress_result_includes_task():
    s = compress_result("tester", "tester-1", "Write tests for /health", "Tests written", 80, 40, "haiku")
    assert "Write tests for /health" in s


def test_compress_result_includes_result():
    s = compress_result("coder", "coder-1", "task", "Added GET /health route", 100, 50, "haiku")
    assert "Added GET /health route" in s


def test_compress_result_includes_token_count():
    s = compress_result("coder", "coder-1", "task", "done", 1234, 567, "haiku")
    assert "1801" in s  # 1234 + 567


def test_compress_result_success_status():
    s = compress_result("coder", "coder-1", "task", "done", 10, 10, "haiku", status="success")
    assert "success" in s.lower()


def test_compress_result_failure_status():
    s = compress_result("coder", "coder-1", "task", "err", 10, 10, "haiku", status="budget_cap")
    assert "budget_cap" in s


# ---------------------------------------------------------------------------
# Role prompts
# ---------------------------------------------------------------------------

def test_all_roles_have_prompts():
    for role in ("planner", "coder", "reviewer", "tester"):
        assert role in ROLE_PROMPTS
        assert len(ROLE_PROMPTS[role]) > 50


def test_role_prompts_mention_yield_to_user():
    for role, prompt in ROLE_PROMPTS.items():
        assert "yield_to_user" in prompt, f"{role} prompt missing yield_to_user instruction"


# ---------------------------------------------------------------------------
# ConversationAgent.run_turn — multi-turn memory (no real API calls)
# ---------------------------------------------------------------------------

class _MockUsage:
    input_tokens = 10
    output_tokens = 5


class _MockTextBlock:
    type = "text"
    text = "Mock reply."


class _MockEndTurnResponse:
    content = [_MockTextBlock()]
    stop_reason = "end_turn"
    usage = _MockUsage()


class _MockProvider:
    """Returns a simple end_turn text response every time."""
    async def complete(self, system, messages, tools, model_cfg):
        return _MockEndTurnResponse()


@pytest.mark.asyncio
async def test_run_turn_preserves_history():
    """Two sequential run_turn calls must carry history from the first turn."""
    from itakt.config import SafetyConfig
    from itakt.monitor import TokenMonitor
    from itakt.orchestrator import ConversationAgent
    from itakt.safety import SafetyLayer
    from itakt.tools import ToolRegistry

    config = Config()
    monitor = TokenMonitor(budget=config.budget)
    registry = ToolRegistry()
    safety = SafetyLayer(SafetyConfig(), registry, audit_log_path="/dev/null")

    agent = ConversationAgent(config, _MockProvider(), monitor, safety)

    await agent.run_turn("What is the capital of France?")
    await agent.run_turn("And what language do they speak there?")

    # Both user inputs must be present in the accumulated history
    user_texts = [
        m["content"]
        for m in agent.messages
        if m["role"] == "user" and isinstance(m["content"], str)
    ]
    assert "What is the capital of France?" in user_texts, (
        f"First turn not found in history: {user_texts}"
    )
    assert "And what language do they speak there?" in user_texts, (
        f"Second turn not found in history: {user_texts}"
    )


@pytest.mark.asyncio
async def test_run_turn_messages_alternate_roles():
    """After two turns the message sequence must alternate user/assistant."""
    from itakt.config import SafetyConfig
    from itakt.monitor import TokenMonitor
    from itakt.orchestrator import ConversationAgent
    from itakt.safety import SafetyLayer
    from itakt.tools import ToolRegistry

    config = Config()
    monitor = TokenMonitor(budget=config.budget)
    safety = SafetyLayer(SafetyConfig(), ToolRegistry(), audit_log_path="/dev/null")

    agent = ConversationAgent(config, _MockProvider(), monitor, safety)

    await agent.run_turn("Turn one")
    await agent.run_turn("Turn two")

    roles = [m["role"] for m in agent.messages]
    for i in range(len(roles) - 1):
        assert roles[i] != roles[i + 1], (
            f"Adjacent same-role messages at index {i}: {roles}"
        )


@pytest.mark.asyncio
async def test_run_turn_returns_reply():
    """run_turn must return the mock provider's text."""
    from itakt.config import SafetyConfig
    from itakt.monitor import TokenMonitor
    from itakt.orchestrator import ConversationAgent
    from itakt.safety import SafetyLayer
    from itakt.tools import ToolRegistry

    config = Config()
    monitor = TokenMonitor(budget=config.budget)
    safety = SafetyLayer(SafetyConfig(), ToolRegistry(), audit_log_path="/dev/null")

    agent = ConversationAgent(config, _MockProvider(), monitor, safety)
    reply = await agent.run_turn("Hello")
    assert reply == "Mock reply."


# ---------------------------------------------------------------------------
# _normalize_for_continuation
# ---------------------------------------------------------------------------

def test_normalize_converts_yield_to_user_to_text():
    from itakt.orchestrator import _normalize_for_continuation

    messages = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu1", "name": "yield_to_user",
             "input": {"message": "Here is my answer."}}
        ]},
    ]
    _normalize_for_continuation(messages)

    last = messages[-1]
    assert last["role"] == "assistant"
    assert last["content"][0]["type"] == "text"
    assert last["content"][0]["text"] == "Here is my answer."


def test_normalize_leaves_text_blocks_untouched():
    from itakt.orchestrator import _normalize_for_continuation

    messages = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": [{"type": "text", "text": "Already text."}]},
    ]
    _normalize_for_continuation(messages)
    assert messages[-1]["content"][0]["text"] == "Already text."


def test_normalize_noop_when_last_is_user():
    from itakt.orchestrator import _normalize_for_continuation

    messages = [{"role": "user", "content": "not assistant"}]
    _normalize_for_continuation(messages)  # must not raise
    assert messages[-1]["role"] == "user"
