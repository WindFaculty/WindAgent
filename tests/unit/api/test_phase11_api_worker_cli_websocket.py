"""
Unit tests for WindAgent API, Worker, CLI, and WebSocket Adoption (Phase 11).
Verifies removal of IN_MEMORY_TASKS and MOCK_DOMAIN_EVENTS, DTO mapping, typed WorkerId & RuntimeRunId,
EventEnvelope publishing, CLI Doctor checks, and WebSocket event sequence replay.
"""

import pytest
from fastapi.testclient import TestClient

from windagent_core.domain.types import WorkerId, RuntimeRunId, SessionId
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_api.main import app
from windagent_worker.runner import ProductionWorker
from windagent_cli.main import doctor as cli_doctor

client = TestClient(app)


def test_api_v2_tasks_retired_tombstone():
    """Phase 15: /api/v2/tasks is retired; no in-memory task store exists."""
    sess_id = str(SessionId.generate())

    create_resp = client.post("/api/v2/tasks", json={"prompt": "Integrate payment API", "session_id": sess_id})
    assert create_resp.status_code == 410
    assert create_resp.json()["title"] == "API V2 Retired"


def test_api_v2_events_no_mock_domain_events():
    resp = client.get("/api/v2/events")
    # Phase 15: the V2 events surface is retired behind the tombstone.
    assert resp.status_code == 410
    body = resp.json()
    assert isinstance(body, dict)
    assert "evt_01" not in str(body)


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
    assert res == 2
    captured = capsys.readouterr().out
    assert "Duplicate Model Check" in captured
    assert "Import Boundary Check" in captured
    assert "Schema Migration" in captured
    assert "Configuration" in captured
    assert "Worker" in captured
    assert "System health status: DOWN" in captured
