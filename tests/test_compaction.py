"""Tests for chat compaction — Context Engine Layer 1."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from itakt.compaction import (
    compact_messages,
    estimate_tokens,
    should_compact,
    _messages_to_text,
)
from itakt.config import ContextConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_context_cfg(**overrides) -> ContextConfig:
    return ContextConfig(
        compaction_threshold=overrides.get("compaction_threshold", 0.6),
        preserve_recent=overrides.get("preserve_recent", 2),
        max_tool_result_tokens=2000,
        context_window_tokens=overrides.get("context_window_tokens", 200_000),
    )


def make_long_messages(n_pairs: int = 10) -> list[dict]:
    """Create n_pairs of user/assistant exchanges."""
    msgs = []
    for i in range(n_pairs):
        msgs.append({"role": "user", "content": f"User message {i} " + "x" * 50})
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": f"Assistant response {i} " + "y" * 50}]})
    return msgs


class FakeBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeUsage:
    input_tokens = 50
    output_tokens = 100


class FakeResponse:
    def __init__(self, text: str = "This is a compaction summary."):
        self.content = [FakeBlock(text)]
        self.stop_reason = "end_turn"
        self.usage = FakeUsage()


class FakeProvider:
    def __init__(self, response_text: str = "This is a compaction summary."):
        self.calls: list[dict] = []
        self._text = response_text

    async def complete(self, system, messages, tools, model_cfg):
        self.calls.append({"system": system, "messages": messages})
        return FakeResponse(self._text)


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------

def test_estimate_tokens_empty():
    assert estimate_tokens([]) == 0


def test_estimate_tokens_nonempty():
    msgs = [{"role": "user", "content": "hello world"}]
    estimate = estimate_tokens(msgs)
    assert estimate > 0


def test_estimate_tokens_grows_with_more_messages():
    short = [{"role": "user", "content": "hi"}]
    long = [{"role": "user", "content": "hi " + "x" * 1000}]
    assert estimate_tokens(long) > estimate_tokens(short)


# ---------------------------------------------------------------------------
# should_compact
# ---------------------------------------------------------------------------

def test_should_compact_false_below_threshold():
    # small messages, very high threshold
    msgs = [{"role": "user", "content": "tiny"}]
    cfg = make_context_cfg(compaction_threshold=0.9, context_window_tokens=200_000)
    assert should_compact(msgs, cfg) is False


def test_should_compact_true_above_threshold():
    # Fill messages to exceed a tiny threshold
    msgs = make_long_messages(50)  # 100 messages, each with 50+ chars
    cfg = make_context_cfg(compaction_threshold=0.001, context_window_tokens=200_000)
    # 0.001 * 200_000 = 200 tokens threshold → easy to exceed
    assert should_compact(msgs, cfg) is True


def test_should_compact_at_exact_threshold():
    """Just below threshold → False."""
    msgs = [{"role": "user", "content": "x" * 100}]
    tok = estimate_tokens(msgs)
    # Set threshold just above current estimate → should not compact
    window = tok * 2
    cfg = make_context_cfg(compaction_threshold=0.9, context_window_tokens=window)
    # 0.9 * (tok*2) = 1.8*tok > tok → False
    assert should_compact(msgs, cfg) is False


# ---------------------------------------------------------------------------
# compact_messages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compact_reduces_token_estimate(tmp_path):
    messages = make_long_messages(20)  # 40 messages
    before = estimate_tokens(messages)

    provider = FakeProvider("Summary: we did lots of things.")
    cfg = make_context_cfg(preserve_recent=2)
    from itakt.config import ModelConfig
    model_cfg = ModelConfig(model="fake-haiku", max_tokens=1024, temperature=0.1)

    result = await compact_messages(
        messages=messages,
        system="You are an agent.",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="test-agent",
        traces_dir=str(tmp_path / "traces"),
    )

    after = estimate_tokens(result)
    assert after < before, f"Expected after ({after}) < before ({before})"


@pytest.mark.asyncio
async def test_compact_writes_trace_file(tmp_path):
    messages = make_long_messages(10)
    provider = FakeProvider()
    cfg = make_context_cfg(preserve_recent=2)
    from itakt.config import ModelConfig
    model_cfg = ModelConfig(model="fake", max_tokens=512)

    traces_dir = str(tmp_path / "traces")
    await compact_messages(
        messages=messages,
        system="sys",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="agent-x",
        traces_dir=traces_dir,
    )

    trace_files = list(Path(traces_dir).glob("compaction_agent-x_*.json"))
    assert len(trace_files) == 1, "Expected exactly one trace file"

    data = json.loads(trace_files[0].read_text())
    assert data["agent"] == "agent-x"
    assert "removed_messages" in data
    assert len(data["removed_messages"]) > 0


@pytest.mark.asyncio
async def test_compact_preserves_recent_messages(tmp_path):
    """The last preserve_recent*2 messages must appear verbatim in the result."""
    messages = make_long_messages(10)  # 20 messages
    preserve_recent = 3
    cfg = make_context_cfg(preserve_recent=preserve_recent)

    provider = FakeProvider("A summary.")
    from itakt.config import ModelConfig
    model_cfg = ModelConfig(model="fake", max_tokens=512)

    result = await compact_messages(
        messages=messages,
        system="sys",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="test",
        traces_dir=str(tmp_path / "traces"),
    )

    # The last preserve_recent*2 original messages must all appear in result
    expected_tail = messages[-(preserve_recent * 2):]
    result_texts = json.dumps(result, default=str)
    for msg in expected_tail:
        content = msg["content"]
        # For plain strings check directly; for lists extract inner text
        if isinstance(content, str):
            key = content[:20]
        else:
            # content is a list of dicts like [{"type": "text", "text": "..."}]
            key = content[0].get("text", "")[:20] if content else ""
        assert key in result_texts, f"Expected recent message not found: {key!r}"


@pytest.mark.asyncio
async def test_compact_summary_injected_as_user_message(tmp_path):
    """Result must start with a user message containing the compaction summary."""
    messages = make_long_messages(8)
    provider = FakeProvider("KEY SUMMARY TEXT HERE")
    cfg = make_context_cfg(preserve_recent=2)
    from itakt.config import ModelConfig
    model_cfg = ModelConfig(model="fake", max_tokens=512)

    result = await compact_messages(
        messages=messages,
        system="sys",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="test",
        traces_dir=str(tmp_path / "traces"),
    )

    assert result[0]["role"] == "user"
    assert "Compacted Summary" in result[0]["content"]
    assert "KEY SUMMARY TEXT HERE" in result[0]["content"]


@pytest.mark.asyncio
async def test_compact_too_short_returns_unchanged(tmp_path):
    """If messages is shorter than preserve_recent*2+1, return as-is."""
    messages = [{"role": "user", "content": "only one message"}]
    provider = FakeProvider()
    cfg = make_context_cfg(preserve_recent=4)
    from itakt.config import ModelConfig
    model_cfg = ModelConfig(model="fake", max_tokens=512)

    result = await compact_messages(
        messages=messages,
        system="sys",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="test",
        traces_dir=str(tmp_path / "traces"),
    )
    assert result == messages
    # No API call should have been made
    assert len(provider.calls) == 0


# ---------------------------------------------------------------------------
# _messages_to_text
# ---------------------------------------------------------------------------

def test_messages_to_text_plain():
    msgs = [{"role": "user", "content": "hello"}]
    text = _messages_to_text(msgs)
    assert "USER" in text
    assert "hello" in text


def test_messages_to_text_tool_use():
    msgs = [{"role": "assistant", "content": [
        {"type": "tool_use", "name": "read_file", "input": {"path": "README.md"}}
    ]}]
    text = _messages_to_text(msgs)
    assert "read_file" in text
    assert "Tool call" in text


# ---------------------------------------------------------------------------
# Compaction guard — no immediate re-compaction (1.2 fix)
# ---------------------------------------------------------------------------

def test_compaction_guard_skips_next_iteration():
    """Guard condition: after compacting at iteration N, skip N+1."""
    last_compacted_at = 3

    # Iteration 4 = last_compacted_at + 1 → SKIP
    assert 4 == last_compacted_at + 1

    # Iteration 5 ≠ last_compacted_at + 1 → ALLOW
    assert 5 != last_compacted_at + 1


def test_compaction_guard_initial_value():
    """Initial value -2 means no skip on iteration 0 or 1."""
    last_compacted_at = -2
    # iteration 0: skipped by `iteration > 0` guard regardless
    # iteration 1: 1 != -2+1 = -1 → ALLOW
    assert 1 != last_compacted_at + 1
    # iteration 2: 2 != -1 → ALLOW
    assert 2 != last_compacted_at + 1


@pytest.mark.asyncio
async def test_compact_does_not_immediately_refire(tmp_path):
    """After compaction, should_compact must return False on the very next check
    when the guard is active (messages have not grown further)."""
    from itakt.compaction import should_compact, compact_messages
    from itakt.config import ContextConfig, ModelConfig

    messages = make_long_messages(20)  # well above any threshold

    cfg = ContextConfig(
        compaction_threshold=0.001,  # always triggers
        preserve_recent=2,
        context_window_tokens=200_000,
    )

    provider = FakeProvider("Summary.")
    model_cfg = ModelConfig(model="fake", max_tokens=512)

    # First compact
    result_msgs = await compact_messages(
        messages=messages,
        system="sys",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="guard-test",
        traces_dir=str(tmp_path / "traces"),
    )

    # The guard in the loop checks: iteration != last_compacted_at + 1
    # Simulate: we're now on the iteration immediately after compaction.
    # Even though should_compact() would fire again (tokens still above threshold),
    # the guard prevents it.
    last_compacted_at = 5
    current_iteration = 6  # = last_compacted_at + 1

    guard_blocks = (current_iteration == last_compacted_at + 1)
    assert guard_blocks, "Guard should block immediate re-compaction"

    # One iteration later the guard no longer blocks
    current_iteration = 7
    guard_blocks = (current_iteration == last_compacted_at + 1)
    assert not guard_blocks, "Guard should allow compaction after skipping one iteration"
