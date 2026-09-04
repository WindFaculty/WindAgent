"""Phase 8 contracts for the canonical /api/v4 surface."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi.testclient import TestClient
from windagent.kernel.ids import EntityId
from windagent.platform.configuration.settings import Settings
from windagent.platform.jobs import (
    DurableJobQueue,
    JobEnvelope,
    JobReceipt,
    JobRecord,
    JobStatus,
    JobSubmission,
)
from windagent.platform.modules import ModuleConflictError, ModuleManifest
from windagent_api.app import create_app


class StubQueue:
    def __init__(self) -> None:
        self.record: JobRecord | None = None

    async def submit(self, job: JobSubmission) -> JobReceipt:
        job_id = EntityId.new()
        now = datetime.now(UTC)
        self.record = JobRecord(
            envelope=JobEnvelope(
                id=job_id,
                job_type=job.job_type,
                version=job.version,
                payload=job.payload,
                priority=job.priority,
                max_attempts=job.max_attempts,
                timeout_s=job.timeout_s,
                deadline=job.deadline,
                correlation_id=job.correlation_id,
                causation_id=job.causation_id,
            ),
            status=JobStatus.PENDING,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        return JobReceipt(job_id)

    async def get(self, job_id: EntityId) -> JobRecord | None:
        if self.record is None or self.record.envelope.id != job_id:
            return None
        return self.record

    async def request_cancel(self, job_id: EntityId) -> bool:
        return self.record is not None and self.record.envelope.id == job_id


def _app(queue: object | None = None):  # type: ignore[no-untyped-def]
    return create_app(
        Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"),
        job_queue=cast("DurableJobQueue | None", queue),
    )


def test_system_info_is_served_through_the_query_bus() -> None:
    with TestClient(_app(StubQueue())) as client:
        response = client.get("/api/v4/system/info")
    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v4"
    assert body["environment"] == "test"
    assert isinstance(body["version"], str)
    assert "api.system" in body["modules"]
    assert "api.debug" in body["modules"]


def test_debug_module_only_registers_when_a_queue_is_injected() -> None:
    with TestClient(_app()) as client:
        response = client.get("/api/v4/system/info")
    assert response.status_code == 200
    modules = response.json()["modules"]
    # Feature modules arrive via package discovery; the debug surface is
    # the only app-owned module gated on explicit composition.
    assert "api.system" in modules
    assert "api.debug" not in modules


def test_unknown_v4_route_returns_canonical_error_envelope() -> None:
    with TestClient(_app()) as client:
        response = client.get("/api/v4/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert set(body["error"]) == {"code", "message", "context"}


def test_transport_validation_returns_canonical_envelope() -> None:
    with TestClient(_app(StubQueue())) as client:
        response = client.post("/debug/jobs", json={"max_attempts": 0})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request_validation_error"
    entry = body["error"]["context"]["errors"][0]
    assert set(entry) == {"loc", "msg", "type"}


def test_duplicate_module_registration_fails_at_composition() -> None:
    # create_app builds the same system manifest internally; injecting a
    # second manifest with the same ID must fail validation at startup.
    with pytest.raises(ModuleConflictError, match="already registered"):
        create_app(
            Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"),
            manifests=(ModuleManifest(id="api.system", version="0"),),
        )
