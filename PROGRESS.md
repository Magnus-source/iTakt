# iTakt — Progress Log

---

## Day 2 — Multi-Agent Orchestration

### Demo 2 Output

```
$ .venv/bin/python demo2_runner.py

============================================================
Demo 2: Multi-Agent Orchestration
============================================================
[agent] orchestrator (claude-sonnet-4-6) started
[agent] spawn coder-1 (claude-haiku-4-5-20251001) t+67.1s
[agent] spawn tester-1 (claude-haiku-4-5-20251001) t+67.1s   ← same timestamp = parallel start
[agent] return coder-1 tokens=5130 usd=$0.0041 t+71.9s
[agent] return tester-1 tokens=8742 usd=$0.0070 t+76.0s
[agent] 2 sub-agents ran in parallel (overlap confirmed)
============================================================
Orchestrator response:
Everything is done and all **3 tests pass**. Here's a summary:
  - demo/app.py: added /health endpoint (status: ok, timestamp: UTC ISO)
  - demo/test_health.py: 3 tests — status_code, status_field, timestamp_field
  - pytest: 3 passed in 0.11s
ctx 87,160 tok | $0.2636 | steps 23 | budget 17.4%
```

**Audit log confirms:**
```
coder-1  TOOL read_file  'demo/app.py'          → SAFE → EXECUTED   (23:42:39)
tester-1 TOOL read_file  'demo/app.py'          → SAFE → EXECUTED   (23:42:39)  ← same second
coder-1  TOOL write_file 'demo/app.py'          → SAFE → EXECUTED   (23:42:41)
tester-1 TOOL write_file 'demo/test_health.py'  → SAFE → EXECUTED   (23:42:42)
orchestrator TOOL bash   'pytest ...'           → SAFE → EXECUTED   (23:42:57)
```

---

### How parallelism works (asyncio.gather)

When the orchestrator's LLM response contains multiple `spawn_sub_agent` tool calls
in a single turn, `run_orchestrator()` collects them all and runs:

```python
gathered = await asyncio.gather(*[_spawn_one(tc) for tc in spawn_calls])
```

`asyncio.gather` submits every coroutine to the **same event loop** and switches
between them whenever one hits an `await` (i.e., every time a coroutine is waiting
for an HTTP response from Anthropic). This means:

1. Both `provider.complete()` calls go out over the network **simultaneously** —
   neither waits for the other to finish before starting.
2. While the first coroutine is blocked waiting for its API response, the event
   loop is free to advance the second coroutine's API call.
3. The two Anthropic API calls therefore overlap in wall-clock time, even though
   only one thread is used.

This is confirmed by the timestamps: both sub-agents print `t+67.1s` (same value
to one decimal place), meaning they started within 100 ms of each other even though
they each take ~5 s of API time.

A `asyncio.Semaphore(config.agents.max_parallel)` caps concurrency: if more
sub-agents are requested than `max_parallel` allows, the excess wait for a slot
before making their first API call.

**Why not threads?** `asyncio` is sufficient because the bottleneck is network I/O
(waiting for Anthropic). All Python code between `await` points runs on one thread,
so there is no GIL contention and no risk of race conditions on shared Python objects
(like the `TokenMonitor`).

---

### How model routing works

Model selection is fully config-driven — nothing is hardcoded:

| Agent | Config key | Default model |
|---|---|---|
| Orchestrator | `models.orchestrator.model` | `claude-sonnet-4-6` |
| Sub-agents | `models.sub_agents.model` | `claude-haiku-4-5-20251001` |
| Compaction | `models.compaction.model` | `claude-haiku-4-5-20251001` |

`run_orchestrator()` passes `config.models.orchestrator` to `provider.complete()`.
`run_sub_agent()` passes `config.models.sub_agents`. The provider client (`AnthropicProvider`)
uses whatever `ModelConfig.model` it receives — it has no knowledge of roles.

To swap models (e.g., use Opus for the orchestrator), only `itakt.yaml` needs to
change — no code changes required.

