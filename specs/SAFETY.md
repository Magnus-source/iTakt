# iTakt — Safety Layer Specification

## Purpose

Prevent agents from executing harmful commands or making destructive file changes without explicit user approval.

## Command Classification

Every tool call passes through the safety layer before execution. Each call is classified into one of three categories:

### Safe (Auto-Execute)
Non-destructive, read-only operations. No user approval needed.

Default safe operations:
- `read_file` — any file read
- `list_directory` — listing directory contents
- `bash` commands matching safe patterns:
  - `ls`, `cat`, `head`, `tail`, `wc`, `find`, `grep`, `echo`, `pwd`, `which`, `env`, `date`
  - `python -c "..."` (read-only scripts)
  - `pytest`, `python -m pytest` (running tests)
  - `git status`, `git log`, `git diff`

### Review (User Approval Required)
Operations that modify state. Shown to user with details before execution.

Default review operations:
- `write_file` — creating new files
- `edit_file` — modifying existing files
- `bash` commands that aren't classified as safe or blocked:
  - `pip install`, `npm install`
  - `git add`, `git commit`
  - `python script.py` (running scripts)
  - `mkdir`, `touch`, `mv`, `cp`

### Blocked (Rejected)
Destructive or dangerous operations. Rejected with explanation, not executed.

Default blocked patterns:
- `rm -rf /` or `rm -rf ~` or similar broad destructive commands
- `format`, `mkfs`
- `dd if=` (disk operations)
- `chmod 777`
- `curl | sh`, `wget | sh` (piped execution from internet)
- `shutdown`, `reboot`
- Any command containing `sudo` (configurable)
- `>` redirecting to system files (`/etc/`, `/usr/`, etc.)

## Configuration

Safety rules are fully configurable in `itakt.yaml`:

```yaml
safety:
  # Override classification for specific commands
  allowlist:
    - pattern: "npm run build"
      classification: safe
    - pattern: "docker compose up"
      classification: safe

  blocklist:
    - pattern: "curl.*|.*sh"
      classification: blocked
      reason: "Piped remote execution not allowed"

  # Whether sudo commands are blocked
  block_sudo: true

  # Whether to require approval for file writes
  auto_approve_writes: false

  # Max file size for write operations (bytes)
  max_write_size: 1048576  # 1MB
```

## Approval Flow

When a tool call is classified as "review":

```
┌────────────────────────────────────────────┐
│ 🔍 Review Required                         │
│                                             │
│ Agent: Coder                                │
│ Tool:  edit_file                            │
│ File:  src/app.py                           │
│                                             │
│ Change:                                     │
│ - old: def index():                         │
│ + new: def index():                         │
│ +          return {"status": "ok"}          │
│                                             │
│ [A]pprove  [D]eny  [E]dit  [A]lways-approve│
└────────────────────────────────────────────┘
```

Options:
- **Approve** — execute this one time
- **Deny** — reject, agent is informed and can try alternative
- **Edit** — modify the command/content before approving
- **Always-approve** — add this pattern to session allowlist (not persisted to config)

## Sub-Agent Safety

Sub-agents inherit the same safety rules. A sub-agent cannot bypass approval by framing a command differently — the classification is based on the actual tool call, not the agent's description of it.

## Logging

All tool calls and their classifications are logged to the session log:
```
[2026-05-14 10:23:45] TOOL bash "pytest test_app.py" → SAFE → EXECUTED (exit 0)
[2026-05-14 10:23:52] TOOL edit_file "src/app.py" → REVIEW → APPROVED → EXECUTED
[2026-05-14 10:24:01] TOOL bash "rm -rf /tmp/*" → BLOCKED → REJECTED (broad destructive)
```
