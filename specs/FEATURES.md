# MAESTRO — Feature Specifications

## F1: Multi-Agent Orchestration

**Priority:** Core

The orchestrator receives a user task, creates a plan, and delegates to sub-agents.

### Behavior
1. User submits task in natural language
2. Orchestrator analyzes task complexity
3. **Simple tasks** (single file edit, quick question) → orchestrator handles directly
4. **Complex tasks** (multiple files, code + tests, refactoring) → decomposed into sub-tasks
5. Sub-agents are spawned (up to `max_parallel` concurrent)
6. Each sub-agent gets: role, task description, relevant file contents
7. Sub-agents execute independently, using tools as needed
8. Results are compressed and returned to orchestrator
9. Orchestrator synthesizes results and presents to user

### Agent Decision Loop
Each agent (orchestrator and sub-agents) follows the same loop:
```
while True:
    response = llm.complete(messages, tools)

    if response.has_tool_calls:
        for tool_call in response.tool_calls:
            result = safety_layer.execute(tool_call)
            messages.append(tool_result)
        continue  # let LLM decide next action

    if response.wants_to_yield:
        return response.message_to_user

    # LLM decided no more tool calls needed
    return response.final_message
```

## F2: Smart Model Routing

**Priority:** Core

Different models for different roles to optimize cost/quality tradeoff.

### Configuration
- Orchestrator model: configurable, defaults to Claude Sonnet
- Sub-agent model: configurable, defaults to Claude Haiku
- Compaction model: configurable, defaults to Claude Haiku

### Provider Support
- Anthropic (Claude models) — primary
- OpenAI (GPT models) — secondary
- Groq (Llama models) — for fast/cheap sub-agents

Provider interface abstracted so adding new providers requires minimal code.

## F3: Context Engineering

**Priority:** Core

See [CONTEXT-ENGINE.md](./CONTEXT-ENGINE.md) for full specification.

### Features
- Automatic chat compaction at configurable threshold
- Tool-result trimming for large outputs
- Sub-agent result compression
- Context budget monitoring per agent

## F4: Real-Time Token Dashboard

**Priority:** Core

Terminal UI panel showing live cost information.

### Display
```
╭─ Token Usage ─────────────────────────────────╮
│ Session: 45,230 tokens ($0.42)                 │
│ Budget:  500,000 tokens ($5.00)                │
│ ██████████░░░░░░░░░░░░░░░░░░ 9.0%             │
│                                                 │
│ Active Agents:                                  │
│  ● Orchestrator  12,100 tok  $0.18              │
│  ● Coder         18,430 tok  $0.14              │
│  ● Tester        14,700 tok  $0.10              │
╰─────────────────────────────────────────────────╯
```

### Budget Warnings
- **70% threshold:** Yellow warning banner in UI
- **90% threshold:** Red warning, agents informed to wrap up
- **100% hard cap:** All API calls blocked, session summary shown

## F5: Safety-First Tool Execution

**Priority:** Core

See [SAFETY.md](./SAFETY.md) for full specification.

### Features
- Three-tier classification: safe / review / blocked
- Configurable allowlist and blocklist
- User approval flow with approve/deny/edit options
- Full audit log of all tool executions

## F6: Partial File Editing

**Priority:** Core

Agents can make surgical edits to files without rewriting entire contents.

### Tool: edit_file
```
Parameters:
  - file_path: string
  - old_text: string (exact text to find)
  - new_text: string (replacement text)
```

### Behavior
- Finds exact match of `old_text` in file
- Replaces with `new_text`
- Fails if `old_text` not found or matches multiple locations
- Shows diff to user if classified as "review"

## F7: Bash Execution

**Priority:** Core

Full shell command execution with safety classification.

### Tool: bash
```
Parameters:
  - command: string
  - working_directory: string (optional, defaults to project root)
  - timeout: int (optional, defaults to 30 seconds)
```

### Behavior
- Command passes through safety layer
- Executed in subprocess with timeout
- stdout and stderr captured
- Output trimmed if exceeding `max_tool_result_tokens`
- Non-zero exit code reported to agent

## F8: Docker Deployment

**Priority:** Core

One-command deployment for any machine.

### Files
- `Dockerfile` — Python image with all dependencies
- `docker-compose.yml` — service definition with volume mounts
- `.env.example` — template for API keys

### Usage
```bash
cp .env.example .env
# Edit .env with API key
docker compose up
```

### Volume Mounts
- Project directory mounted at `/workspace` (so agents can read/edit project files)
- Config file mounted at `/app/maestro.yaml`

## F9: Autonomous Agent Loop

**Priority:** Core (baseline requirement)

The agent autonomously decides whether to continue working or yield to user.

### Mechanism
- LLM response is parsed for tool calls
- If tool calls present → execute and continue loop
- If no tool calls and response is a message → yield to user
- Special `yield_to_user` tool available for explicit handoff
- Maximum iteration limit as safety net (configurable, default: 20)
