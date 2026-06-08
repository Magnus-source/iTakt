"""Orchestrator — multi-agent decision loop with parallel sub-agent spawning."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from .agent import _content_to_dicts
from .compaction import compact_messages, estimate_tokens, should_compact
from .config import Config
from .dashboard import check_and_print_warnings, budget_summary
from .monitor import TokenMonitor
from .provider import AnthropicProvider
from .safety import SafetyLayer
from .session_writer import (
    event_agent_spawn, event_agent_return, event_compaction,
    event_budget_cap, event_budget_warning, event_tool_call,
    record_session_state, reset_session,
)
from .subagent import run_sub_agent
from .tools import TOOL_SCHEMAS, YIELD_TO_USER_SCHEMA

# ---------------------------------------------------------------------------
# spawn_sub_agent tool schema (orchestrator-only)
# ---------------------------------------------------------------------------

SPAWN_SUB_AGENT_SCHEMA: dict = {
    "name": "spawn_sub_agent",
    "description": (
        "Spawn a focused sub-agent to work on a specific sub-task. "
        "For complex tasks that need both code changes AND tests, call spawn_sub_agent "
        "multiple times in a SINGLE response — they run in parallel. "
        "Simple tasks (single file read, quick question, one small change) can be "
        "handled directly with the standard tools instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": ["planner", "coder", "reviewer", "tester"],
                "description": "Specialization of the sub-agent.",
            },
            "task": {
                "type": "string",
                "description": "Focused, self-contained task description for this sub-agent.",
            },
            "context": {
                "type": "string",
                "description": (
                    "Relevant context the sub-agent needs: file contents, "
                    "requirements, existing code snippets."
                ),
            },
        },
        "required": ["role", "task"],
    },
}

ORCHESTRATOR_SYSTEM = """\
You are iTakt, an AI orchestrator that manages a team of specialised sub-agents \
for software engineering tasks.

ROUTING RULES:
- SIMPLE task (read a file, answer a question, one small change) → handle directly \
with your standard tools (read_file, list_directory, write_file, edit_file, bash).
- COMPLEX task (code changes + tests, multiple files, multi-step refactor) → \
decompose and delegate. Call spawn_sub_agent multiple times in a SINGLE response \
so the agents run IN PARALLEL. Never spawn sequentially when parallel is possible.

Sub-agent roles: planner (analyse/plan), coder (write/edit code), \
reviewer (review changes), tester (write/run tests).

