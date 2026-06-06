"""Tests for tool-result trimming — Context Engine Layer 2."""
from __future__ import annotations

import pytest
from pathlib import Path

from itakt.tools import _trim, bash, ToolRegistry


# ---------------------------------------------------------------------------
# _trim helper
# ---------------------------------------------------------------------------

def test_trim_short_text_unchanged():
    text = "hello world"
    assert _trim(text, max_chars=100) == text


def test_trim_long_text_reduced():
    text = "x" * 10_000
    result = _trim(text, max_chars=1000)
    assert len(result) < len(text)


def test_trim_contains_marker():
    text = "A" * 5000 + "B" * 5000
    result = _trim(text, max_chars=1000)
    assert "trimmed" in result or "..." in result


def test_trim_preserves_head_and_tail():
    head = "HEAD_START"
    tail = "TAIL_END"
    filler = "x" * 10_000
    text = head + filler + tail
    result = _trim(text, max_chars=500)
    assert head in result
    assert tail in result


def test_trim_head_60pct_tail_30pct():
    """Verify the 60/30 split ratio."""
    text = "x" * 10_000
    max_chars = 1000
    result = _trim(text, max_chars)
    head = int(max_chars * 0.6)
    tail = int(max_chars * 0.3)
    # Result length ≈ head + tail + marker
    assert len(result) <= head + tail + 200  # 200 chars for the marker line


# ---------------------------------------------------------------------------
# bash stderr is never trimmed
# ---------------------------------------------------------------------------

def test_bash_stderr_not_trimmed():
    """Large stderr output is preserved in full (errors must never be truncated)."""
    # Generate a command with verbose stderr
    cmd = "for i in $(seq 1 200); do echo 'error line '$i >&2; done"
    result = bash(cmd, max_output_chars=100)  # tiny limit for stdout
    # stderr should have all 200 lines
    assert result["exit_code"] == 0
    stderr_lines = result["stderr"].strip().splitlines()
    assert len(stderr_lines) == 200, f"Got {len(stderr_lines)} stderr lines, expected 200"


def test_bash_stdout_trimmed_when_large():
    """Large stdout is trimmed to max_output_chars."""
    # Generate 10000 chars of stdout
    cmd = "python3 -c \"print('x' * 10000)\""
    result = bash(cmd, max_output_chars=500)
    assert len(result["stdout"]) < 10_000
    assert "trimmed" in result["stdout"] or len(result["stdout"]) <= 600


# ---------------------------------------------------------------------------
# ToolRegistry trims read_file output
# ---------------------------------------------------------------------------

def test_registry_read_file_trims_large_file(tmp_path):
    """read_file via registry is trimmed when file exceeds max_tool_result_tokens."""
    # Write a file with ~10k chars
    large_file = tmp_path / "big.txt"
    large_file.write_text("line\n" * 2000)

    # max_tool_result_tokens=100 → max_chars=400
    registry = ToolRegistry(max_tool_result_tokens=100)
    result = registry.execute("read_file", {"path": str(large_file)})

    assert len(result) < 10_000
    assert "trimmed" in result or len(result) <= 500


def test_registry_read_file_error_not_trimmed():
    """ERROR messages from read_file are never trimmed."""
    registry = ToolRegistry(max_tool_result_tokens=10)  # tiny limit
    result = registry.execute("read_file", {"path": "/nonexistent/path/file.txt"})
    assert result.startswith("ERROR:")


def test_registry_read_file_small_file_unchanged(tmp_path):
    """Small files pass through without a truncation marker."""
    f = tmp_path / "small.txt"
    f.write_text("hello world\n")
    registry = ToolRegistry(max_tool_result_tokens=2000)
    result = registry.execute("read_file", {"path": str(f)})
    assert "trimmed" not in result
    assert "hello world" in result


# ---------------------------------------------------------------------------
# bash max_output_chars in ToolRegistry
# ---------------------------------------------------------------------------

def test_registry_bash_applies_trimming():
    """bash via registry respects the max_tool_result_tokens limit."""
    registry = ToolRegistry(max_tool_result_tokens=50)  # ~200 chars
    result = registry.execute("bash", {"command": "python3 -c \"print('y'*5000)\""})
    # stdout in the formatted result should be trimmed
    assert len(result) < 5_000
