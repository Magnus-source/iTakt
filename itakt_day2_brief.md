# Day 2 — build the iTakt orchestration layer (parallel sub-agents)

## Context
Night 1 is done on branch `night1-foundation`: config manager, Anthropic provider, token
monitor, tool registry (read_file/list_directory/write_file/edit_file/bash), safety layer
(safe/review/blocked), single-agent loop, and the REPL. Build ON these — do not rebuild
them. First read the existing `src/` to learn the real interfaces, then read the specs as
the contract: `specs/ARCHITECTURE.md` (§2 Main Agent, §3 Sub-Agents, Data Flow),
`specs/FEATURES.md` (F1 Multi-Agent Orchestration, F2 Smart Model Routing), and
`specs/DEMO-PLAN.md` (Demo 2). Discover interfaces, don't assume them.

## Scope — Day 2 only
Add real multi-agent orchestration with genuinely parallel sub-agents and model routing,
ending with DEMO-PLAN Demo 2 working end-to-end. Do NOT build the Rich dashboard,
compaction, the safety blocked-command demo, or Docker — later days. Stop after Demo 2 works.

## Build (in order)
1. Sub-agent runner — reuse the Night-1 agent loop as a sub-agent: role-specific system
   prompt, its OWN message history (clean focused context), its own per-agent token tracking
   feeding the existing token monitor, tool access through the existing safety layer. Roles:
   planner, coder, reviewer, tester.
2. spawn_sub_agent tool (orchestrator-only) — params: role, task (scoped), relevant context.
   Runs a sub-agent and returns a COMPRESSED summary (not the full conversation). The
   orchestrator must be able to request several in one turn.
3. Parallel execution — when 2+ sub-agents are requested, run them concurrently with
   asyncio.gather, capped at max_parallel from config (default 3). Must be genuinely
   concurrent. Make it observable: log each sub-agent start and end with timestamps so
   overlapping wall-clock is visible, e.g. "[agent] spawn coder-1 (haiku) t+0.0s" ...
   "[agent] return coder-1 tokens=... usd=... t+4.2s", and after a batch print
   "N sub-agents ran in parallel (overlap confirmed)".
4. Model routing (F2) — orchestrator uses orchestrator_model from config (Sonnet);
   sub-agents use sub_agent_model (Haiku) by default; orchestrator MAY pick a stronger model
   for a complex role. All model choices from config, nothing hardcoded. Log each agent's model.
5. Result compression + synthesis — compress each sub-agent output to a short summary before
   returning to the orchestrator; orchestrator synthesizes one final answer for the user.
6. Orchestrator decision logic — simple task (one file/quick question) → handle directly via
   the Night-1 single-agent path, no spawning. Complex task (multiple files, code + tests,
   refactor) → decompose and spawn. Orchestrator tools: spawn_sub_agent, yield_to_user, plus
   standard tools.
7. Demo prep — create a small demo project dir with a minimal Flask app.py so Demo 2 has
   something to edit. Add flask to dependencies and install it into .venv.

## Definition of done (Day 2)
Demo 2 runs end-to-end: "Add a /health endpoint to app.py that returns JSON {status: ok,
timestamp: <current time>}, and write a test for it" → orchestrator spawns a coder and a
tester in parallel (overlap visible in the log) → their edit_file/write_file go through the
safety approval flow → orchestrator runs pytest (passes) → synthesizes → yields. Plus:
- Tests: spawn_sub_agent; parallel execution (assert overlapping start/end timestamps);
  model routing (assert sub-agents use the Haiku model from config); result compression.
- pytest all green (Night-1 + Day-2).
- PROGRESS.md updated with a clear, human-readable explanation of HOW the parallelism
  (asyncio.gather) and model routing work — written so someone can learn the design from it.

## Working discipline (mandatory)
- You are on branch day2-orchestration (off night1-foundation).
- Commit after each component with a clear message.
- Do NOT use `source .venv/bin/activate` — invoke venv binaries directly (.venv/bin/python,
  .venv/bin/pytest, .venv/bin/pip) so bash doesn't trigger the source approval prompt.
- Build on the Night-1 components; do not rewrite them unless a spec genuinely requires it.
- Keep PROGRESS.md current. Log any blocker under "## BLOCKED" and continue; never guess
  destructively.
- Stop after Demo 2 works. Do not begin Day-3 work (dashboard, compaction, Docker).
