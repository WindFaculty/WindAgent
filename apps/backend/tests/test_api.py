"""End-to-end HTTP tests against the FastAPI app (no WebSocket).

WebSocket behaviour is covered separately in test_websocket.py because
sync TestClient + WS has a deadlock with multi-event flows; that file
uses httpx.AsyncClient instead.
"""
from __future__ import annotations

import pytest


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "windagent-backend"


def test_create_session(client):
    resp = client.post("/sessions")
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"]
    assert body["status"] == "idle"
    assert body["created_at"]


def test_get_session_unknown_returns_404(client):
    resp = client.get("/sessions/00000000-0000-4000-8000-000000000999")
    assert resp.status_code == 404


def test_get_session_returns_existing(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.get(f"/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sid


def test_send_message_returns_workflow(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hello"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["message_id"]
    assert body["workflow_id"]
    assert body["step_count"] == 2


def test_send_message_unknown_session_returns_404(client):
    resp = client.post(
        "/sessions/00000000-0000-4000-8000-000000000999/messages",
        json={"content": "hello"},
    )
    assert resp.status_code == 404


def test_get_workflow_after_planning(client):
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hello"},
    )
    # Phase 5: the runner auto-starts on /messages. With MockGuiAdapter
    # the workflow completes almost instantly; give it a tiny window.
    import time
    time.sleep(0.2)
    resp = client.get(f"/sessions/{sid}/workflow")
    assert resp.status_code == 200
    wf = resp.json()
    # Status is whatever the runner has reached — pending/running/completed.
    assert wf["status"] in {"pending", "running", "completed"}
    assert wf["session_id"] == sid
    assert len(wf["steps"]) == 2
    assert wf["steps"][0]["tool_name"] == "open_app"
    assert wf["steps"][1]["tool_name"] == "type_text"


def test_pause_without_workflow_returns_404(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(f"/sessions/{sid}/pause")
    assert resp.status_code == 404


def test_pause_with_workflow_returns_202(client):
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/messages", json={"content": "Mở Notepad và gõ Hi"}
    )
    resp = client.post(f"/sessions/{sid}/pause")
    assert resp.status_code == 202
    assert resp.json()["status"] == "paused_requested"


def test_resume_returns_202(client):
    sid = client.post("/sessions").json()["session_id"]
    client.post(f"/sessions/{sid}/messages", json={"content": "Mở Edge"})
    resp = client.post(f"/sessions/{sid}/resume")
    assert resp.status_code == 202
    assert resp.json()["status"] == "resumed_requested"


def test_stop_returns_202(client):
    sid = client.post("/sessions").json()["session_id"]
    client.post(f"/sessions/{sid}/messages", json={"content": "Mở Notepad"})
    resp = client.post(f"/sessions/{sid}/stop")
    assert resp.status_code == 202
    assert resp.json()["status"] == "stopped_requested"


def test_retry_endpoint_returns_202_in_phase5(client):
    """Phase 5: retry is implemented (returns 202 + status retry_requested)."""
    import time
    sid = client.post("/sessions").json()["session_id"]
    client.post(
        f"/sessions/{sid}/messages",
        json={"content": "Mở Notepad và gõ Hello"},
    )
    # Wait for runner to finish so the workflow has a recorded state.
    time.sleep(0.2)
    wf = client.get(f"/sessions/{sid}/workflow").json()
    step_id = wf["steps"][0]["id"]
    resp = client.post(f"/workflow/{step_id}/retry")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "retry_requested"
    assert body["step_id"] == step_id
    assert body["workflow_id"] == wf["workflow_id"]


def test_message_validation_rejects_empty(client):
    sid = client.post("/sessions").json()["session_id"]
    resp = client.post(f"/sessions/{sid}/messages", json={"content": ""})
    assert resp.status_code == 422  # Pydantic rejects min_length=1
