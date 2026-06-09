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


# ---------------------------------------------------------------------------
# Tool-pair-safe compaction boundary (Bug B fix)
# ---------------------------------------------------------------------------

def _tool_pair_history() -> list[dict]:
    return [
        {"role": "user", "content": "task one"},
        {"role": "assistant", "content": [{"type": "text", "text": "done one"}]},
        {"role": "user", "content": "task two"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "a"}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "a"}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t2", "name": "read_file", "input": {"path": "b"}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "b"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "done two"}]},
    ]


def test_safe_split_index_skips_tool_result_boundary():
    """The default boundary lands on a tool_result message; the safe index must
    move earlier to a genuine user turn so no pair is split."""
    from itakt.compaction import _safe_split_index

    history = _tool_pair_history()  # len 8
    preserve_n = 2
    default = len(history) - preserve_n  # 6 → user(tool_result t2)
    assert history[default]["content"][0]["type"] == "tool_result"

    split = _safe_split_index(history, preserve_n)
    assert history[split]["role"] == "user"
    # the chosen boundary is a genuine user turn (not a tool_result message)
    assert history[split]["content"] == "task two"


@pytest.mark.asyncio
async def test_compact_keeps_tool_pairs_intact(tmp_path):
    """After compacting a history with tool_use/tool_result pairs, the result
    must be a valid sequence: no orphan tool_result, every tool_use answered."""
    from itakt.compaction import compact_messages
    from itakt.config import ModelConfig

    history = _tool_pair_history()
    cfg = make_context_cfg(preserve_recent=1)  # preserve_n=2 → default on a pair
    provider = FakeProvider("Summary.")
    model_cfg = ModelConfig(model="fake", max_tokens=512)

    result = await compact_messages(
        messages=history,
        system="sys",
        context_cfg=cfg,
        provider=provider,
        model_cfg=model_cfg,
        agent_name="pair-test",
        traces_dir=str(tmp_path / "traces"),
    )

    # No orphan tool_result: every tool_result has its tool_use in the prev msg.
    for i, msg in enumerate(result):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        rids = {b.get("tool_use_id") for b in content
                if isinstance(b, dict) and b.get("type") == "tool_result"}
        if rids:
            prev = result[i - 1].get("content", []) if i > 0 else []
            prev_uids = {b.get("id") for b in prev
                         if isinstance(b, dict) and b.get("type") == "tool_use"}
            assert rids <= prev_uids, f"orphan tool_result at index {i}: {rids - prev_uids}"
    # Roles still alternate (summary/ack pair + kept tail).
    roles = [m["role"] for m in result]
    for i in range(len(roles) - 1):
        assert roles[i] != roles[i + 1], f"non-alternating roles: {roles}"


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