---

### Day 2 Components

#### 1. Sub-agent runner (`src/itakt/subagent.py`)
- `run_sub_agent(role, task, context, config, provider, monitor, safety, agent_name, t0)`
- Own clean message history — no shared state with the orchestrator's conversation
- Uses `config.models.sub_agents` (Haiku) — confirmed by `[agent] spawn ... (claude-haiku-...)` logs
- Imports `_content_to_dicts` from `agent.py` (reuses Night-1 helper)
- `compress_result()` formats the sub-agent's final output into the CONTEXT-ENGINE.md summary format
- Prints `[agent] spawn NAME MODEL t+Xs` on start, `[agent] return NAME tokens=N t+Xs` on finish

**Proving command:** `grep "spawn\|return" <(python demo2_runner.py 2>&1)` — shows overlapping timestamps

#### 2. Orchestrator (`src/itakt/orchestrator.py`)
- `run_orchestrator(task, config, provider, monitor, safety)`
- Splits each LLM turn's tool calls into `spawn_calls` (→ `asyncio.gather`) and `regular_calls` (→ sync safety layer)
- `SPAWN_SUB_AGENT_SCHEMA` — role enum, task, context (optional)
- `asyncio.Semaphore(config.agents.max_parallel)` caps parallel sub-agents
- Prints `N sub-agents ran in parallel (overlap confirmed)` after each batch

**Proving command:** `.venv/bin/python demo2_runner.py`

#### 3. REPL updated
- `repl.py` now calls `run_orchestrator()` instead of `run_agent()`
- `run_agent()` in `agent.py` preserved (still importable, not deleted)

#### 4. Demo project (`demo/app.py`)
- Minimal Flask app with `/` endpoint
- `/health` endpoint added by the coder sub-agent during Demo 2
- `demo/test_health.py` written by the tester sub-agent during Demo 2

**Proving command:** `.venv/bin/python -m pytest demo/test_health.py -v` → 3 passed

#### 5. Tests (`tests/test_orchestrator.py`) — 20 tests
- Schema validation for `spawn_sub_agent`
- `test_parallel_execution_is_concurrent` — asserts elapsed < 0.55s for two 0.3s coroutines
- `test_semaphore_caps_concurrency` — asserts Semaphore(1) serialises execution
- `test_gather_preserves_result_order` — asserts results arrive in call order
- Model routing — asserts sonnet for orchestrator, haiku for sub-agents
- Result compression — asserts format includes role, task, result, token count

**Proving command:** `.venv/bin/python -m pytest tests/ -q` → 81 passed

---

## Night 1 Progress

## Demo 1 Output (pasted per working-discipline requirement)

```
$ .venv/bin/python demo1_runner.py

[Demo 1] Task: 'Read the README.md and tell me what this project does'

Here's a summary of what **iTakt** is and does:

---

## 🎼 iTakt — A Multi-Agent AI Coding Assistant

**iTakt** is a terminal-based AI coding agent (similar to Claude Code or
OpenAI Codex), but with a distinctive architectural twist: instead of relying
on a single, smarter model, it uses a **multi-agent orchestration** approach
where tasks are broken down and delegated to **specialized sub-agents working
in parallel**.

The name comes from the Swedish phrase *"i takt"* (meaning *"in beat/in
time"*), reflecting the conductor/orchestra metaphor at the heart of the
design.

### ✨ Key Features

| Feature | Description |
|---|---|
| Multi-agent orchestration | Spawns parallel sub-agents (planner, coder, reviewer, tester) |
| Dynamic model routing | Cheap/fast models for simple tasks, powerful models for complex |
| Context engineering | Chat compaction, tool-result trimming, sliding context windows |
| Real-time token dashboard | Live cost tracking, budget warnings, hard spending cap |
| Safety-first execution | Commands classified safe/review/blocked before running |
| Surgical file editing | Search/replace edits, not full-file rewrites |
| Docker-packaged | One-command setup via docker compose up |
| Fully configurable | Models, budgets, safety rules in YAML config |

### 📌 Current Status
Project is in Specification & Architecture phase — specs in /specs are the blueprint.

ctx 3,833 tok | $0.0175 | steps 2 | budget 0.8%
```

