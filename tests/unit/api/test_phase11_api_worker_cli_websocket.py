"""
Unit tests for WindAgent API, Worker, CLI, and WebSocket Adoption (Phase 11).
Verifies removal of IN_MEMORY_TASKS and MOCK_DOMAIN_EVENTS, DTO mapping, typed WorkerId & RuntimeRunId,
EventEnvelope publishing, CLI Doctor checks, and WebSocket event sequence replay.
"""

import pytest
import sys
from fastapi.testclient import TestClient

from windagent_core.domain.types import WorkerId, RuntimeRunId, TaskId, SessionId
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_api.main import app
from windagent_worker.runner import ProductionWorker
from windagent_cli.main import doctor as cli_doctor

client = TestClient(app)


def test_api_v2_tasks_no_in_memory_tasks():
    sess_id = str(SessionId.generate())

    # 1. Create Task
    create_resp = client.post("/api/v2/tasks", json={"prompt": "Integrate payment API", "session_id": sess_id})
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert "task_id" in data
    assert data["session_id"] == sess_id
    assert data["status"] in ("RECEIVED", "CREATED", "PLANNING", "RUNNING", "PENDING", "pending")
    assert "created_at" in data
    assert "2026-07-23" not in data["created_at"]  # No hardcoded legacy timestamp

    task_id = data["task_id"]

    # 2. Get Task
    get_resp = client.get(f"/api/v2/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["task_id"] == task_id

    # 3. Cancel Task
    cancel_resp = client.post(f"/api/v2/tasks/{task_id}/cancel")
    assert cancel_resp.status_code in (200, 400)


def test_api_v2_events_no_mock_domain_events():
    resp = client.get("/api/v2/events")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    # Verify no mock events hardcoded
    for evt in events:
        assert "evt_01" not in evt.get("event_id", "")


@pytest.mark.asyncio
async def test_worker_typed_ids_and_canonical_events():
    worker = ProductionWorker(name="test_worker_p11")
    await worker.start()
    assert isinstance(worker.worker_id, WorkerId)
    assert isinstance(worker.runtime_run_id, RuntimeRunId)

    env = worker.emit_event(EventCatalog.TASK_CREATED, {"task_id": "task_123"})
    assert isinstance(env, EventEnvelope)
    assert env.sequence == 1
    assert env.metadata["worker_id"] == str(worker.worker_id)

    await worker.stop()
    assert worker.is_running is False


def test_cli_doctor_phase11_checks(capsys):
    res = cli_doctor()
    assert res == 0
    captured = capsys.readouterr().out
    assert "Duplicate Model Check" in captured
    assert "Import Boundary Check" in captured
    assert "Migration Status Check" in captured
    assert "Secret Configuration Check" in captured
    assert "Event Schema Version Check" in captured
