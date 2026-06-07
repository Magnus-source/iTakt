--- PLAN: Day 5 — hardening + simple web GUI ---

GUARDRAIL (applies to everything): Do NOT weaken or remove any existing passing test or smoke check. The smoke test must still report 9/9 at the end. These are additive/strengthening changes — build on existing code, do not rewrite working modules.

## Phase 1 — fix the weaknesses found in testing

### 1.1 Safety classifier — destructive ops wrapped in a safe-prefixed command (the real gap)
Problem observed: `find . -type d -name "__pycache__" -exec rm -rf {} +` was classified SAFE and executed, because the command starts with `find` (a safe prefix) so the embedded `rm -rf` bypassed the blocklist.
Fix in `src/itakt/safety.py`: check destructive/blocklist patterns against the WHOLE command string FIRST, before any safe-prefix match. A destructive operation appearing anywhere — `rm -rf`, `chmod 777`, `dd if=`, `mkfs`, `> /etc`, `| sh`, including when wrapped via `-exec`, `xargs`, `;`, `&&`, `|` — must never be auto-SAFE. Catastrophic forms (`rm -rf /`, `~`, `/tmp` root, `dd`, `mkfs`, `chmod 777`, `curl|sh`, `sudo`) → BLOCKED; other scoped destructive ops (e.g. a scoped `rm -rf` via find) → REVIEW (require approval), not SAFE.
Add tests to `tests/test_safety.py`: `find . -name x -exec rm -rf {} +` → NOT safe; `ls && rm -rf /tmp/x` → NOT safe; `git ls-files | xargs rm -rf` → NOT safe. Keep genuinely-safe ones safe: `git status`, `pytest`, `ls -la`, and `find . -name "*.py"` (a find with NO destructive -exec) → still safe.

### 1.2 Compaction — guard against immediate re-compaction
Problem: compaction can leave tokens still above the threshold, and `should_compact` runs every iteration, so it could re-compact every turn. Add a guard so compaction does not fire two iterations in a row / does not re-fire until the history has grown again since the last compaction. Keep it simple. Add a test: a history that compacts but stays above threshold does NOT immediately compact again on the next check.

### 1.3 Minor: `demo/app.py` uses `datetime.utcnow()` (DeprecationWarning on 3.14)
Change to `datetime.now(datetime.UTC)`; update the demo test if needed so it still passes.

After Phase 1: run `.venv/bin/python -m pytest` (all green, incl. new tests) AND `bash scripts/smoke.sh` (still 9 passed / 0 failed). Fix any regression before Phase 2. Commit.

## Phase 2 — strict, simple web dashboard (observability, read-only)
A minimal local web dashboard (Flask is already a dependency) visualising a live iTakt session. One page, no build tooling, no external CDNs.
- New module `src/itakt/web_dashboard.py` (separate from the existing Rich terminal `dashboard.py`). Serves on 127.0.0.1, configurable port (default 8787).
- Shows: session totals (tokens, cost, budget bar with %), per-agent breakdown (orchestrator + sub-agents: role, model, tokens, cost), and a live event stream (agent spawned/returned, tool calls + safety classification, compaction events) so parallel agents are visible.
- Decoupled data source (low risk): the orchestrator/monitor writes session state + an append-only event log to `traces/session_state.json` and `traces/events.jsonl` as events happen. Wrap ALL such writes in try/except so they can NEVER break the agent. The dashboard reads those files and auto-refreshes every ~1.5s with plain JS polling — no websockets, no frameworks.
- Strict/simple styling: one self-contained HTML page, minimal clean CSS.
- Launch: `python -m itakt.web_dashboard` (and a `scripts/dashboard.sh` wrapper). Document it in the README under "Web dashboard (optional)".
- Add a basic test that the server starts and renders an empty-state page without crashing.
- The dashboard must be entirely additive — it must not change agent behaviour or break any existing test or the smoke test.

After Phase 2: run the full test suite + smoke test again; confirm 9/9 and all tests green. Update PROGRESS.md describing both phases (safety classifier now defense-in-depth, compaction guard, web dashboard).

## Working discipline
- Branch `day5-hardening-gui` off `day4-packaging`; commit per change; keep PROGRESS.md current; log blockers under "## BLOCKED"; don't use `source`; build on existing code.
- Acceptance gate for the whole task: smoke test reports 9/9 at the end.
