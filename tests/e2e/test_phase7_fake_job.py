"""Phase 7 vertical slice: HTTP → SQL → worker → outbox → realtime."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from windagent.platform.configuration.settings import Settings
from windagent.platform.events import OutboxPublisher, OutboxStore
from windagent.platform.jobs import JobHandlerRegistry
from windagent.platform.jobs.postgres import PostgresJobQueue
from windagent.platform.persistence import metadata
from windagent.platform.realtime import RealtimeHub
from windagent_api.app import create_app
from windagent_worker import FakeJobHandler, WorkerRuntime, WorkerTickStatus


async def test_fake_job_vertical_slice(tmp_path: Path) -> None:
    database_path = (tmp_path / "phase7-e2e.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    queue = PostgresJobQueue(session_factory)
    hub = RealtimeHub()
    publisher = OutboxPublisher(OutboxStore(session_factory), hub, worker_id="e2e-events")
    registry = JobHandlerRegistry()
    registry.register(FakeJobHandler())
    worker = WorkerRuntime(
        queue,
        registry,
        worker_id="e2e-worker",
        lease_s=30,
        heartbeat_interval_s=1,
        outbox_publisher=publisher,
    )
    app = create_app(
        Settings(environment="test", database_url=f"sqlite+aiosqlite:///{database_path}"),
        job_queue=queue,
        realtime_hub=hub,
    )
    subscription = await hub.subscribe()

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://v2.test",
        ) as client:
            accepted = await client.post(
                "/debug/jobs",
                json={"job_type": "debug.echo", "payload": {"message": "hello"}},
            )
            assert accepted.status_code == 202
            job_id = accepted.json()["job_id"]

            report = await worker.run_once()
            status = await client.get(f"/debug/jobs/{job_id}")
            realtime = await subscription.next(timeout_s=1)

        assert report.status == WorkerTickStatus.SUCCEEDED
        assert status.json()["status"] == "succeeded"
        assert status.json()["result"] == {
            "echo": {"message": "hello"},
            "handled": True,
        }
        assert realtime.event.event_type == "platform.job.succeeded"
        assert realtime.event.to_dict()["aggregate_id"] == job_id
    finally:
        await subscription.unsubscribe()
        await engine.dispose()
