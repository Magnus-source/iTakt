# Day 4 — packaging + demonstrability (Docker, README, VG smoke test)

## Context
Days 1-3 are done: foundation, orchestration (parallel sub-agents + routing), and the
context engine + token dashboard + safety demos. Build ON these. Read the existing src/
first, then the specs as the contract: specs/FEATURES.md (F7 Bash, F8 Docker Deployment),
specs/ARCHITECTURE.md (deployment, config/.env), specs/CONFIG.md, specs/DEMO-PLAN.md.

## Scope — Day 4 only
Package the project and make every VG requirement provable with one command. Do NOT add new
agent features. Stop after the smoke test is green for all VG.1-9 and Docker is packaged.

## Build (in order)

### 1. VG smoke test (scripts/smoke.sh) — the centerpiece (HG-4 demonstrability)
A single script that exercises EACH VG requirement by running the real behavior and
asserting observable evidence, then prints one line per requirement and a final tally.
Output per check: `PASS VG.X <name>   run=<short-id>   <evidence pointer>`, ending with
`N passed / M failed`. Write a markdown report to `traces/smoke_report.md`. Cover:
- VG.1 parallel sub-agents — task that spawns 2+ sub-agents; assert overlapping wall-clock.
- VG.2 context compaction — trigger /compact; assert after-tokens < before-tokens and a trace file written.
- VG.3 cost monitoring + hard cap — set a low cap; assert the session STOPS at the cap.
- VG.4 harmful tool-call protection — attempt a blocked command; assert rejected before execution.
- VG.5 bash execution — run a safe bash command; assert real output.
- VG.6 partial file editing — edit one section; assert only that section changed (diff).
- VG.7 deployable packaging — assert Dockerfile + docker-compose.yml exist and are valid; if docker is available, run `docker build` and assert success, otherwise mark "files present, build unverified (no docker here)".
- VG.8 config/.env split — assert .env.example exists, .env is gitignored, and grep of traces/ for the API key value finds nothing.
- VG.9 yield vs guess — simple task; assert the model yields on its own (stop reason, not max-iter).
Checks that need the agent make real API calls (need a valid .env). Keep checks independent and idempotent.

### 2. Docker packaging (F8, VG.7)
- `Dockerfile` — Python image with all dependencies.
- `docker-compose.yml` — service definition; mount config at /app/itakt.yaml and a traces volume; read API key from .env.
- `.env.example` — verify it exists.
- If docker is available here, verify `docker build` succeeds; otherwise note that the user must run `docker compose up` to verify.

### 3. config/.env split + no-leak (VG.8)
- Confirm .env holds secrets only and is gitignored; .env.example is the template.
- Confirm no secret leak: grep traces/ for the API key value → nothing.

### 4. README finalize (VG.7)
- Quickstart matching reality: `cp .env.example .env`, add key, `docker compose up` (and the local `.venv` path). A short Architecture section pointing to the specs as the source of truth. Example commands for the 5 demos.

### 5. Demo prep + final verification
- Ensure the 5 DEMO-PLAN demos run in order (Flask demo app exists from Day 2; add a low-budget config preset for Demo 3 if missing).
- Run the full test suite and the smoke test; fix anything red.

## Definition of done (Day 4)
- `scripts/smoke.sh` prints PASS for all VG.1-9, `N passed / 0 failed`, writes traces/smoke_report.md.
- Dockerfile + docker-compose.yml exist and are valid (build verified if docker is available).
- grep of traces/ for the API key finds nothing.
- README quickstart works.
- pytest all green (Days 1-4).
- PROGRESS.md updated with the smoke-test output and the docker run command.

## Working discipline (mandatory)
- You are on branch day4-packaging (off day3-context-safety).
- Commit after each component.
- Do NOT use `source .venv/bin/activate` — invoke .venv/bin/python etc. directly.
- Build on existing components; do not rewrite them unless a spec requires it.
- Keep PROGRESS.md current; log blockers under "## BLOCKED" and continue.
- Stop after the smoke test is green and Docker is packaged. Day 5 is rehearsal — do not script it.
