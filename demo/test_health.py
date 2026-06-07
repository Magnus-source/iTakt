"""Pytest tests for the /health endpoint of the iTakt demo Flask app."""
import pytest
from datetime import datetime
from app import app


@pytest.fixture
def client():
    """Create a Flask test client for use in tests."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_status_code(client):
    """Assert that GET /health returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_contains_status_ok(client):
    """Assert that the JSON body contains 'status': 'ok'."""
    response = client.get("/health")
    data = response.get_json()
    assert data["status"] == "ok"


def test_health_contains_timestamp_key(client):
    """Assert that the JSON body contains a 'timestamp' key."""
    response = client.get("/health")
    data = response.get_json()
    assert "timestamp" in data


def test_health_timestamp_is_valid_iso8601(client):
    """Assert that the timestamp value is a valid ISO 8601 datetime string."""
    response = client.get("/health")
    data = response.get_json()
    timestamp = data["timestamp"]
    # Should not raise; proves it's a valid ISO 8601 string
    parsed = datetime.fromisoformat(timestamp)
    assert isinstance(parsed, datetime)


def test_health_response_is_json(client):
    """Assert that the Content-Type header indicates JSON."""
    response = client.get("/health")
    assert response.content_type == "application/json"


def test_health_complete_response(client):
    """Integration test: status 200, status=ok, and valid ISO timestamp."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    parsed = datetime.fromisoformat(data["timestamp"])
    assert isinstance(parsed, datetime)
