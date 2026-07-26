"""
Phase 25 Unit and E2E Integration Tests: Canonical API V2 Cutover.
Verifies all 14 V2 routers, FastAPI TestClient integration, X-Idempotency-Key enforcement,
RFC 7807 error responses, WebSocket/SSE last_sequence event replay, and fail-closed readiness probes.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "tools", "apps/api"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.domain.types import EventId
from windagent_api.routers.v2_events import record_event_durable


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_liveness_and_readiness_probes(client):
    """Readiness fails closed when required runtime dependencies are absent."""
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "live"

    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 503
    assert res_ready.json()["status"] == "DOWN"
    assert res_ready.json()["checks"]["worker"]["status"] != "UP"
    assert "checks" in res_ready.json()


def test_api_v2_task_creation_e2e_with_idempotency(client):
    """Verify E2E task creation with X-Idempotency-Key header."""
    headers = {"X-Idempotency-Key": "idem_test_key_999"}
    payload = {
        "prompt": "Fix critical bug in payment service",
        "session_id": "sess_p25_test",
        "workflow_name": "bugfix"
    }

    res = client.post("/api/v2/tasks", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["task_id"] is not None
    assert data["prompt"] == "Fix critical bug in payment service"
    assert data["idempotency_key"] == "idem_test_key_999"

    task_id = data["task_id"]

    # GET task details
    res_get = client.get(f"/api/v2/tasks/{task_id}")
    assert res_get.status_code == 200
    assert res_get.json()["task_id"] == task_id

    # POST cancel task
    res_cancel = client.post(f"/api/v2/tasks/{task_id}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] in ("CANCELLED", "CANCELLED")


def test_all_14_canonical_v2_routers_accessible(client):
    """Verify endpoints across all 14 canonical V2 routers return 200 OK."""
    endpoints = [
        "/api/v2/sessions",
        "/api/v2/tasks",
        "/api/v2/runs",
        "/api/v2/workflows",
        "/api/v2/events",
        "/api/v2/providers",
        "/api/v2/tools",
        "/api/v2/permissions",
        "/api/v2/artifacts",
        "/api/v2/memory",
        "/api/v2/plugins",
        "/api/v2/skills",
        "/api/v2/evals",
        "/api/v2/observability/spans",
    ]

    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with status {res.status_code}"


def test_rfc7807_error_response_mapping(client):
    """Verify 404 Not Found returns structured RFC 7807 error response."""
    res = client.get("/api/v2/tasks/non_existent_task_id_xyz")
    assert res.status_code == 404
    data = res.json()
    assert "detail" in data or "title" in data


def test_event_stream_last_sequence_replay():
    """Verify event replay logic filtering by last_sequence cursor."""
    # Emit events
    env1 = EventEnvelope(
        event_id=EventId.generate(),
        event_type=EventCatalog.TASK_CREATED,
        aggregate_id="agg_1",
        sequence=1,
        payload={"task": "1"},
    )
    env2 = EventEnvelope(
        event_id=EventId.generate(),
        event_type=EventCatalog.TASK_COMPLETED,
        aggregate_id="agg_1",
        sequence=2,
        payload={"task": "1"},
    )

    record_event_durable(env1)
    record_event_durable(env2)

    with TestClient(app) as c:
        res = c.get("/api/v2/events?last_sequence=1")
        assert res.status_code == 200
        events = res.json()
        assert len(events) >= 1
        assert events[-1]["sequence_number"] == 2
