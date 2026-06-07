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


def _load_events(last_n: int = 100) -> list[dict]:
    try:
        lines = _EVENTS.read_text().splitlines()
        return [json.loads(l) for l in lines[-last_n:] if l.strip()]
    except Exception:
        return []


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
  .bar.green { background: #48bb78; }
  .bar.yellow { background: #ecc94b; }
  .bar.red { background: #fc8181; }
  .pct { font-size: .78rem; color: #a0aec0; text-align: right; }
  table { width: 100%; border-collapse: collapse; font-size: .82rem; }
  th { text-align: left; color: #718096; font-weight: 500; padding: 4px 8px 8px; border-bottom: 1px solid #2d3748; }
  td { padding: 6px 8px; border-bottom: 1px solid #1e2231; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  .event-list { list-style: none; max-height: 320px; overflow-y: auto; font-size: .8rem; }
  .event-list li { padding: 5px 0; border-bottom: 1px solid #1e2231; display: flex; gap: 8px; }
  .event-list li:last-child { border-bottom: none; }
  .ts { color: #4a5568; min-width: 85px; font-variant-numeric: tabular-nums; }
  .badge-safe   { background: #276749; color: #9ae6b4; padding: 1px 5px; border-radius: 3px; }
  .badge-review { background: #744210; color: #fbd38d; padding: 1px 5px; border-radius: 3px; }
  .badge-blocked { background: #742a2a; color: #feb2b2; padding: 1px 5px; border-radius: 3px; }
  .badge-spawn  { background: #2c4f8c; color: #bee3f8; padding: 1px 5px; border-radius: 3px; }
  .badge-compact { background: #322659; color: #d6bcfa; padding: 1px 5px; border-radius: 3px; }
  .badge-warn   { background: #744210; color: #fbd38d; padding: 1px 5px; border-radius: 3px; }
  .badge-cap    { background: #742a2a; color: #feb2b2; padding: 1px 5px; border-radius: 3px; }
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
    <div class="card" id="session-card">
      <h2>Session</h2>
      <div class="stat"><span class="label">Tokens</span><span class="value" id="tot-tok">–</span></div>
      <div class="stat"><span class="label">Cost</span><span class="value" id="tot-cost">–</span></div>
      <div class="stat"><span class="label">Steps</span><span class="value" id="steps">–</span></div>
      <div class="bar-wrap"><div class="bar green" id="budget-bar" style="width:0%"></div></div>
      <div class="pct" id="budget-pct">–</div>
    </div>
    <div class="card">
      <h2>Agents</h2>
      <table>
        <thead><tr><th>Agent</th><th>Tokens</th><th>Cost</th><th>Calls</th></tr></thead>
        <tbody id="agents-tbody"><tr><td colspan="4" class="empty">no data yet</td></tr></tbody>
      </table>
    </div>
  </div>
  <div class="card">
    <h2>Event Stream</h2>
    <ul class="event-list" id="event-list">
      <li><span class="empty" style="width:100%">waiting for events…</span></li>
    </ul>
  </div>
</main>
<script>
const fmt = n => typeof n === 'number' ? n.toLocaleString() : '–';
const fmtCost = c => typeof c === 'number' ? '$' + c.toFixed(4) : '–';
const shortTs = ts => ts ? ts.slice(11, 23) : '–';

function badgeFor(ev) {
  if (ev.type === 'agent_spawn') return `<span class="badge-spawn">spawn</span>`;
  if (ev.type === 'agent_return') return `<span class="badge-spawn">return</span>`;
  if (ev.type === 'tool_call') {
    const c = ev.classification || '';
    return `<span class="badge-${c.toLowerCase()}">${c}</span>`;
  }
  if (ev.type === 'compaction') return `<span class="badge-compact">compact</span>`;
  if (ev.type === 'budget_warning') return `<span class="badge-warn">warn ${ev.level}%</span>`;
  if (ev.type === 'budget_cap') return `<span class="badge-cap">cap</span>`;
  return `<span>${ev.type}</span>`;
}

function descFor(ev) {
  if (ev.type === 'agent_spawn') return `${ev.agent} (${ev.model}) t+${ev.t_offset}s`;
  if (ev.type === 'agent_return') return `${ev.agent} tokens=${fmt(ev.tokens)} usd=${fmtCost(ev.cost)} t+${ev.t_offset}s`;
  if (ev.type === 'tool_call') return `${ev.agent} → ${ev.tool} → ${ev.outcome} [${ev.summary}]`;
  if (ev.type === 'compaction') return `${ev.agent} ${fmt(ev.before)}→${fmt(ev.after)} tok (${ev.pct}% reduced)`;
  if (ev.type === 'budget_warning') return `budget at ${ev.level}%`;
  if (ev.type === 'budget_cap') return `STOPPED: ${fmt(ev.total_tokens)} tok / ${fmtCost(ev.total_cost)}`;
  return JSON.stringify(ev);
}

async function refresh() {
  try {
    const [stateRes, eventsRes] = await Promise.all([
      fetch('/api/state'), fetch('/api/events')
    ]);
    const state = await stateRes.json();
    const events = await eventsRes.json();

    // Session card
    const tok = state.total_tokens || 0;
    const cap = state.budget_tokens || 1;
    const pct = Math.min(100, tok / cap * 100);
    document.getElementById('tot-tok').textContent = fmt(tok);
    document.getElementById('tot-cost').textContent = fmtCost(state.total_cost);
    document.getElementById('steps').textContent = fmt(state.steps);
    const bar = document.getElementById('budget-bar');
    bar.style.width = pct.toFixed(1) + '%';
    bar.className = 'bar ' + (pct >= 90 ? 'red' : pct >= 70 ? 'yellow' : 'green');
    document.getElementById('budget-pct').textContent = pct.toFixed(1) + '% of ' + fmt(cap) + ' tokens';

    // Agents table
    const tbody = document.getElementById('agents-tbody');
    const agents = state.agents || {};
    const names = Object.keys(agents);
    if (names.length) {
      tbody.innerHTML = names.map(name => {
        const a = agents[name];
        const t = (a.input || 0) + (a.output || 0);
        return `<tr><td>${name}</td><td>${fmt(t)}</td><td>${fmtCost(a.cost)}</td><td>${fmt(a.calls)}</td></tr>`;
      }).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">no data yet</td></tr>';
    }

    // Events
    const ul = document.getElementById('event-list');
    if (events.length) {
      ul.innerHTML = events.slice().reverse().map(ev =>
        `<li><span class="ts">${shortTs(ev.ts)}</span>${badgeFor(ev)}<span>${descFor(ev)}</span></li>`
      ).join('');
    }

    document.getElementById('refresh-ts').textContent = 'updated ' + new Date().toLocaleTimeString();
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
    parser.add_argument("--port", type=int, default=8787, help="Port to listen on (default 8787)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    args = parser.parse_args()
    print(f"iTakt dashboard →  http://{args.host}:{args.port}/")
    print("Reads traces/session_state.json and traces/events.jsonl (written by agent)")
    print("Ctrl-C to stop")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
