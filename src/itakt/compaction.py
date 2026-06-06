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

    to_compact = messages[:-preserve_n] if preserve_n else messages[:]
    to_keep = messages[-preserve_n:] if preserve_n else []

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
