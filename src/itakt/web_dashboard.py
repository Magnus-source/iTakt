"""Web dashboard — minimal Flask server that reads session_state.json + events.jsonl.

Launch:  python -m itakt.web_dashboard [--port 8787]
Access:  http://127.0.0.1:8787/

Entirely additive: reads traces/ files written by session_writer.py.
Never touches agent code, never raises inside the agent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flask import Flask, Response, jsonify

app = Flask(__name__)

_STATE = Path("traces/session_state.json")
_EVENTS = Path("traces/events.jsonl")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text())
    except Exception:
        return {}


def _load_events(last_n: int = 200) -> list[dict]:
    try:
        lines = _EVENTS.read_text().splitlines()
        return [json.loads(l) for l in lines[-last_n:] if l.strip()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Hierarchy computation — derived entirely from existing event types
# ---------------------------------------------------------------------------

def _compute_hierarchy(events: list[dict], state: dict) -> dict:
    """Compute agent tree + active state from the existing event log.

    Active rule:
      - An agent is active if it has an ``agent_spawn`` event with no matching
        ``agent_return`` event yet, AND the session has not ended (no
        ``budget_cap`` event).
      - The orchestrator becomes inactive when a ``budget_cap`` fires.
    Hierarchy rule:
      - ``orchestrator`` is always root.
      - Every other agent (coder-N, tester-N, …) is a child of orchestrator.
        If an event carries an explicit ``parent`` field, that is used instead.
    """
    spawned: dict[str, dict] = {}   # name → {model, role, t_offset, parent}
    returned: set[str] = set()
    session_ended: bool = False

    for ev in events:
        etype = ev.get("type", "")
        if etype == "agent_spawn":
            name = ev.get("agent", "")
            if name and name not in spawned:
                spawned[name] = {
                    "model": ev.get("model", ""),
                    "role":  ev.get("role", name),
                    "t_offset": ev.get("t_offset", 0.0),
                    "parent": ev.get("parent", None),
                }
        elif etype == "agent_return":
            returned.add(ev.get("agent", ""))
        elif etype == "budget_cap":
            session_ended = True

    agents_state = state.get("agents", {})

    def _node(name: str) -> dict:
        info  = spawned.get(name, {})
        usage = agents_state.get(name, {})
        tokens = (usage.get("input", 0) + usage.get("output", 0))
        is_orch = name == "orchestrator"
        active = (
            name in spawned
            and name not in returned
            and not (session_ended and is_orch)
        )
        return {
            "name":   name,
            "role":   info.get("role", name),
            "model":  info.get("model", ""),
            "active": active,
            "tokens": tokens,
            "cost":   usage.get("cost", 0.0),
        }

    # Children: all spawned agents except orchestrator, in appearance order.
    # Respect explicit parent field; default parent is orchestrator.
    children: list[dict] = []
    seen: set[str] = set()
    for ev in events:
        if ev.get("type") == "agent_spawn":
            name = ev.get("agent", "")
            if name and name != "orchestrator" and name not in seen:
                seen.add(name)
                children.append(_node(name))

    return {
        "root":     _node("orchestrator"),
        "children": children,
        "has_data": bool(spawned),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index() -> Response:
    return Response(_HTML, mimetype="text/html")


@app.route("/api/state")
def api_state() -> Response:
    return jsonify(_load_state())


@app.route("/api/events")
def api_events() -> Response:
    return jsonify(_load_events())


@app.route("/api/hierarchy")
def api_hierarchy() -> Response:
    events = _load_events(500)
    state  = _load_state()
    return jsonify(_compute_hierarchy(events, state))


# ---------------------------------------------------------------------------
# Self-contained HTML page
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iTakt Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  header { background: #1a1d27; border-bottom: 1px solid #2d3748; padding: 14px 24px; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.2rem; font-weight: 600; letter-spacing: .03em; }
  header .badge { font-size: .72rem; background: #2d3748; border-radius: 4px; padding: 2px 8px; color: #90cdf4; }
  main { padding: 24px; max-width: 1100px; margin: 0 auto; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
  .card { background: #1a1d27; border: 1px solid #2d3748; border-radius: 8px; padding: 18px; }
  .card h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .1em; color: #718096; margin-bottom: 12px; }
  .stat { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
  .stat .label { color: #a0aec0; font-size: .85rem; }
  .stat .value { font-size: 1rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .bar-wrap { height: 8px; background: #2d3748; border-radius: 4px; margin: 10px 0 4px; overflow: hidden; }
  .bar { height: 100%; border-radius: 4px; transition: width .4s ease; }
  .bar.green  { background: #48bb78; }
  .bar.yellow { background: #ecc94b; }
  .bar.red    { background: #fc8181; }
  .pct { font-size: .78rem; color: #a0aec0; text-align: right; }

  /* ---- Agent hierarchy ---- */
  @keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 0 0 rgba(99, 179, 237, 0);   border-color: #2d3748; }
    50%       { box-shadow: 0 0 14px 5px rgba(99, 179, 237, .35); border-color: #63b3ed; }
  }
  #hierarchy-tree { min-height: 80px; }
  .tree-root   { margin-bottom: 12px; }
  .tree-line   { width: 2px; height: 14px; background: #2d3748; margin-left: 22px; }
  .tree-children { display: flex; flex-wrap: wrap; gap: 10px; padding-left: 10px;
                   border-left: 2px solid #2d3748; margin-left: 20px; }
  .agent-node  { background: #111520; border: 1px solid #2d3748; border-radius: 6px;
                 padding: 10px 14px; min-width: 155px; transition: border-color .4s; }
  .agent-node.active { animation: pulse-glow 1.8s ease-in-out infinite; }
  .agent-header { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
  .agent-dot   { font-size: .8rem; }
  .dot-active  { color: #48bb78; }
  .dot-idle    { color: #4a5568; }
  .agent-name  { font-size: .85rem; font-weight: 600; }
  .agent-role  { font-size: .65rem; color: #718096; text-transform: uppercase;
                 letter-spacing: .06em; margin-left: auto; }
  .agent-model { font-size: .65rem; color: #4a5568; white-space: nowrap;
                 overflow: hidden; text-overflow: ellipsis; max-width: 130px;
                 margin-bottom: 3px; }
  .agent-stats { font-size: .75rem; color: #a0aec0; font-variant-numeric: tabular-nums; }

  /* ---- Event stream ---- */
  .event-list { list-style: none; max-height: 280px; overflow-y: auto; font-size: .8rem; }
  .event-list li { padding: 5px 0; border-bottom: 1px solid #1e2231; display: flex; gap: 8px; }
  .event-list li:last-child { border-bottom: none; }
  .ts { color: #4a5568; min-width: 85px; font-variant-numeric: tabular-nums; }
  .badge-safe    { background: #276749; color: #9ae6b4; padding: 1px 5px; border-radius: 3px; }
  .badge-review  { background: #744210; color: #fbd38d; padding: 1px 5px; border-radius: 3px; }
  .badge-blocked { background: #742a2a; color: #feb2b2; padding: 1px 5px; border-radius: 3px; }
  .badge-spawn   { background: #2c4f8c; color: #bee3f8; padding: 1px 5px; border-radius: 3px; }
  .badge-compact { background: #322659; color: #d6bcfa; padding: 1px 5px; border-radius: 3px; }
  .badge-warn    { background: #744210; color: #fbd38d; padding: 1px 5px; border-radius: 3px; }
  .badge-cap     { background: #742a2a; color: #feb2b2; padding: 1px 5px; border-radius: 3px; }
  .empty { color: #4a5568; font-style: italic; padding: 12px 0; text-align: center; }
  #refresh-ts { font-size: .72rem; color: #4a5568; margin-left: auto; }
</style>
</head>
<body>
<header>
  <h1>iTakt</h1>
  <span class="badge">Web Dashboard</span>
  <span id="refresh-ts">–</span>
</header>
<main>
  <div class="grid">
    <!-- Session card -->
    <div class="card" id="session-card">
      <h2>Session</h2>
      <div class="stat"><span class="label">Tokens</span><span class="value" id="tot-tok">–</span></div>
      <div class="stat"><span class="label">Cost</span><span class="value" id="tot-cost">–</span></div>
      <div class="stat"><span class="label">Steps</span><span class="value" id="steps">–</span></div>
      <div class="bar-wrap"><div class="bar green" id="budget-bar" style="width:0%"></div></div>
      <div class="pct" id="budget-pct">–</div>
    </div>

    <!-- Agent hierarchy card -->
    <div class="card">
      <h2>Agent Hierarchy</h2>
      <div id="hierarchy-tree">
        <div class="empty">waiting for agents…</div>
      </div>
    </div>
  </div>

  <!-- Event stream -->
  <div class="card">
    <h2>Event Stream</h2>
    <ul class="event-list" id="event-list">
      <li><span class="empty" style="width:100%">waiting for events…</span></li>
    </ul>
  </div>
</main>

<script>
const fmt     = n => typeof n === 'number' ? n.toLocaleString() : '–';
const fmtCost = c => typeof c === 'number' ? '$' + c.toFixed(4) : '–';
const shortTs = ts => ts ? ts.slice(11, 23) : '–';
const shortModel = m => m ? m.split('-').slice(0,3).join('-') : '';

// ---- Hierarchy rendering ----

function agentNodeHtml(agent) {
  const cls      = agent.active ? 'agent-node active' : 'agent-node';
  const dotCls   = agent.active ? 'agent-dot dot-active' : 'agent-dot dot-idle';
  const dotChar  = agent.active ? '●' : '○';
  const roleTag  = agent.role && agent.role !== agent.name
    ? `<span class="agent-role">${agent.role}</span>` : '';
  const modelTag = agent.model
    ? `<div class="agent-model">${shortModel(agent.model)}</div>` : '';
  return `<div class="${cls}">
    <div class="agent-header">
      <span class="${dotCls}">${dotChar}</span>
      <span class="agent-name">${agent.name}</span>
      ${roleTag}
    </div>
    ${modelTag}
    <div class="agent-stats">${fmt(agent.tokens)} tok · ${fmtCost(agent.cost)}</div>
  </div>`;
}

function renderHierarchy(hier) {
  const el = document.getElementById('hierarchy-tree');
  if (!hier || !hier.has_data) {
    el.innerHTML = '<div class="empty">waiting for agents…</div>';
    return;
  }
  const rootHtml = `<div class="tree-root">${agentNodeHtml(hier.root)}</div>`;
  let childHtml  = '';
  if (hier.children && hier.children.length) {
    const nodes = hier.children.map(agentNodeHtml).join('');
    childHtml = `<div class="tree-line"></div><div class="tree-children">${nodes}</div>`;
  }
  el.innerHTML = rootHtml + childHtml;
}

// ---- Event stream rendering ----

function badgeFor(ev) {
  if (ev.type === 'agent_spawn')  return `<span class="badge-spawn">spawn</span>`;
  if (ev.type === 'agent_return') return `<span class="badge-spawn">return</span>`;
  if (ev.type === 'tool_call') {
    const c = ev.classification || '';
    return `<span class="badge-${c.toLowerCase()}">${c}</span>`;
  }
  if (ev.type === 'compaction')     return `<span class="badge-compact">compact</span>`;
  if (ev.type === 'budget_warning') return `<span class="badge-warn">warn ${ev.level}%</span>`;
  if (ev.type === 'budget_cap')     return `<span class="badge-cap">cap</span>`;
  return `<span>${ev.type}</span>`;
}

function descFor(ev) {
  if (ev.type === 'agent_spawn')  return `${ev.agent} (${ev.model}) t+${ev.t_offset}s`;
  if (ev.type === 'agent_return') return `${ev.agent} tokens=${fmt(ev.tokens)} usd=${fmtCost(ev.cost)} t+${ev.t_offset}s`;
  if (ev.type === 'tool_call')    return `${ev.agent} → ${ev.tool} → ${ev.outcome} [${ev.summary}]`;
  if (ev.type === 'compaction')   return `${ev.agent} ${fmt(ev.before)}→${fmt(ev.after)} tok (${ev.pct}% reduced)`;
  if (ev.type === 'budget_warning') return `budget at ${ev.level}%`;
  if (ev.type === 'budget_cap')   return `STOPPED: ${fmt(ev.total_tokens)} tok / ${fmtCost(ev.total_cost)}`;
  return JSON.stringify(ev);
}

// ---- Main refresh loop ----

async function refresh() {
  try {
    const [stateRes, eventsRes, hierRes] = await Promise.all([
      fetch('/api/state'), fetch('/api/events'), fetch('/api/hierarchy')
    ]);
    const state  = await stateRes.json();
    const events = await eventsRes.json();
    const hier   = await hierRes.json();

    // Session card
    const tok = state.total_tokens || 0;
    const cap = state.budget_tokens || 1;
    const pct = Math.min(100, tok / cap * 100);
    document.getElementById('tot-tok').textContent  = fmt(tok);
    document.getElementById('tot-cost').textContent = fmtCost(state.total_cost);
    document.getElementById('steps').textContent    = fmt(state.steps);
    const bar = document.getElementById('budget-bar');
    bar.style.width  = pct.toFixed(1) + '%';
    bar.className    = 'bar ' + (pct >= 90 ? 'red' : pct >= 70 ? 'yellow' : 'green');
    document.getElementById('budget-pct').textContent =
      pct.toFixed(1) + '% of ' + fmt(cap) + ' tokens';

    // Hierarchy
    renderHierarchy(hier);

    // Events
    const ul = document.getElementById('event-list');
    if (events.length) {
      ul.innerHTML = events.slice().reverse().map(ev =>
        `<li><span class="ts">${shortTs(ev.ts)}</span>${badgeFor(ev)}<span>${descFor(ev)}</span></li>`
      ).join('');
    }

    document.getElementById('refresh-ts').textContent =
      'updated ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('refresh-ts').textContent = 'error: ' + e.message;
  }
}

refresh();
setInterval(refresh, 1500);
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="iTakt web dashboard")
    parser.add_argument("--port", type=int, default=8787,
                        help="Port to listen on (default 8787)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default 127.0.0.1)")
    args = parser.parse_args()
    print(f"iTakt dashboard →  http://{args.host}:{args.port}/")
    print("Reads traces/session_state.json and traces/events.jsonl (written by agent)")
    print("Ctrl-C to stop")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
