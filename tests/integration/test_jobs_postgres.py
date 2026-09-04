"""Phase 7 reliability semantics on canonical PostgreSQL."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from windagent.kernel.types.json import JSONValue
from windagent.platform.configuration.settings import Settings
from windagent.platform.events import (
    OutboxPublisher,
    OutboxStore,
    events_table,
    outbox_table,
)
from windagent.platform.jobs import JobHandlerRegistry, JobStatus, JobSubmission
from windagent.platform.jobs.postgres import (
    PostgresJobQueue,
    job_attempts_table,
    jobs_table,
)
from windagent.platform.persistence import Database
from windagent.platform.realtime import RealtimeHub
from windagent_api.app import create_app
from windagent_worker import FakeJobHandler, WorkerRuntime, WorkerTickStatus

pytestmark = [pytest.mark.postgres]


class EchoHandler:
    @property
    def job_type(self) -> str:
        return "integration.echo"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        return {"echo": payload.get("value")}


async def _clean_jobs(database: Database) -> None:
    async with database.session_factory() as session:
        await session.execute(delete(job_attempts_table))
        await session.execute(delete(jobs_table))
        await session.commit()


async def _clean_vertical_slice(database: Database) -> None:
    async with database.session_factory() as session:
        await session.execute(delete(outbox_table))
        await session.execute(delete(events_table))
        await session.execute(delete(job_attempts_table))
        await session.execute(delete(jobs_table))
        await session.commit()


async def test_concurrent_workers_claim_disjoint_jobs(database: Database) -> None:
    await _clean_jobs(database)
    queue = PostgresJobQueue(database.session_factory)
    receipts = [
        await queue.submit(JobSubmission("integration.echo", {"value": index}))
        for index in range(8)
    ]

    async def claim(worker_id: str):  # type: ignore[no-untyped-def]
        return await queue.claim_next(worker_id=worker_id, lease_s=30)

    claims = await asyncio.gather(*(claim(f"worker-{index}") for index in range(8)))
    claimed_ids = [str(claimed.id) for claimed in claims if claimed is not None]

    assert len(claimed_ids) == 8
    assert len(set(claimed_ids)) == 8
    assert set(claimed_ids) == {str(receipt.job_id) for receipt in receipts}


async def test_worker_finalization_is_atomic_and_restart_visible(database: Database) -> None:
    await _clean_jobs(database)
    api_queue = PostgresJobQueue(database.session_factory)
    receipt = await api_queue.submit(
        JobSubmission(
            "integration.echo",
            {"value": "postgres"},
            idempotency_key="integration-restart-visible",
        )
    )

    registry = JobHandlerRegistry()
    registry.register(EchoHandler())
    worker_queue = PostgresJobQueue(database.session_factory)
    worker = WorkerRuntime(
        worker_queue,
        registry,
        worker_id="integration-worker",
        lease_s=30,
        heartbeat_interval_s=1,
    )
    report = await worker.run_once()

    restarted_server_queue = PostgresJobQueue(database.session_factory)
    record = await restarted_server_queue.get(receipt.job_id)
    duplicate = await restarted_server_queue.submit(
        JobSubmission(
            "integration.echo",
            {"value": "ignored"},
            idempotency_key="integration-restart-visible",
        )
    )

    assert report.status == WorkerTickStatus.SUCCEEDED
    assert record is not None and record.status == JobStatus.SUCCEEDED
    assert record.result == {"echo": "postgres"}
    assert duplicate.job_id == receipt.job_id
    assert duplicate.deduplicated is True


async def test_fake_job_http_postgres_worker_outbox_websocket_vertical_slice(
    database: Database,
    database_url: str,
) -> None:
    await _clean_vertical_slice(database)
    queue = PostgresJobQueue(database.session_factory)
    hub = RealtimeHub()
    publisher = OutboxPublisher(
        OutboxStore(database.session_factory),
        hub,
        worker_id="integration-events",
    )
    registry = JobHandlerRegistry()
    registry.register(FakeJobHandler())
    worker = WorkerRuntime(
        queue,
        registry,
        worker_id="integration-fake-worker",
        lease_s=30,
        heartbeat_interval_s=1,
        outbox_publisher=publisher,
    )
    app = create_app(
        Settings(environment="test", database_url=database_url),
        job_queue=queue,
        realtime_hub=hub,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://v2.test",
    ) as client:
        accepted = await client.post(
            "/debug/jobs",
            json={"job_type": "debug.echo", "payload": {"message": "postgres"}},
        )
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]

        report = await worker.run_once()
        status = await client.get(f"/debug/jobs/{job_id}")

    with TestClient(app) as client:
        with client.websocket_connect("/debug/jobs/events?after=0") as websocket:
            websocket_event = websocket.receive_json()

    assert report.status == WorkerTickStatus.SUCCEEDED
    assert report.outbox_published == 1
    assert status.json()["status"] == "succeeded"
    assert status.json()["result"] == {
        "echo": {"message": "postgres"},
        "handled": True,
    }
    assert websocket_event["event"]["event_type"] == "platform.job.succeeded"
    assert websocket_event["event"]["aggregate_id"] == job_id
