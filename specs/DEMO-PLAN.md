# MAESTRO — Live Demo Plan

## Presentation: 5-10 minutes

### Demo 1: Simple Task — Single Agent (1 min)

**Purpose:** Show baseline functionality — agent uses tools and yields.

```
User: "Read the README.md and tell me what this project does"
```

Expected flow:
- Orchestrator uses `read_file` (auto-approved, safe)
- Responds with summary
- Yields to user

**Demonstrates:** Tool usage, safety classification (safe = auto), yield behavior.

### Demo 2: Complex Task — Multi-Agent (3 min)

**Purpose:** Show the core multi-agent orchestration.

```
User: "Add a /health endpoint to app.py that returns JSON {status: ok, timestamp: <current time>}, and write a test for it"
```

Expected flow:
- Orchestrator analyzes task → decides to spawn sub-agents
- Terminal shows agent activity panel updating
- Coder sub-agent: proposes `edit_file` on app.py → user approves
- Tester sub-agent: proposes `write_file` test_health.py → user approves
- Both run in parallel (visible in dashboard)
- Orchestrator receives compressed results
- Orchestrator runs `bash: pytest` → user approves → tests pass
- Yields with summary

**Demonstrates:** Multi-agent orchestration, parallel execution, result synthesis, safety approval flow.

### Demo 3: Token Dashboard & Budget (1 min)

**Purpose:** Show cost control in action.

During demos 1 and 2, point out:
- Real-time token counter updating
- Per-agent cost breakdown
- Budget bar progression

Then set a very low hard cap and show what happens:
```yaml
budget:
  hard_cap_tokens: 1000
```

```
User: "Refactor the entire codebase"
```

Expected: Agent starts, hits cap quickly, session stops with budget summary.

**Demonstrates:** Token monitoring, budget warnings, hard cap enforcement.

### Demo 4: Safety Layer (1 min)

**Purpose:** Show command classification.

```
User: "Clean up temporary files"
```

If agent tries `rm -rf /tmp/*`:
- Safety layer blocks it
- Agent is informed and tries a safer alternative

**Demonstrates:** Blocked command rejection, agent adaptation.

### Demo 5: Context Engineering (1 min)

**Purpose:** Show chat compaction in action.

- Have a pre-prepared long session (or run through several tasks)
- Show the compaction happening: "Compacting conversation history..."
- Show that the agent still remembers key decisions after compaction
- Point to token savings in dashboard

**Demonstrates:** Chat compaction, context management.

## Architecture Walkthrough (2-3 min)

After live demos, briefly walk through:

1. **Architecture diagram** — show the component layout
2. **Config file** — show how everything is configurable
3. **Model routing** — explain the cost optimization
4. **What I would add next** — show awareness of limitations

## Prep Checklist

- [ ] Small Flask app in demo project directory
- [ ] `maestro.yaml` configured with reasonable budget
- [ ] `.env` with valid API key
- [ ] Docker image built and tested
- [ ] Low-budget config ready for Demo 3
- [ ] Pre-warmed session available if time is tight
- [ ] Architecture diagram printed or ready to show
