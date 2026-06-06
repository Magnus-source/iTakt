"""Tool Registry — read_file, list_directory, write_file, edit_file, bash."""
from __future__ import annotations

import difflib
import os
import subprocess
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Individual tool implementations (return strings for the LLM)
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    try:
        content = Path(path).read_text(errors="replace")
        return content
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except PermissionError:
        return f"ERROR: permission denied: {path}"
    except Exception as exc:
        return f"ERROR: {exc}"


def list_directory(path: str = ".") -> str:
    try:
        entries = sorted(os.listdir(path))
        if not entries:
            return "(empty directory)"
        lines = []
        for name in entries:
            full = os.path.join(path, name)
            marker = "/" if os.path.isdir(full) else ""
            lines.append(f"{name}{marker}")
        return "\n".join(lines)
    except FileNotFoundError:
        return f"ERROR: directory not found: {path}"
    except PermissionError:
        return f"ERROR: permission denied: {path}"
    except Exception as exc:
        return f"ERROR: {exc}"


def write_file(path: str, content: str) -> str:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except PermissionError:
        return f"ERROR: permission denied: {path}"
    except Exception as exc:
        return f"ERROR: {exc}"


def edit_file(path: str, old_text: str, new_text: str) -> tuple[str, str]:
    """Edit a file by exact search-replace.

    Returns (result_message, unified_diff).
    Fails if old_text not found or matches multiple locations.
    """
    try:
        original = Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return f"ERROR: file not found: {path}", ""
    except PermissionError:
        return f"ERROR: permission denied: {path}", ""
    except Exception as exc:
        return f"ERROR: {exc}", ""

    count = original.count(old_text)
    if count == 0:
        return f"ERROR: old_text not found in {path}", ""
    if count > 1:
        return f"ERROR: old_text matches {count} locations in {path} — be more specific", ""

    updated = original.replace(old_text, new_text, 1)

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )

    try:
        Path(path).write_text(updated)
    except Exception as exc:
        return f"ERROR writing {path}: {exc}", ""

    return f"Edited {path} successfully", diff


def bash(
    command: str,
    working_directory: Optional[str] = None,
    timeout: int = 30,
    max_output_chars: int = 8000,
) -> dict[str, Any]:
    """Run a shell command. Returns dict with stdout, stderr, exit_code."""
    cwd = working_directory or os.getcwd()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        stdout = _trim(proc.stdout, max_output_chars)
        stderr = proc.stderr  # never trim errors
        return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}
    except subprocess.TimeoutExpired:
        return {
            "stdout": f"(timeout after {timeout}s)",
            "stderr": "",
            "exit_code": -1,
        }
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "exit_code": -1}


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = int(max_chars * 0.3)
    omitted = len(text) - head - tail
    return (
        text[:head]
        + f"\n[... {omitted} chars trimmed ...]\n"
        + text[-tail:]
    )


# ---------------------------------------------------------------------------
# Anthropic tool schemas (used by the LLM)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "read_file",
        "description": "Read the full contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path. Defaults to current directory.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Destination file path."},
                "content": {"type": "string", "description": "File content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edit a file by replacing an exact occurrence of old_text with new_text. "
            "Fails if old_text is not found or appears more than once."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File to edit."},
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find (must match exactly once).",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a shell command and return stdout/stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."},
                "working_directory": {
                    "type": "string",
                    "description": "Working directory (optional).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 30).",
                },
            },
            "required": ["command"],
        },
    },
]

YIELD_TO_USER_SCHEMA: dict = {
    "name": "yield_to_user",
    "description": (
        "Hand control back to the user with a response message. "
        "Call this when you have completed the task or need user input."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The response to present to the user.",
            },
        },
        "required": ["message"],
    },
}


# ---------------------------------------------------------------------------
# Registry — dispatch tool calls by name
# ---------------------------------------------------------------------------

class ToolRegistry:
    def __init__(self, max_tool_result_tokens: int = 2000) -> None:
        self._max_chars = max_tool_result_tokens * 4  # ~4 chars/token

    def execute(self, name: str, inputs: dict) -> str:
        """Execute a tool and return its result as a string."""
        if name == "read_file":
            return read_file(inputs["path"])

        if name == "list_directory":
            return list_directory(inputs.get("path", "."))

        if name == "write_file":
            return write_file(inputs["path"], inputs["content"])

        if name == "edit_file":
            msg, diff = edit_file(
                inputs["path"], inputs["old_text"], inputs["new_text"]
            )
            if diff:
                return f"{msg}\n\n{diff}"
            return msg

        if name == "bash":
            result = bash(
                inputs["command"],
                working_directory=inputs.get("working_directory"),
                timeout=inputs.get("timeout", 30),
                max_output_chars=self._max_chars,
            )
            parts = [f"Exit code: {result['exit_code']}"]
            if result["stdout"]:
                parts.append(f"stdout:\n{result['stdout']}")
            if result["stderr"]:
                parts.append(f"stderr:\n{result['stderr']}")
            return "\n".join(parts)

        return f"ERROR: unknown tool '{name}'"

    def get_edit_preview(self, path: str, old_text: str, new_text: str) -> str:
        """Generate a diff preview for the review prompt without modifying the file."""
        try:
            original = Path(path).read_text(errors="replace")
        except Exception as exc:
            return f"(cannot preview: {exc})"
        count = original.count(old_text)
        if count == 0:
            return "(old_text not found — edit will fail)"
        if count > 1:
            return f"(old_text found {count} times — edit will fail)"
        updated = original.replace(old_text, new_text, 1)
        return "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
