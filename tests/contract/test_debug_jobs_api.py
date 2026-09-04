"""Transport contracts for the opt-in Phase 7 debug vertical slice."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import cast

from fastapi.testclient import TestClient
from windagent.kernel.events import EventEnvelope
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
from windagent.platform.realtime import RealtimeHub
from windagent_api.app import create_app


class DebugQueue:
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
                trace_id=job.trace_id,
                actor_id=job.actor_id,
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


def _app(queue: DebugQueue, hub: RealtimeHub | None = None):  # type: ignore[no-untyped-def]
    return create_app(
        Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"),
        job_queue=cast(DurableJobQueue, queue),
        realtime_hub=hub,
    )


def test_debug_job_submission_and_status_contract() -> None:
    queue = DebugQueue()
    with TestClient(_app(queue)) as client:
        response = client.post(
            "/debug/jobs",
            json={"job_type": "debug.echo", "payload": {"message": "hello"}},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        status = client.get(f"/debug/jobs/{job_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "pending"
        assert status.json()["job_type"] == "debug.echo"
        assert queue.record is not None
        assert queue.record.envelope.trace_id == response.headers["x-trace-id"]
        assert str(queue.record.envelope.correlation_id) == response.headers[
            "x-correlation-id"
        ]


def test_debug_websocket_replays_outbox_delivered_event() -> None:
    queue = DebugQueue()
    hub = RealtimeHub()
    aggregate_id = EntityId.new()
    asyncio.run(
        hub.publish(
            EventEnvelope(
                event_type="platform.job.succeeded",
                aggregate_type="job",
                aggregate_id=aggregate_id,
                sequence=0,
                payload={"status": "succeeded"},
            )
        )
    )

    with TestClient(_app(queue, hub)) as client:
        with client.websocket_connect("/debug/jobs/events?after=0") as websocket:
            message = websocket.receive_json()

    assert message["position"] == 1
    assert message["event"]["aggregate_id"] == str(aggregate_id)