After all sub-agents complete, synthesise their results, run any needed verification \
(e.g. pytest), then call yield_to_user with a clear summary.
Always call yield_to_user when done."""

ORCHESTRATOR_TOOLS = TOOL_SCHEMAS + [SPAWN_SUB_AGENT_SCHEMA, YIELD_TO_USER_SCHEMA]


# ---------------------------------------------------------------------------
# Message-sequence helper
# ---------------------------------------------------------------------------

def _normalize_for_continuation(messages: list[dict]) -> None:
    """Ensure the last assistant message is safe to continue after.

    When the loop exits via ``yield_to_user``, the final assistant message
    contains a ``tool_use`` block.  The Anthropic API requires a ``tool_result``
    before the next user message, so we convert the ``yield_to_user`` block into
    a plain text block in-place.  All other content blocks are left untouched.
    """
    if not messages or messages[-1].get("role") != "assistant":
        return
    content = messages[-1].get("content", [])
    if not isinstance(content, list):
        return
    new_content = []
    for block in content:
        if (isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "yield_to_user"):
            msg = block.get("input", {}).get("message", "")
            if msg:
                new_content.append({"type": "text", "text": msg})
            # else: drop the empty block — the text was already returned as reply
        else:
            new_content.append(block)
    messages[-1]["content"] = new_content


# ---------------------------------------------------------------------------
# Core loop (extracted so ConversationAgent can reuse it)
# ---------------------------------------------------------------------------

async def _orchestrator_loop(
    messages: list[dict],
    config: Config,
    provider: AnthropicProvider,
    monitor: TokenMonitor,
    safety: SafetyLayer,
    semaphore: asyncio.Semaphore,
    role_counters: dict[str, int],
    t0: float,
    last_compacted_at: int = -2,
) -> tuple[str, int]:
    """Run the decision loop on *messages* (mutated in-place).

    Returns ``(reply_text, last_compacted_at)`` so the caller can persist
    ``last_compacted_at`` across turns.
    """
    model_cfg = config.models.orchestrator
    agent_name = "orchestrator"

    for iteration in range(config.agents.max_iterations):
        if check_and_print_warnings(monitor):
            try:
                event_budget_cap(monitor.total_tokens(), monitor.total_cost())
            except Exception:
                pass
            return budget_summary(monitor), last_compacted_at

        # Auto-compact when messages history exceeds threshold,
        # but never on the iteration immediately following a compaction.
        if (iteration > 0
                and iteration != last_compacted_at + 1
                and should_compact(messages, config.context)):
            before_tok = estimate_tokens(messages)
            messages[:] = await compact_messages(
                messages=messages,
                system=ORCHESTRATOR_SYSTEM,
                context_cfg=config.context,
                provider=provider,
                model_cfg=config.models.compaction,
                agent_name=agent_name,
                traces_dir="traces",
            )
            last_compacted_at = iteration
            try:
                event_compaction(agent_name, before_tok, estimate_tokens(messages), "traces/")
            except Exception:
                pass

        response = await provider.complete(
            system=ORCHESTRATOR_SYSTEM,
            messages=messages,
            tools=ORCHESTRATOR_TOOLS,
            model_cfg=model_cfg,
        )

        monitor.record(
            agent_name=agent_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider=model_cfg.provider,
            model=model_cfg.model,
        )
        try:
            record_session_state(
                total_tokens=monitor.total_tokens(),
                total_cost=monitor.total_cost(),
                budget_tokens=monitor._budget.hard_cap_tokens,
                budget_usd=monitor._budget.hard_cap_usd,
                agents={k: {"input": v.input_tokens, "output": v.output_tokens,
                            "cost": v.cost_usd, "calls": v.calls}
                        for k, v in monitor.agents_usage().items()},
                steps=monitor._steps,
            )
        except Exception:
            pass

        messages.append({"role": "assistant", "content": _content_to_dicts(response.content)})

        # No more tool calls — extract text response
        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    return block.text, last_compacted_at
            return "(orchestrator finished with no text)", last_compacted_at

        # Scan for yield_to_user (always handled first)
        for block in response.content:
            if block.type == "tool_use" and block.name == "yield_to_user":
                return block.input.get("message", "(no message)"), last_compacted_at

        # Partition all tool calls
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        spawn_calls = [tc for tc in tool_calls if tc.name == "spawn_sub_agent"]
        regular_calls = [tc for tc in tool_calls if tc.name != "spawn_sub_agent"]

        # Collect results keyed by tool_use_id (preserve order later)
        results: dict[str, str] = {}

        # Regular tools: sequential sync execution
        for tc in regular_calls:
            res = safety.execute(tc.name, tc.input, agent_name)
            results[tc.id] = res
            try:
                cls_val = safety.classify(tc.name, tc.input)[0].value
                outcome = "BLOCKED" if res.startswith("[BLOCKED]") else "EXECUTED"
                event_tool_call(agent_name, tc.name, cls_val, outcome,
                                str(tc.input)[:60])
            except Exception:
                pass

        # spawn_sub_agent: parallel async execution
        if spawn_calls:
            async def _spawn_one(tc: object) -> tuple[str, str]:
                role: str = tc.input["role"]
                role_counters[role] += 1
                sub_name = f"{role}-{role_counters[role]}"
                async with semaphore:
                    summary = await run_sub_agent(
                        role=role,
                        task=tc.input["task"],
                        context=tc.input.get("context", ""),
                        config=config,
                        provider=provider,
                        monitor=monitor,
                        safety=safety,
                        agent_name=sub_name,
                        t0=t0,
                    )
                return tc.id, summary

            gathered = await asyncio.gather(*[_spawn_one(tc) for tc in spawn_calls])
            for tool_id, summary in gathered:
                results[tool_id] = summary

            n = len(spawn_calls)
            print(
                f"[agent] {n} sub-agent{'s' if n > 1 else ''} ran in parallel"
                + (" (overlap confirmed)" if n > 1 else "")
            )

        # Build ordered tool results for the next LLM turn
        ordered: list[dict] = [
            {"type": "tool_result", "tool_use_id": tc.id, "content": results[tc.id]}
            for tc in tool_calls
            if tc.id in results
        ]
        messages.append({"role": "user", "content": ordered})

    return "[iTakt] Max iterations reached.", last_compacted_at


# ---------------------------------------------------------------------------
# Public function API — reset-per-task (unchanged external behaviour)
# ---------------------------------------------------------------------------

async def run_orchestrator(
    task: str,
    config: Config,
    provider: AnthropicProvider,
    monitor: TokenMonitor,
    safety: SafetyLayer,
) -> str:
    """Fresh-per-task orchestrator run.  Demo runners and smoke test use this."""
    messages: list[dict] = [{"role": "user", "content": task}]
    model_cfg = config.models.orchestrator
    semaphore = asyncio.Semaphore(config.agents.max_parallel)
    role_counters: dict[str, int] = defaultdict(int)
    t0 = time.monotonic()

    print(f"[agent] orchestrator ({model_cfg.model}) started")
    try:
        reset_session()
        event_agent_spawn("orchestrator", model_cfg.model, "orchestrator", 0.0)
    except Exception:
        pass

    reply, _ = await _orchestrator_loop(
        messages, config, provider, monitor, safety,
        semaphore, role_counters, t0,
    )
    return reply


# ---------------------------------------------------------------------------
# Stateful class API — persistent history across REPL turns
# ---------------------------------------------------------------------------

class ConversationAgent:
    """Maintains message history across multiple REPL turns.

    ``run_turn(user_input)`` appends the user message to the existing history
    and runs the decision loop, so the agent remembers previous exchanges.

    ``run_orchestrator`` (the function above) always resets per task and is
    unaffected by this class.
    """

    def __init__(
        self,
        config: Config,
        provider: AnthropicProvider,
        monitor: TokenMonitor,
        safety: SafetyLayer,
    ) -> None:
        self._config = config
        self._provider = provider
        self._monitor = monitor
        self._safety = safety
        self.messages: list[dict] = []
        self._semaphore = asyncio.Semaphore(config.agents.max_parallel)
        self._role_counters: dict[str, int] = defaultdict(int)
        self._t0 = time.monotonic()
        self._last_compacted_at: int = -2
        self._started: bool = False

    async def run_turn(self, user_input: str) -> str:
        """Append *user_input* to history, run one turn, return the reply.

        On the first call, initialises the session (``reset_session`` +
        ``event_agent_spawn``).  Subsequent calls reuse the same history.
        """
        # First-turn session initialisation
        if not self._started:
            self._started = True
            model = self._config.models.orchestrator.model
            print(f"[agent] orchestrator ({model}) started")
            try:
                reset_session()
                event_agent_spawn("orchestrator", model, "orchestrator", 0.0)
            except Exception:
                pass

        self.messages.append({"role": "user", "content": user_input})

        reply, self._last_compacted_at = await _orchestrator_loop(
            self.messages,
            self._config, self._provider, self._monitor, self._safety,
            self._semaphore, self._role_counters, self._t0,
            self._last_compacted_at,
        )

        # If the loop returned via yield_to_user, the last assistant message
        # contains a tool_use block.  Convert it to text so the next user
        # message is always a valid continuation (Anthropic API requires
        # tool_result before a new user turn, not a bare user message).
        _normalize_for_continuation(self.messages)

        # Edge case: budget_cap fires before any API call (messages still ends
        # with the user message we just appended).  Add the reply as an
        # assistant message so the sequence stays valid.
        if self.messages and self.messages[-1].get("role") != "assistant":
            self.messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": reply}],
            })

        return reply
