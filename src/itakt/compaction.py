"""Chat compaction — Context Engine Layer 1.

Spec (CONTEXT-ENGINE.md):
  1. Take all messages except system prompt and last preserve_recent exchanges.
  2. Send them to the compaction model with the compaction prompt.
  3. Replace old messages with a single [Compacted Summary] message.
  4. Write removed messages to traces/ so history is preserved, not deleted.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import ContextConfig, ModelConfig
from .provider import AnthropicProvider

COMPACTION_PROMPT = (
    "Summarize this conversation, preserving all key decisions, "
    "file changes made, current task status, and any unresolved issues. "
    "Be thorough but concise."
)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: JSON-serialise and divide char count by 4."""
    try:
        return len(json.dumps(messages, default=str)) // 4
    except Exception:
        return 0


def should_compact(messages: list[dict], context_cfg: ContextConfig) -> bool:
    """True when estimated tokens exceed compaction_threshold × context_window."""
    threshold = int(context_cfg.compaction_threshold * context_cfg.context_window_tokens)
    return estimate_tokens(messages) >= threshold


# ---------------------------------------------------------------------------
# Tool-pair-safe split boundary
# ---------------------------------------------------------------------------

def _is_tool_result_message(msg: dict) -> bool:
    """True when *msg* carries one or more ``tool_result`` blocks.

    Such a message only makes sense immediately after the assistant
    ``tool_use`` message it answers — it must never become the first kept
    message after compaction, or its matching ``tool_use`` is gone.
    """
    content = msg.get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )


def _safe_split_index(messages: list[dict], preserve_n: int) -> int:
    """Return a split index that never separates a tool_use from its tool_result.

    The compactor keeps ``messages[split:]`` verbatim and summarises
    ``messages[:split]``.  We move the default boundary
    (``len - preserve_n``) *earlier* until it lands on a genuine user turn —
    i.e. a ``user`` message that is **not** a ``tool_result`` message.  That
    guarantees:

      * the kept tail starts with a user message (alternation stays valid after
        the injected summary/ack pair), and
      * no tool_use/tool_result pair is split across the boundary.

    Returns ``0`` when no safe boundary exists at/before the default (the whole
    history is one unbroken exchange); the caller then skips compaction.
    """
    if preserve_n <= 0:
        return len(messages)
    split = len(messages) - preserve_n
    if split <= 0:
        return 0
    while split > 0 and (
        messages[split].get("role") != "user"
        or _is_tool_result_message(messages[split])
    ):
        split -= 1
    return split


# ---------------------------------------------------------------------------
# Message serialisation helper
# ---------------------------------------------------------------------------

def _messages_to_text(messages: list[dict]) -> str:
    """Convert a messages list to readable plain text for the compaction prompt."""
    lines = []
    for msg in messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    inp = json.dumps(block.get("input", {}), default=str)[:150]
                    parts.append(f"[Tool call: {block.get('name')}({inp})]")
                elif btype == "tool_result":
                    res = str(block.get("content", ""))[:150]
                    parts.append(f"[Tool result: {res}]")
            content = " ".join(parts)

        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------

async def compact_messages(
    messages: list[dict],
    system: str,
    context_cfg: ContextConfig,
    provider: AnthropicProvider,
    model_cfg: ModelConfig,
    agent_name: str = "agent",
    traces_dir: str = "traces",
) -> list[dict]:
    """Compact old messages via LLM summary.

    Keeps the last preserve_recent exchanges verbatim; everything older is
    summarised.  The removed messages are written to a trace file before being
    discarded so "did you lose information?" is always answerable: no.

    Returns a new (shorter) messages list.
    """
    # An "exchange" = one user + one assistant message = 2 items
    preserve_n = context_cfg.preserve_recent * 2

    if len(messages) <= preserve_n + 1:
        return messages  # nothing old enough to compact

    # Choose a boundary that never splits a tool_use/tool_result pair.  If no
    # safe boundary exists at/before the default, the history is one unbroken
    # exchange — leave it untouched rather than emit an invalid sequence.
    split = _safe_split_index(messages, preserve_n)
    if split <= 0:
        return messages

    to_compact = messages[:split]
    to_keep = messages[split:]

    before_tokens = estimate_tokens(messages)

    # 1. Write trace before discarding -----------------------------------------
    Path(traces_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_path = Path(traces_dir) / f"compaction_{agent_name}_{ts}.json"
    try:
        with open(trace_path, "w") as fh:
            json.dump(
                {"agent": agent_name, "timestamp": ts, "removed_messages": to_compact},
                fh,
                indent=2,
                default=str,
            )
    except Exception as exc:
        print(f"[context] WARNING: could not write trace: {exc}")
        trace_path = Path("(trace write failed)")

    # 2. Ask compaction model to summarise -------------------------------------
    history_text = _messages_to_text(to_compact)
    summary_request = [
        {
            "role": "user",
            "content": (
                f"{COMPACTION_PROMPT}\n\nConversation to summarize:\n\n{history_text}"
            ),
        }
    ]

    summary_text = "(compaction summary unavailable)"
    try:
        response = await provider.complete(
            system=(
                "You are a helpful assistant. Produce accurate, concise summaries "
                "of agentic coding conversations."
            ),
            messages=summary_request,
            tools=[],
            model_cfg=model_cfg,
        )
        for block in response.content:
            if hasattr(block, "text") and block.text:
                summary_text = block.text
                break
    except Exception as exc:
        summary_text = f"[compaction LLM call failed: {exc}]"

    # 3. Build new messages: summary pair + recent exchanges -------------------
    # Inject as user/assistant so the alternation rule is never broken:
    #   user(summary) → assistant(ack) → [to_keep starts with user] → …
    new_messages: list[dict] = [
        {
            "role": "user",
            "content": f"[Compacted Summary of Earlier Conversation]\n{summary_text}",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Understood. I have reviewed the summary and will continue.",
                }
            ],
        },
        *to_keep,
    ]

    after_tokens = estimate_tokens(new_messages)
    pct = round((1 - after_tokens / max(before_tokens, 1)) * 100)

    print(
        f"[context] compacted {before_tokens:,} → {after_tokens:,} tokens "
        f"({pct}% reduced); full history in {trace_path}"
    )

    return new_messages
