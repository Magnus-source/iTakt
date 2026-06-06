"""Tests for the Tool Registry."""
import os
import pytest
from pathlib import Path

from itakt.tools import (
    ToolRegistry,
    read_file,
    list_directory,
    write_file,
    edit_file,
    bash,
)


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def test_read_file_success(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world\n")
    result = read_file(str(f))
    assert "hello world" in result


def test_read_file_not_found(tmp_path):
    result = read_file(str(tmp_path / "nonexistent.txt"))
    assert "error" in result.lower()
    assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------

def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "subdir").mkdir()
    result = list_directory(str(tmp_path))
    assert "a.txt" in result
    assert "b.txt" in result
    assert "subdir/" in result


def test_list_directory_not_found(tmp_path):
    result = list_directory(str(tmp_path / "missing"))
    assert "error" in result.lower()


def test_list_directory_empty(tmp_path):
    result = list_directory(str(tmp_path))
    assert "empty" in result.lower()


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

def test_write_file(tmp_path):
    path = str(tmp_path / "new.txt")
    result = write_file(path, "hello")
    assert "wrote" in result.lower() or "error" not in result.lower()
    assert Path(path).read_text() == "hello"


def test_write_file_creates_parents(tmp_path):
    path = str(tmp_path / "nested" / "dir" / "file.txt")
    result = write_file(path, "data")
    assert Path(path).exists()
    assert Path(path).read_text() == "data"


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

def test_edit_file_success(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("def hello():\n    pass\n")
    msg, diff = edit_file(str(f), "    pass", "    return 'hi'")
    assert "error" not in msg.lower()
    assert "return 'hi'" in f.read_text()
    assert "pass" not in f.read_text()
    assert "+" in diff  # diff shows addition


def test_edit_file_not_found_text(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("def hello():\n    pass\n")
    msg, diff = edit_file(str(f), "nonexistent text", "replacement")
    assert "error" in msg.lower()
    assert "not found" in msg.lower()
    assert diff == ""


def test_edit_file_multiple_matches(tmp_path):
    f = tmp_path / "dup.py"
    f.write_text("foo\nfoo\nbar\n")
    msg, diff = edit_file(str(f), "foo", "baz")
    assert "error" in msg.lower()
    assert "multiple" in msg.lower() or "2" in msg


def test_edit_file_file_not_found(tmp_path):
    msg, diff = edit_file(str(tmp_path / "missing.py"), "old", "new")
    assert "error" in msg.lower()
    assert diff == ""


def test_edit_file_preserves_rest(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("line1\nTARGET\nline3\n")
    msg, diff = edit_file(str(f), "TARGET", "REPLACED")
    assert "error" not in msg.lower()
    content = f.read_text()
    assert "line1" in content
    assert "REPLACED" in content
    assert "line3" in content
    assert "TARGET" not in content


# ---------------------------------------------------------------------------
# bash
# ---------------------------------------------------------------------------

def test_bash_success():
    result = bash("echo hello")
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]


def test_bash_nonzero_exit():
    result = bash("false")
    assert result["exit_code"] != 0


def test_bash_stderr():
    result = bash("echo err >&2")
    # Some shells may put it in stdout or stderr depending on implementation
    combined = result["stdout"] + result["stderr"]
    assert "err" in combined


def test_bash_timeout():
    result = bash("sleep 10", timeout=1)
    assert result["exit_code"] != 0
    assert "timeout" in result["stdout"].lower()


def test_bash_working_directory(tmp_path):
    result = bash("pwd", working_directory=str(tmp_path))
    assert str(tmp_path) in result["stdout"]


# ---------------------------------------------------------------------------
# ToolRegistry.execute (integration)
# ---------------------------------------------------------------------------

def test_registry_read_file(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("content")
    reg = ToolRegistry()
    out = reg.execute("read_file", {"path": str(f)})
    assert "content" in out


def test_registry_edit_file_diff_in_output(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("alpha\nbeta\n")
    reg = ToolRegistry()
    out = reg.execute("edit_file", {"path": str(f), "old_text": "alpha", "new_text": "omega"})
    assert "omega" in f.read_text()
    assert "+" in out  # diff present in output


def test_registry_unknown_tool():
    reg = ToolRegistry()
    out = reg.execute("vaporize", {})
    assert "unknown" in out.lower()
