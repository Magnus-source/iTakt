# MAESTRO — Configuration Specification

## Principles

1. **All settings in config file** — no hardcoded values
2. **All secrets in environment variables** — never in config file
3. **Sensible defaults** — works out of the box with just an API key

## Environment Variables (.env)

```bash
# Required: at least one provider API key
ANTHROPIC_API_KEY=sk-ant-...

# Optional: additional providers
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# Optional: override config file path
MAESTRO_CONFIG=./maestro.yaml
```

## Configuration File (maestro.yaml)

```yaml
# ============================================
# MAESTRO Configuration
# ============================================

# --- Model Configuration ---
models:
  orchestrator:
    provider: anthropic
    model: claude-sonnet-4-20250514
    max_tokens: 4096
    temperature: 0.3

  sub_agents:
    provider: anthropic
    model: claude-haiku-4-20250414
    max_tokens: 2048
    temperature: 0.2

  compaction:
    # Model used for chat compaction summaries
    # Using a cheap/fast model here saves money
    provider: anthropic
    model: claude-haiku-4-20250414
    max_tokens: 1024
    temperature: 0.1

# --- Token Budget ---
budget:
  # Hard cap: stop all execution when reached
  hard_cap_tokens: 500000
  hard_cap_usd: 5.00

  # Warning thresholds (percentage of hard cap)
  warning_thresholds:
    - 0.70  # 70% — yellow warning
    - 0.90  # 90% — red warning

  # Cost per million tokens (for dashboard display)
  pricing:
    anthropic:
      claude-sonnet-4-20250514:
        input: 3.00
        output: 15.00
      claude-haiku-4-20250414:
        input: 0.80
        output: 4.00

# --- Context Engineering ---
context:
  # Chat compaction trigger (fraction of context window)
  compaction_threshold: 0.6

  # Recent exchanges to preserve during compaction
  preserve_recent: 4

  # Max tokens per tool result before trimming
  max_tool_result_tokens: 2000

  # Trimming strategy: head_tail or head_only
  truncation_strategy: head_tail

# --- Sub-Agents ---
agents:
  # Max concurrent sub-agents
  max_parallel: 3

  # Available agent roles
  roles:
    - planner
    - coder
    - reviewer
    - tester

# --- Safety ---
safety:
  block_sudo: true
  auto_approve_writes: false
  max_write_size: 1048576  # 1MB

  allowlist:
    - pattern: "pytest"
      classification: safe
    - pattern: "python -m pytest"
      classification: safe
    - pattern: "git status"
      classification: safe
    - pattern: "git diff"
      classification: safe

  blocklist:
    - pattern: "rm -rf /"
      classification: blocked
      reason: "Root deletion not allowed"
    - pattern: "rm -rf ~"
      classification: blocked
      reason: "Home directory deletion not allowed"

# --- UI ---
ui:
  # Show agent activity panel
  show_agent_activity: true

  # Show token dashboard
  show_token_dashboard: true

  # Color theme
  theme: dark

# --- Logging ---
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  file: ./maestro.log
  log_tool_calls: true
  log_token_usage: true
```

## .env.example

Shipped with the repository:

```bash
# MAESTRO Environment Variables
# Copy this file to .env and fill in your API key(s)

# Required: Anthropic API key (for Claude models)
ANTHROPIC_API_KEY=your-key-here

# Optional: OpenAI API key
# OPENAI_API_KEY=your-key-here

# Optional: Groq API key (for fast Llama models)
# GROQ_API_KEY=your-key-here
```

## Config Validation

On startup, MAESTRO validates the configuration:
1. Check that at least one API key is set in environment
2. Validate YAML structure against schema
3. Verify referenced models match the configured provider
4. Warn if budget seems unusually high or low
5. Apply defaults for any missing optional fields
