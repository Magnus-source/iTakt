# iTakt

A terminal-based multi-agent AI coding assistant. Tasks are decomposed and delegated to
specialized sub-agents (planner, coder, reviewer, tester) running in parallel, while an
orchestrator synthesizes the results. *I takt* — Swedish for "in time", as in an orchestra
playing to the same beat.

> The best way to handle complex coding tasks isn't a smarter model but a smarter *workflow*.
> And with dynamic model routing, multi-agent doesn't mean multi-dollar.

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/Magnus-source/itakt.git
cd itakt

cp .env.example .env
# Edit .env — add your Anthropic API key:
#   ANTHROPIC_API_KEY=sk-ant-...

docker compose up
```

The REPL starts. Type a task and press Enter.

### Local (.venv)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cp .env.example .env
# Edit .env with your API key

.venv/bin/python -m itakt
```

---

## Core Features

| Feature | Description |
|---|---|
| Multi-agent orchestration | Orchestrator spawns parallel sub-agents; results synthesized |
| Dynamic model routing | Sonnet for orchestrator, Haiku for sub-agents — configurable |
| Context engineering | Auto chat compaction, tool-result trimming, `/compact` command |
| Token dashboard | Live cost per agent, budget warnings at 70%/90%, hard cap |
| Safety-first execution | All bash/file ops classified safe/review/blocked before running |
| Partial file editing | Surgical search/replace with unified diff, not full rewrites |
| Fully configurable | `itakt.yaml` for all settings, `.env` for secrets only |

---

## Demo Commands

All demos run without a TTY (non-interactive, auto-approve writes):

```bash
# Demo 1 — Simple task, single agent, read_file auto-approved
.venv/bin/python demo1_runner.py

# Demo 2 — Multi-agent: coder + tester spawned in parallel
.venv/bin/python demo2_runner.py

# Demo 3 — Token dashboard + budget hard cap (hard_cap_tokens=1000)
.venv/bin/python demo3_runner.py

# Demo 4 — Blocked-command safety classifier + agent adaptation
.venv/bin/python demo4_runner.py

# Demo 5 — Chat compaction: before→after tokens, trace written, agent works after
.venv/bin/python demo5_runner.py
```

Interactive REPL (requires a TTY):

```bash
.venv/bin/python -m itakt
# > Read the README.md and tell me what this project does
# > /compact          (force context compaction)
# > exit
```

---

## VG Smoke Test

Run all 9 VG requirements as live assertions:

```bash
.venv/bin/python scripts/smoke_test.py
# Prints PASS/FAIL per VG.1-9
# Writes traces/smoke_report.md
```

---

## Configuration

Copy `config/itakt.example.yaml` to `itakt.yaml` and customize. All settings live in the
YAML; secrets (API keys) live exclusively in `.env`.

Key config sections:

```yaml
models:
  orchestrator:   { model: claude-sonnet-4-6 }   # complex decisions
  sub_agents:     { model: claude-haiku-4-5-20251001 }  # fast execution

budget:
  hard_cap_tokens: 500000   # session stops here
  hard_cap_usd: 5.00

safety:
  block_sudo: true
  auto_approve_writes: false   # require approval for file writes
```

---

## Architecture

The specs directory is the source of truth — code was generated from these:

```
specs/
  ARCHITECTURE.md      System design & component diagram
  FEATURES.md          Feature specifications (F1-F9)
  CONTEXT-ENGINE.md    Compaction + trimming + sub-agent compression
  SAFETY.md            Three-tier classification (safe/review/blocked)
  CONFIG.md            All configuration keys and defaults
  DEMO-PLAN.md         Live demo script (Demos 1-5)
```

Component stack (bottom-up):

```
Config Manager   → loads itakt.yaml + .env, validates with pydantic
Provider Client  → async Anthropic SDK wrapper, returns (content, usage)
Token Monitor    → per-agent token + cost tracking, budget warnings
Tool Registry    → read_file, list_directory, write_file, edit_file, bash
Safety Layer     → classify → auto/approve/block; audit log
Context Engine   → chat compaction (Layer 1), tool-result trimming (Layer 2)
Sub-Agent Runner → clean context, role prompt, Haiku model, compress_result()
Orchestrator     → asyncio.gather parallel spawning, yield_to_user, synthesis
Token Dashboard  → Rich panel with budget bar + per-agent breakdown
REPL             → prompt-toolkit async session, /compact command
```

---

## Status

| Phase | Status |
|---|---|
| Specs & architecture | Complete |
| Foundation (config, provider, tools, safety, agent loop, REPL) | Complete |
| Orchestration (parallel sub-agents, model routing, synthesis) | Complete |
| Context engine (compaction, trimming, dashboard, hard cap) | Complete |
| Packaging (Docker, smoke test) | Complete |
