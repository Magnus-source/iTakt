# iTakt — Product Pitch

**Multi-Agent Engineering Studio for Task Routing & Orchestration**

---

Imagine describing what you want to build — in plain text — and an entire engineering firm gets to work. Not a single AI struggling with everything in one context window, but a team of specialists working in parallel.

iTakt is a terminal-based coding agent in the same category as Claude Code and OpenAI Codex, but with a core idea that sets it apart: **tasks are broken down and delegated to specialized sub-agents** working in parallel — one plans, one codes, one reviews, one tests — while an orchestrator holds the big picture together.

## Why Multi-Agent?

Today's coding agents are powerful but fundamentally single-threaded in their thinking. One model, one context window, one chain of thought. When the task gets complex, the context fills up, the model loses track, and quality degrades.

iTakt takes a different approach: instead of asking one model to be everything, we give each role to a specialist. The orchestrator understands the task and creates a plan. The coder writes the implementation. The reviewer checks for issues. The tester verifies it works. Each agent has a focused context window with only what it needs.

## Dynamic Model Routing — Multi-Agent Without Multi-Dollar

The obvious concern with multi-agent is cost. iTakt solves this with dynamic model routing: the orchestrator selects model based on task complexity. Simple file read or a straightforward pytest? Haiku. Architecture decisions or complex refactoring? Sonnet. Every token spent where it matters most.

The result: you get a team at roughly the cost of a single generalist agent.

## Context Engineering — The Hidden Superpower

The real bottleneck in agentic coding isn't model intelligence — it's context management. iTakt implements:

- **Automatic chat compaction** — conversation history is periodically summarized to free up context space while preserving key decisions and outcomes
- **Tool-result trimming** — large outputs from bash commands or file reads are intelligently truncated, keeping the relevant parts
- **Sliding context windows** — each sub-agent gets a fresh, focused context with only the information relevant to its specific task
- **Smart result synthesis** — the orchestrator receives compressed summaries from sub-agents, not their full conversation histories

## Safety First

Every tool call is classified before execution:
- ✅ **Safe** — read operations, non-destructive commands → auto-approved
- ⚠️ **Review** — file writes, installs → shown to user for approval
- 🚫 **Blocked** — destructive commands (rm -rf, format, etc.) → rejected with explanation

All rules configurable via YAML. No surprises.

## Real-Time Cost Control

- Live token usage per agent displayed in terminal
- Budget warnings at configurable thresholds (default: 70% and 90%)
- Hard cap that stops execution — no infinite API loops, no surprise bills
- Per-session and per-agent cost breakdown

## Deployment

```bash
docker compose up
```

One command. Set your API key in `.env`. Everything else in `itakt.yaml`. Done.

## Feature Summary

| Feature | Description |
|---------|-------------|
| Multi-agent orchestration | Parallel sub-agents with role specialization |
| Smart model routing | Dynamic model selection based on task complexity |
| Context engineering | Chat compaction, result trimming, sliding windows |
| Token dashboard | Real-time cost tracking with warnings and hard cap |
| Safety layer | Command classification with allowlist/blocklist |
| Partial file editing | Search/replace surgical edits |
| Bash execution | Full shell access with safety checks |
| Docker deployment | One-command setup on any machine |
| YAML configuration | All settings in one file, secrets in .env |
