"""Safety Layer — classify tool calls, handle approval flow, write audit log."""
from __future__ import annotations

import datetime
import re
from enum import Enum
from pathlib import Path
from typing import Optional

from .config import SafetyConfig
from .tools import ToolRegistry


class Classification(str, Enum):
    SAFE = "safe"
    REVIEW = "review"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Built-in default patterns (from SAFETY.md)
# ---------------------------------------------------------------------------

_SAFE_BASH_RE = re.compile(
    r"^("
    r"ls( |$)|cat |head |tail |wc |find |grep |echo |pwd$|which |env$|date$"
    r"|python -c [\"']"
    r"|pytest|python -m pytest"
    r"|git (status|log|diff)"
    r")",
    re.IGNORECASE,
)

_BLOCKED_BASH_RE = re.compile(
    r"("
    r"rm\s+-rf\s+/|rm\s+-rf\s+~"
    r"|\bformat\b|\bmkfs\b"
    r"|dd\s+if="
    r"|chmod\s+777"
    r"|curl.+\|\s*sh|wget.+\|\s*sh"
    r"|\bshutdown\b|\breboot\b"
    r"|>\s*/etc/|>\s*/usr/"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# SafetyLayer
# ---------------------------------------------------------------------------

class SafetyLayer:
    def __init__(
        self,
        safety_cfg: SafetyConfig,
        registry: ToolRegistry,
        audit_log_path: str = "./itakt_audit.log",
    ) -> None:
        self._cfg = safety_cfg
        self._registry = registry
        self._audit_path = Path(audit_log_path)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, tool_name: str, tool_input: dict) -> tuple[Classification, str]:
        """Return (classification, reason)."""

        # File-size guard for write_file
        if tool_name == "write_file":
            content = tool_input.get("content", "")
            if len(content.encode()) > self._cfg.max_write_size:
                return Classification.BLOCKED, "file exceeds max_write_size"

        # Tool-level defaults (non-bash)
        if tool_name in ("read_file", "list_directory"):
            return Classification.SAFE, "read-only"
        if tool_name in ("write_file", "edit_file"):
            if self._cfg.auto_approve_writes:
                return Classification.SAFE, "auto_approve_writes=true"
            # Still check config blocklist before returning review
            # (handled below for bash; for file ops just return review unless listed)

        # Bash classification
        if tool_name == "bash":
            command = tool_input.get("command", "")
            return self._classify_bash(command)

        # write_file / edit_file default
        return Classification.REVIEW, "file modification"

    def _classify_bash(self, command: str) -> tuple[Classification, str]:
        # 1. Config blocklist
        for entry in self._cfg.blocklist:
            if re.search(entry.pattern, command, re.IGNORECASE):
                return Classification.BLOCKED, entry.reason

        # 2. sudo check
        if self._cfg.block_sudo and re.search(r"\bsudo\b", command):
            return Classification.BLOCKED, "sudo commands are blocked"

        # 3. Built-in blocked patterns
        if _BLOCKED_BASH_RE.search(command):
            return Classification.BLOCKED, "matches built-in blocked pattern"

        # 4. Config allowlist
        for entry in self._cfg.allowlist:
            if re.search(entry.pattern, command, re.IGNORECASE):
                cls = Classification(entry.classification)
                return cls, f"config allowlist: {entry.pattern}"

        # 5. Built-in safe patterns
        if _SAFE_BASH_RE.match(command.strip()):
            return Classification.SAFE, "matches built-in safe pattern"

        # 6. Default bash → review
        return Classification.REVIEW, "bash default"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self, tool_name: str, tool_input: dict, agent_name: str = "agent"
    ) -> str:
        """Classify, optionally prompt for approval, execute or reject."""
        cls, reason = self.classify(tool_name, tool_input)

        if cls == Classification.BLOCKED:
            msg = f"[BLOCKED] {tool_name}: {reason}"
            self._audit(tool_name, tool_input, agent_name, cls, "REJECTED", reason)
            return msg

        if cls == Classification.SAFE:
            result = self._registry.execute(tool_name, tool_input)
            self._audit(tool_name, tool_input, agent_name, cls, "EXECUTED")
            return result

        # REVIEW — prompt user
        approved = self._prompt_review(tool_name, tool_input, agent_name)
        if approved:
            result = self._registry.execute(tool_name, tool_input)
            self._audit(tool_name, tool_input, agent_name, cls, "APPROVED→EXECUTED")
            return result
        else:
            self._audit(tool_name, tool_input, agent_name, cls, "DENIED")
            return f"[DENIED] {tool_name} was not approved by user."

    # ------------------------------------------------------------------
    # Review prompt
    # ------------------------------------------------------------------

    def _prompt_review(
        self, tool_name: str, tool_input: dict, agent_name: str
    ) -> bool:
        print()
        print("=" * 60)
        print(f"  Review Required")
        print(f"  Agent : {agent_name}")
        print(f"  Tool  : {tool_name}")

        if tool_name == "edit_file":
            path = tool_input.get("path", "")
            old = tool_input.get("old_text", "")
            new = tool_input.get("new_text", "")
            print(f"  File  : {path}")
            diff = self._registry.get_edit_preview(path, old, new)
            print("\nDiff preview:")
            print(diff or "(no diff)")

        elif tool_name == "write_file":
            path = tool_input.get("path", "")
            content = tool_input.get("content", "")
            print(f"  File  : {path}  ({len(content)} bytes)")

        elif tool_name == "bash":
            print(f"  Command: {tool_input.get('command', '')}")
            wd = tool_input.get("working_directory")
            if wd:
                print(f"  Cwd   : {wd}")

        print("=" * 60)

        try:
            answer = input("[A]pprove / [D]eny > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "d"

        return answer in ("a", "approve", "y", "yes")

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _audit(
        self,
        tool_name: str,
        tool_input: dict,
        agent_name: str,
        cls: Classification,
        outcome: str,
        reason: str = "",
    ) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = _summarise_input(tool_name, tool_input)
        line = f"[{ts}] {agent_name} TOOL {tool_name} {summary} → {cls.value.upper()} → {outcome}"
        if reason:
            line += f" ({reason})"
        try:
            with open(self._audit_path, "a") as fh:
                fh.write(line + "\n")
        except Exception:
            pass  # audit log failure must never crash the agent


def _summarise_input(tool_name: str, inputs: dict) -> str:
    if tool_name == "bash":
        return repr(inputs.get("command", "")[:60])
    if tool_name in ("read_file", "write_file", "edit_file"):
        return repr(inputs.get("path", ""))
    if tool_name == "list_directory":
        return repr(inputs.get("path", "."))
    return ""
