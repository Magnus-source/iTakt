# iTakt

A terminal-based AI coding agent in the same category as Claude Code and OpenAI Codex but with a fundamentally different approach: tasks are decomposed and delegated to specialized sub-agents working in parallel, while an orchestrator/conductor keeps the orchestra playing to the same beat, i takt in Swedish, and synthesizes the results.

> The best way to handle complex coding tasks isn't a smarter model but it's a smarter *workflow*. And with dynamic model routing, multi-agent doesn't mean multi-dollar.

---

## Core Features

> **Multi-agent orchestration** a main agent automatically spawns parallel sub-agents and synthesizes their results. Each agent has a role: planner, coder, reviewer, tester.
> **Dynamic model routing** the orchestrator selects model based on task complexity. Simple file read or a straightforward pytest? Haiku. Architecture decisions or complex refactoring? Sonnet. Every token spent where it matters most.
> **Context engineering** automatic chat compaction, tool-result trimming, and sliding context windows so agents never drown in their own history.
> **Real-time token dashboard** live cost tracking per agent, budget warnings at configurable thresholds, and a hard cap that stops execution before your wallet bleeds.
> **Safety-first tool execution** all bash commands and file operations are classified (safe/review/blocked) before execution, with allowlist/blocklist in config.
> **Partial file editing** surgical edits via search/replace, not full-file rewrites.
> **Bash execution** full shell access with safety classification.
> **Docker-packaged** `docker compose up`, set your API key in `.env`, done. Runs on any machine.
> **Fully configurable** model selection, token budgets, safety rules, all in a YAML config. No hardcoded values.

## Project Philosophy

This project follows a **spec-first development approach**, as advocated by the course methodology:

> *"Your real programming language is `.md` in this assignment. Not python."*

The `/specs` directory contains the architecture documents, feature specifications, and test plans that serve as the blueprint for the entire system. The code is generated from these specs, the planning *is* the product.

## Repository Structure

```
itakt/
├── README.md                 # This file
├── specs/                    # Architecture & feature specifications
│   ├── ARCHITECTURE.md       # System architecture & component design
│   ├── FEATURES.md           # Detailed feature specifications
│   ├── CONTEXT-ENGINE.md     # Context engineering deep-dive
│   ├── SAFETY.md             # Safety layer specification
│   ├── CONFIG.md             # Configuration specification
│   └── DEMO-PLAN.md          # Live demonstration script
├── docs/                     # Supporting documentation
│   └── PITCH.md              # Product pitch
├── config/                   # Configuration templates
│   └── itakt.example.yaml    # Example configuration file
├── .env.example              # Environment variable template
├── Dockerfile                # Container definition
├── docker-compose.yml        # One-command deployment
└── src/                      # Source code (generated from specs)
    └── ...
```

## Quick Start (Coming Soon)

```bash
# Clone the repo
git clone https://github.com/Magnus-source/itakt.git
cd itakt

# Configure
cp .env.example .env
# Edit .env with your API key(s)

# Run
docker compose up
```

## Status

**Phase: Specification & Architecture**

The project is currently in the planning phase. Specs are being finalized before code generation begins.

| Phase | Status |
|-------|--------|
| Product pitch | Complete |
| Architecture spec | In progress |
| Feature specs | In progress |
| Code generation | Upcoming |
| Testing & demo prep | Upcoming |
