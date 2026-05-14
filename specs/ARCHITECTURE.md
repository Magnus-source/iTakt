# MAESTRO — System Architecture

## Overview

MAESTRO is a terminal-based multi-agent coding system. A user submits a task in natural language. The system decomposes it, delegates to specialized sub-agents, and synthesizes the result — with full cost control and safety guarantees.

## High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│                   Terminal UI                     │
│            (Rich/Textual interface)               │
├─────────────────────────────────────────────────┤
│                  Main Agent                       │
│         (Orchestrator / Task Router)              │
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Planner  │ │  Coder   │ │    Reviewer       │ │
│  │Sub-Agent │ │Sub-Agent │ │   Sub-Agent       │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│                                                   │
├─────────────────────────────────────────────────┤
│              Context Engine                       │
│  (Compaction, Trimming, Window Management)        │
├─────────────────────────────────────────────────┤
│              Safety Layer                         │
│  (Command Classification, Approval Flow)          │
├─────────────────────────────────────────────────┤
│              Token Monitor                        │
│  (Cost Tracking, Budget Warnings, Hard Cap)       │
├─────────────────────────────────────────────────┤
│              Tool Registry                        │
│  (Bash, File Read, File Edit, File Write)         │
├─────────────────────────────────────────────────┤
│              Config Manager                       │
│  (YAML config + .env secrets)                     │
└─────────────────────────────────────────────────┘
```

## Component Details

### 1. Terminal UI

**Responsibility:** User interaction, displaying agent activity, token dashboard.

- Rich-based terminal interface with panels for:
  - Chat input/output (main conversation)
  - Agent activity feed (which sub-agents are running, their status)
  - Token usage dashboard (cost per agent, total, budget remaining)
- User can type natural language tasks
- Agent decides autonomously whether to make more tool calls or yield back to user
- User approval prompts for review-classified operations

### 2. Main Agent (Orchestrator)

**Responsibility:** Task understanding, decomposition, delegation, synthesis.

- Receives user task in natural language
- Uses the configured "orchestrator model" (e.g. Claude Sonnet)
- Creates a task plan: what needs to be done, in what order, with what dependencies
- Spawns sub-agents for independent tasks (parallel where possible)
- Collects sub-agent results via compressed summaries
- Synthesizes final result and presents to user
- Decides whether to continue (more tool calls) or yield to user

**LLM interaction pattern:**
- System prompt defines orchestrator role and available sub-agent types
- Tools available: spawn_sub_agent, synthesize_results, yield_to_user
- Plus all standard tools (bash, file operations) for simple tasks that don't need delegation

### 3. Sub-Agents

**Responsibility:** Focused execution of specific sub-tasks.

Each sub-agent is a separate LLM session with:
- Its own system prompt (role-specific)
- Its own context window (clean, focused)
- Access to the tool registry
- A scoped task description from the orchestrator

**Agent types:**

| Agent | Role | Typical Model |
|-------|------|---------------|
| Planner | Analyzes codebase, creates implementation plan | Orchestrator model |
| Coder | Writes/edits code based on plan | Fast model (Haiku) |
| Reviewer | Reviews changes for bugs, style, issues | Fast model (Haiku) |
| Tester | Runs tests, verifies changes work | Fast model (Haiku) |

**Parallel execution:**
- Sub-agents run concurrently via asyncio
- Each has independent context and token tracking
- Results are collected and compressed before returning to orchestrator
- Max parallel agents configurable (default: 3)

### 4. Context Engine

**Responsibility:** Managing context window usage across all agents.

See [CONTEXT-ENGINE.md](./CONTEXT-ENGINE.md) for full specification.

Key mechanisms:
- **Chat compaction** — when conversation exceeds threshold, older messages are summarized
- **Tool-result trimming** — large outputs are truncated with smart extraction
- **Sub-agent result compression** — sub-agent outputs are summarized before passing to orchestrator
- **Context budget per agent** — each agent has a max context allocation

### 5. Safety Layer

**Responsibility:** Preventing harmful tool execution.

See [SAFETY.md](./SAFETY.md) for full specification.

Classification system:
- **Safe:** Read-only operations → auto-execute
- **Review:** Write operations → require user approval
- **Blocked:** Destructive operations → rejected

### 6. Token Monitor

**Responsibility:** Real-time cost tracking and budget enforcement.

- Tracks input/output tokens per agent per API call
- Calculates cost based on model pricing in config
- Displays real-time dashboard in terminal UI
- Emits warnings at configurable thresholds (default: 70%, 90%)
- Enforces hard cap — refuses to make API calls that would exceed budget
- Per-session summary at end

### 7. Tool Registry

**Responsibility:** Providing tools that agents can use to interact with the filesystem and shell.

| Tool | Description | Safety Default |
|------|-------------|---------------|
| `bash` | Execute shell commands | Review |
| `read_file` | Read file contents | Safe |
| `write_file` | Create new file | Review |
| `edit_file` | Partial edit via search/replace | Review |
| `list_directory` | List files in directory | Safe |

All tools pass through the Safety Layer before execution.

### 8. Config Manager

**Responsibility:** Loading and validating configuration.

See [CONFIG.md](./CONFIG.md) for full specification.

Two sources:
- `maestro.yaml` — all settings (models, budgets, safety rules, etc.)
- `.env` — secrets only (API keys)

## Data Flow: A Typical Task

```
User: "Add a /health endpoint to the Flask app with tests"
  │
  ▼
Orchestrator receives task
  │
  ▼
Orchestrator analyzes: needs code changes + tests
  │
  ▼
Spawns sub-agents in parallel:
  ├── Coder: "Add /health endpoint to app.py returning {status: ok}"
  └── Tester: "Write pytest test for /health endpoint"
  │
  ▼ (concurrent execution)
  │
Coder proposes edit_file on app.py → Safety: Review → User approves
Tester proposes write_file test_health.py → Safety: Review → User approves
  │
  ▼
Orchestrator receives compressed results from both
  │
  ▼
Orchestrator runs bash: "pytest test_health.py" → Safety: Review → User approves
  │
  ▼
Tests pass → Orchestrator yields to user with summary
```

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ | Async support, rich ecosystem, LLM library support |
| LLM Client | Anthropic SDK + httpx | Primary provider + flexibility for others |
| Terminal UI | Rich + Prompt Toolkit | Beautiful output + interactive input |
| Async | asyncio | Native Python, parallel sub-agents |
| Config | PyYAML + pydantic | Parsing + validation |
| Deployment | Docker + docker-compose | One-command setup |
| Testing | pytest + pytest-asyncio | Standard Python testing |
