"""API regression tests for SWIFT combat endpoints."""

from fastapi.testclient import TestClient

from web.app import _combat_sessions, app


client = TestClient(app)


def setup_function():
    """Keep the in-memory combat store isolated between tests."""
    _combat_sessions.clear()


def test_invalid_fighter_index_returns_400():
    """Invalid fighter IDs must not escape as unhandled ValueError/HTTP 500."""
    start_response = client.post("/api/combat/start")
    assert start_response.status_code == 200
    session_id = start_response.json()["session_id"]

    response = client.post(
        f"/api/combat/action/{session_id}",
        params={"fighter": 2, "action": "attack"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "fighter must be 0 or 1"}
