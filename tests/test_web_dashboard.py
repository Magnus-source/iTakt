"""Tests for the web dashboard server — starts the Flask app and checks responses."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from itakt.web_dashboard import app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"iTakt" in resp.data
    assert b"text/html" in resp.content_type.encode()


def test_index_contains_key_ui_elements(client):
    resp = client.get("/")
    html = resp.data.decode()
    assert "Session" in html
    assert "Agents" in html
    assert "Event Stream" in html
    assert "budget-bar" in html


def test_api_state_empty(client):
    """With no session_state.json, returns an empty dict."""
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)


def test_api_events_empty(client):
    """With no events.jsonl, returns an empty list."""
    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_api_state_with_file(client, tmp_path, monkeypatch):
    """When session_state.json exists, /api/state returns its content."""
    import itakt.web_dashboard as wd
    state = {"total_tokens": 1234, "total_cost": 0.05, "agents": {}, "steps": 3}
    state_file = tmp_path / "session_state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(wd, "_STATE", state_file)

    resp = client.get("/api/state")
    data = resp.get_json()
    assert data["total_tokens"] == 1234
    assert data["steps"] == 3


def test_api_events_with_file(client, tmp_path, monkeypatch):
    """When events.jsonl exists, /api/events returns parsed events."""
    import itakt.web_dashboard as wd
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        '{"ts":"2026-01-01T00:00:00","type":"agent_spawn","agent":"orchestrator"}\n'
        '{"ts":"2026-01-01T00:00:01","type":"tool_call","tool":"read_file","agent":"orchestrator"}\n'
    )
    monkeypatch.setattr(wd, "_EVENTS", events_file)

    resp = client.get("/api/events")
    data = resp.get_json()
    assert len(data) == 2
    assert data[0]["type"] == "agent_spawn"
    assert data[1]["type"] == "tool_call"


def test_dashboard_does_not_crash_on_malformed_files(client, tmp_path, monkeypatch):
    """Corrupted trace files must not crash the dashboard."""
    import itakt.web_dashboard as wd
    bad_file = tmp_path / "session_state.json"
    bad_file.write_text("{not valid json")
    monkeypatch.setattr(wd, "_STATE", bad_file)

    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.get_json() == {}
