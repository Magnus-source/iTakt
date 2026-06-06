"""Tests for the /health endpoint of the Flask demo app."""
import datetime
import pytest
from demo.app import app


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    return app.test_client()


def test_health_status_code(client):
    """GET /health returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_status_field(client):
    """Response JSON contains "status": "ok"."""
    response = client.get("/health")
    data = response.get_json()
    assert data is not None
    assert "status" in data
    assert data["status"] == "ok"


def test_health_timestamp_field(client):
    """Response JSON contains a "timestamp" key with a valid ISO format string."""
    response = client.get("/health")
    data = response.get_json()
    assert data is not None
    assert "timestamp" in data
    
    timestamp_str = data["timestamp"]
    assert isinstance(timestamp_str, str)
    assert len(timestamp_str) > 0
    
    # Verify it can be parsed by datetime.datetime.fromisoformat()
    parsed_timestamp = datetime.datetime.fromisoformat(timestamp_str)
    assert isinstance(parsed_timestamp, datetime.datetime)
