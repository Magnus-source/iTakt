# Day 3 — context engine + token dashboard + safety demo (the graded-hardest features)

## Context
Days 1-2 are done: foundation (config, provider, token monitor, tool registry, safety
layer, agent loop, REPL) and orchestration (sub-agents, asyncio.gather parallelism, model
routing, synthesis). Build ON these. Read the existing src/ first, then the specs as the
contract: specs/CONTEXT-ENGINE.md, specs/SAFETY.md, specs/FEATURES.md (F4 dashboard, F5
safety), specs/DEMO-PLAN.md (Demos 3, 4, 5). Discover interfaces, don't assume them.

## Scope — Day 3 only
Make the three most-graded features demonstrable live: token dashboard + hard budget cap
(Demo 3), blocked-command safety (Demo 4), and chat compaction (Demo 5). Do NOT build
Docker/packaging or the VG smoke test — that is Day 4. Stop after Demos 3, 4, 5 work.

## Build (in order)

### 1. Chat compaction (CONTEXT-ENGINE Layer 1) — THE most important; examiners probe this
Implement automatic compaction AND a manual `/compact` command.
- Trigger: history exceeds `compaction_threshold` (config, default 0.6 of context window).
  Also expose `/compact` to force it on demand for the demo.
- Mechanism (per spec): take all messages except the system prompt and the last
  `preserve_recent` exchanges (config, default 4); send them to the compaction model (Haiku
  from config) with: "Summarize this conversation, preserving all key decisions, file
  changes made, current task status, and any unresolved issues"; replace the old messages
  with a single [Compacted Summary] message; continue.
- CRITICAL demonstrability (must be provable, not just claimed):
  * Print: `[context] compacted <before> -> <after> tokens (<pct>% reduced); full history in trace`
  * The ctx value in the status line must visibly DROP after compaction.
  * BEFORE replacing them, write the removed messages to a trace file under traces/ so the
    full history is preserved — removed from the active context window, not deleted. This is
    the answer to "did you lose information?": no, it's in the trace.
  * After compaction the agent must still act correctly using summary + recent messages.
- Config: compaction_threshold (0.6), preserve_recent (4), compaction model (Haiku).

### 2. Token dashboard + budget enforcement (FEATURES F4) — Demo 3
- Rich panel: session tokens + cost, a budget bar with %, per-active-agent token + cost
  breakdown (orchestrator + sub-agents).
- Warnings: 70% yellow, 90% red (agents informed to wrap up).
- Hard cap (partially built in Night 1): at hard_cap, BLOCK further API calls and STOP the
  session with a budget summary. Make the stop demonstrable: with `hard_cap_tokens: 1000`
  and a big task ("Refactor the entire codebase"), the agent must hit the cap quickly and
  stop with the summary — not keep going.

### 3. Blocked-command safety (SAFETY.md) — Demo 4
The classifier exists from Night 1. Ensure the BLOCKED tier is demonstrable live: when an
agent attempts a destructive command (e.g. `rm -rf /tmp/*`), the safety layer REJECTS it
BEFORE execution with an explanation, the agent is informed, and it adapts to a safer
alternative. Verify the default blocked patterns from SAFETY.md (rm -rf /, format, dd,
chmod 777, curl|sh, sudo, redirects to /etc and /usr, etc.).

### 4. Tool-result trimming (CONTEXT-ENGINE Layer 2) — verify/complete
Ensure large tool outputs are trimmed to `max_tool_result_tokens` (default 2000) with the
head_tail strategy (first 60% / last 30% / "[... truncated N lines ...]"), and that ERROR
output is never truncated.

## Definition of done (Day 3)
Demos 3, 4, 5 run end-to-end:
- Demo 3: dashboard shows live cost + per-agent breakdown; with a low hard cap the agent
  hits it and STOPS with a budget summary.
- Demo 4: a destructive command is rejected before execution and the agent adapts.
- Demo 5: `/compact` shows before -> after tokens (% reduced), the ctx status line drops,
  the removed history is written to a trace file, and the agent still works correctly after.
Plus:
- Tests: compaction (assert after < before tokens, trace file written, recent + summary
  preserved); dashboard render; budget thresholds + hard-cap stop; blocked classification +
  agent adaptation; tool-result trimming.
- pytest all green (Days 1-3).
- PROGRESS.md updated: explain the compaction mechanism with a concrete before -> after
  example, the budget thresholds, and the blocked-command flow — human-readable.

## Working discipline (mandatory)
- You are on branch day3-context-safety (off day2-orchestration).
- Commit after each component.
- Do NOT use `source .venv/bin/activate` — invoke .venv/bin/python etc. directly.
- Build on the existing components; do not rewrite them unless a spec requires it.
- Keep PROGRESS.md current; log blockers under "## BLOCKED" and continue.
- Stop after Demos 3, 4, 5 work. Do not begin Day-4 (Docker, packaging, smoke test).