**Audit log confirms:** `read_file 'README.md' → SAFE → EXECUTED` (auto-approved, no prompt)

---

## Test Run

```
$ .venv/bin/python -m pytest tests/ -v

============================= test session starts ==============================
platform darwin -- Python 3.14.0, pytest-9.0.3
61 passed in 1.13s
==============================
```

---

## Components Built

### 1. Project Scaffold
**Files:** `pyproject.toml`, `src/itakt/__init__.py`, `src/itakt/__main__.py`, `itakt.yaml`, `.env.example`

**Proving command:**
```
.venv/bin/python -m itakt
# Starts REPL (or shows config error if no API key)
```

**Notes:** Python 3.14 on this machine; `setuptools.build_meta` used (not
`setuptools.backends.legacy` which doesn't exist). SOCKS proxy in the shell
environment requires `httpx[socks]` — installed.

---

### 2. Config Manager
**File:** `src/itakt/config.py`

**What it does:**
- Pydantic v2 models for all config sections (models, budget, context, agents, safety, ui, logging)
- Minimal `.env` parser — sets env vars not already in environment
- `load_config()` searches `ITAKT_CONFIG` → `./itakt.yaml` → defaults
- Raises `RuntimeError` on missing `ANTHROPIC_API_KEY`

**Proving command:**
```python
from itakt.config import load_config
c = load_config()
print(c.models.orchestrator.model)   # claude-sonnet-4-6
print(c.budget.hard_cap_usd)         # 5.0
```

**Blocked:** None.

---

### 3. Provider Client
**File:** `src/itakt/provider.py`

**What it does:**
- `AnthropicProvider(api_key)` wraps `anthropic.AsyncAnthropic`
- `await provider.complete(system, messages, tools, model_cfg)` → `ProviderResponse`
- Returns `ProviderResponse.content` (list of SDK blocks), `.stop_reason`, `.usage` (input/output tokens)

**Proving command:**
```
.venv/bin/python demo1_runner.py   # makes real API call, prints response
```

**Blocked:** None. Model IDs updated from spec's `claude-sonnet-4-20250514` to
`claude-sonnet-4-6` (valid current API ID).

---

### 4. Token Monitor
**File:** `src/itakt/monitor.py`

**What it does:**
- `monitor.record(agent, input_tok, output_tok, provider, model)` — updates per-agent and session totals
- Cost calculation: `(tokens / 1_000_000) × price_per_million`
- `monitor.is_over_budget()` — checks both token cap and USD cap
- `monitor.status_line()` → `"ctx N tok | $X.XXXX | steps N | budget X.X%"`

**Proving command:**
```
# Output from Demo 1 run:
ctx 3,833 tok | $0.0175 | steps 2 | budget 0.8%
```

**Blocked:** None.

---

### 5. Tool Registry
**File:** `src/itakt/tools.py`

**What it does:**
- `read_file(path)` — reads file, returns content string or error
- `list_directory(path)` — sorted listing with `/` suffix for dirs
- `write_file(path, content)` — creates parent dirs, writes file
- `edit_file(path, old_text, new_text)` → `(msg, diff)` — exact match, fails if 0 or >1 occurrences, returns unified diff
- `bash(command, working_directory, timeout)` → `{stdout, stderr, exit_code}` — subprocess with configurable timeout, head_tail output trimming
- `ToolRegistry.execute(name, inputs)` — dispatches and formats result as string for LLM
- Anthropic-format `TOOL_SCHEMAS` list + `YIELD_TO_USER_SCHEMA`

**Proving command:**
```
.venv/bin/python -m pytest tests/test_tools.py -v   # 21 tests, all pass
```

Key test cases:
- `test_edit_file_not_found_text` — FAIL with "not found" when old_text absent
- `test_edit_file_multiple_matches` — FAIL with "multiple" when >1 matches
- `test_bash_timeout` — exit_code=-1, "timeout" in stdout

**Blocked:** None.

---

### 6. Safety Layer
**File:** `src/itakt/safety.py`

**What it does:**
- `SafetyLayer.classify(tool_name, tool_input)` → `(Classification, reason)`
  - `read_file`, `list_directory` → SAFE
  - `write_file`, `edit_file` → REVIEW (or SAFE if `auto_approve_writes=true`)
  - `bash` → checked in order: config blocklist → sudo → built-in blocked → config allowlist → built-in safe → REVIEW default
- `SafetyLayer.execute(tool_name, tool_input, agent_name)`:
  - SAFE → auto-execute
  - REVIEW → show details + `input("[A]pprove / [D]eny > ")` → execute or reject
  - BLOCKED → return `[BLOCKED] reason` string to agent
- Unified diff preview shown for `edit_file` review
- Every call appended to audit log: `[timestamp] agent TOOL name 'arg' → CLASS → OUTCOME`

**Proving command:**
```
.venv/bin/python -m pytest tests/test_safety.py -v   # 40 tests, all pass
cat itakt_audit.log   # after Demo 1: read_file → SAFE → EXECUTED
```

**Blocked:** None.

---

### 7. Single-Agent Loop
**File:** `src/itakt/agent.py`

**What it does:**
- `await run_agent(task, config, provider, monitor, safety)` → final response string
- Loop: `provider.complete()` → if `tool_use`: execute via safety layer, append results, continue → if `end_turn`: extract text
- `yield_to_user` tool handled as loop exit (returns message to caller)
- Budget guard at top of each iteration (`monitor.is_over_budget()`)
- Max-iteration cap (`config.agents.max_iterations`, default 20)
- Converts SDK content blocks to plain dicts for serializable message history

**Proving command:**
```
.venv/bin/python demo1_runner.py   # full loop: read_file (safe) → yield_to_user → printed
```

**Blocked:** None. Note: `prompt_toolkit`'s sync `prompt()` cannot be called
inside a running asyncio event loop — switched REPL to `session.prompt_async()`.

---

### 8. Minimal Terminal REPL
**Files:** `src/itakt/repl.py`, `src/itakt/__main__.py`

**What it does:**
- `python -m itakt` → prints banner → `PromptSession.prompt_async("> ")` loop
- Runs agent loop per task, prints result + status line
- `exit`/`quit`/`q`/Ctrl-C/EOF → clean exit
- History tracking via `InMemoryHistory`

**Proving command:**
```
.venv/bin/python -m itakt
# Shows banner, accepts tasks interactively
```

**Blocked:** Cannot test interactively via stdin pipe (prompt_toolkit requires TTY).
Tested via `demo1_runner.py` which calls `run_agent()` directly.

---

## What Was NOT Built (scope boundary)

Per the Night 1 spec:
- Multi-agent orchestration / sub-agents
- Rich token dashboard (panel UI)
- Chat compaction
- Docker
- Provider abstraction beyond Anthropic

All of the above are day 2+ work.

---

## Known Issues / Notes for Next Night

1. **Model IDs:** Spec uses `claude-sonnet-4-20250514` / `claude-haiku-4-20250414` — updated to `claude-sonnet-4-6` / `claude-haiku-4-5-20251001` which are the current valid IDs.
2. **SOCKS proxy:** The shell has `ALL_PROXY=socks5h://localhost:57124` which requires `httpx[socks]` — installed in `.venv`.
3. **prompt_toolkit + asyncio:** `pt_prompt()` (sync) calls `asyncio.run()` internally — incompatible with a running event loop. REPL uses `prompt_async()`. Safety approval prompt uses plain `input()`.
4. **TTY requirement:** The REPL's `prompt_async()` requires a real TTY. Headless testing via `demo1_runner.py` bypasses the REPL.
