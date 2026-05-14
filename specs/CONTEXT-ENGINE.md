# iTakt — Context Engine Specification

## Problem

LLM context windows are finite. In an agentic coding session, context fills up fast:
- Conversation history grows with every exchange
- Tool results (file contents, bash output) can be enormous
- Multi-agent systems multiply the problem

Without context management, agents lose track of earlier decisions, repeat work, or hit token limits and crash.

## Solution: Three-Layer Context Management

### Layer 1: Chat Compaction

**Trigger:** When conversation history exceeds a configurable threshold (default: 60% of context window).

**Mechanism:**
1. Take all messages except the system prompt and the last N exchanges (default: 4)
2. Send them to the LLM with a compaction prompt: "Summarize this conversation, preserving all key decisions, file changes made, current task status, and any unresolved issues"
3. Replace the old messages with a single `[Compacted Summary]` message
4. Continue the conversation with the summary + recent messages

**Configurable:**
- `compaction_threshold`: percentage of context window that triggers compaction (default: 0.6)
- `preserve_recent`: number of recent exchanges to keep verbatim (default: 4)

### Layer 2: Tool-Result Trimming

**Problem:** A `read_file` on a 500-line file or a `bash` command with verbose output can consume thousands of tokens for information the agent only partially needs.

**Mechanism:**
- **File reads:** If output exceeds `max_tool_result_tokens` (default: 2000 tokens), truncate with:
  - First 60% of token budget → beginning of output
  - Last 30% of token budget → end of output
  - Middle 10% → "[... truncated {N} lines ...]"
- **Bash output:** Same truncation strategy
- **Error output:** Never truncated (errors are always fully preserved)

**Configurable:**
- `max_tool_result_tokens`: max tokens per tool result (default: 2000)
- `truncation_strategy`: "head_tail" (default) or "head_only"

### Layer 3: Sub-Agent Result Compression

**Problem:** A sub-agent might have a 20-message conversation with tool calls to complete its task. Passing all of this back to the orchestrator would flood its context.

**Mechanism:**
1. When a sub-agent completes its task, its full conversation is summarized
2. Summary includes: what was done, what files were changed/created, any issues found, final status
3. Only the compressed summary is passed to the orchestrator
4. Full sub-agent logs are preserved in the session log (for debugging) but not in the orchestrator's context

**Summary format returned to orchestrator:**
```
Sub-Agent: {role} | Status: {success/failure} | Tokens used: {count}
Task: {original task description}
Result: {2-3 sentence summary of what was accomplished}
Files modified: {list of files touched}
Issues: {any problems or warnings}
```

## Context Budget Allocation

Each agent session has a context budget derived from the model's max context window:

```
Total context window (e.g. 200k tokens)
├── System prompt: ~500 tokens (reserved)
├── Compacted history: up to 40% of remaining
├── Recent messages: up to 30% of remaining
├── Tool results: up to 20% of remaining
└── Response buffer: 10% reserved for model output
```

## Monitoring

The context engine exposes metrics to the Token Monitor:
- Current context usage per agent (tokens)
- Number of compactions performed
- Tokens saved by trimming
- Tokens saved by sub-agent compression

These are displayed in the terminal dashboard.
