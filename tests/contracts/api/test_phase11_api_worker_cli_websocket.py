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


def test_cli_doctor_phase11_checks(monkeypatch, capsys):
    """Doctor output surfaces the Phase 11 check sections and maps a DOWN
    verdict to exit code 2. The composer is scripted because the real one
    migrates the default DB before checking it (machine-dependent verdict)."""

    class _ScriptedComposer:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run_checks_sync(self) -> dict:
            return {
                "overall_status": "DOWN",
                "profile": "development",
                "checks": {
                    "import_boundary_check": {"passed": True, "details": "Zero import boundary violations"},
                    "duplicate_model_check": {"passed": True, "details": "ZERO duplicate models found"},
                    "schema_migration": {"passed": False, "details": "No migrations applied - alembic_version is empty"},
                    "configuration": {"passed": True, "details": "Configuration valid (env: development)"},
                    "worker": {"passed": False, "details": "No active workers (available: False)"},
                },
            }

    import sys

    cli_main = sys.modules["windagent_cli.main"]
    monkeypatch.setattr(cli_main, "DoctorCommandComposer", _ScriptedComposer)
    res = cli_doctor()
    assert res == 2
    captured = capsys.readouterr().out
    assert "Duplicate Model Check" in captured
    assert "Import Boundary Check" in captured
    assert "Schema Migration" in captured
    assert "Configuration" in captured
    assert "Worker" in captured
    assert "System health status: DOWN" in captured
