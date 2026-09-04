"""Phase 7 reliability tests over the isolated SQL adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from windagent.kernel.ids import ActorId, CorrelationId, EntityId
from windagent.kernel.types.json import JSONValue
from windagent.platform.events import OutboxPublisher, OutboxStore
from windagent.platform.jobs import (
    DuplicateJobHandlerError,
    JobEnvelope,
    JobHandlerRegistry,
    JobResultValidationError,
    JobResultValidator,
    JobStatus,
    JobSubmission,
)
from windagent.platform.jobs.postgres import (
    CHECKPOINT_AFTER_JOB_STATE_WRITE,
    PostgresJobQueue,
)
from windagent.platform.modules import (
    InMemoryModuleRegistry,
    JobRegistration,
    ModuleLoader,
    ModuleManifest,
    StaticModuleDiscovery,
)
from windagent.platform.observability import InMemoryTelemetry, current_operation_context
from windagent.platform.persistence import metadata
from windagent.platform.realtime import RealtimeHub
from windagent_worker import (
    RetryPolicy,
    WorkerModuleRuntime,
    WorkerRuntime,
    WorkerTickStatus,
)

pytestmark = [pytest.mark.reliability]


@dataclass(slots=True)
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant

    def advance(self, seconds: float) -> None:
        self.instant += timedelta(seconds=seconds)


@pytest.fixture(name="job_runtime_db")
async def _job_runtime_db(
    tmp_path: Path,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], MutableClock]]:
    database_path = (tmp_path / "jobs.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    clock = MutableClock(datetime(2026, 9, 2, 0, 0, tzinfo=UTC))
    try:
        yield session_factory, clock
    finally:
        await engine.dispose()


class EchoHandler:
    @property
    def job_type(self) -> str:
        return "test.echo"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        return {"echo": payload["value"]}


class FlakyHandler:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def job_type(self) -> str:
        return "test.flaky"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        return {"calls": self.calls, "value": payload["value"]}


class SlowHandler:
    @property
    def job_type(self) -> str:
        return "test.slow"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        await asyncio.sleep(1)
        return dict(payload)


class BlockingHandler:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    @property
    def job_type(self) -> str:
        return "test.blocking"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        self.started.set()
        await asyncio.Event().wait()
        return dict(payload)


def _registry(*handlers: EchoHandler | FlakyHandler | SlowHandler | BlockingHandler) -> JobHandlerRegistry:
    registry = JobHandlerRegistry()
    for handler in handlers:
        registry.register(handler)
    return registry


def test_job_envelope_and_submission_freeze_the_json_boundary() -> None:
    raw = {"nested": [1, 2]}
    submission = JobSubmission(" test.echo ", raw, priority=4, max_attempts=2)
    raw["nested"] = [9]

    assert submission.job_type == "test.echo"
    assert submission.payload["nested"] == (1, 2)
    assert submission.priority == 4

    with pytest.raises(ValueError, match="max_attempts"):
        JobSubmission("test.echo", max_attempts=0)
    with pytest.raises(ValueError, match="timeout_s"):
        JobSubmission("test.echo", timeout_s=0)


def test_handler_registry_and_result_validation_are_single_owner() -> None:
    registry = _registry(EchoHandler())
    assert registry.require("test.echo").job_type == "test.echo"
    with pytest.raises(DuplicateJobHandlerError):
        registry.register(EchoHandler())
    with pytest.raises(JobResultValidationError):
        JobResultValidator().validate({"bad": object()})


def test_module_loader_registers_jobs_without_worker_bootstrap_edits() -> None:
    handlers = JobHandlerRegistry()
    runtime = WorkerModuleRuntime(handlers)
    manifest = ModuleManifest(
        id="example",
        version="1.0.0",
        jobs=(JobRegistration("test.echo", EchoHandler()),),
    )

    loaded = ModuleLoader(InMemoryModuleRegistry(), runtime).bootstrap(
        (StaticModuleDiscovery((manifest,)),)
    )

    assert loaded == (manifest,)
    assert handlers.require("test.echo").job_type == "test.echo"


async def test_two_workers_cannot_claim_the_same_job(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    receipt = await queue.submit(JobSubmission("test.echo", {"value": 1}))

    first = await queue.claim_next(worker_id="worker-a", lease_s=30)
    second = await queue.claim_next(worker_id="worker-b", lease_s=30)

    assert first is not None
    assert str(first.id) == str(receipt.job_id)
    assert second is None


async def test_job_trace_and_actor_round_trip_into_worker_telemetry_context(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    telemetry = InMemoryTelemetry("worker-test")
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    actor_id = ActorId.new()
    correlation_id = CorrelationId.new()

    class ContextHandler:
        @property
        def job_type(self) -> str:
            return "test.context"

        async def handle(self, payload: Mapping[str, JSONValue]) -> object:
            context = current_operation_context()
            assert context is not None
            return context.to_attributes()

    receipt = await queue.submit(
        JobSubmission(
            "test.context",
            trace_id=trace_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
    )
    runtime = WorkerRuntime(
        queue,
        _registry(ContextHandler()),  # type: ignore[arg-type]
        worker_id="worker-context",
        lease_s=10,
        heartbeat_interval_s=1,
        clock=clock,
        telemetry=telemetry,
    )

    report = await runtime.run_once()
    record = await queue.get(receipt.job_id)

    assert report.status == WorkerTickStatus.SUCCEEDED
    assert report.run_id is not None
    assert report.task_id is not None
    assert record is not None
    assert record.envelope.trace_id == trace_id
    assert record.envelope.actor_id == actor_id
    job_span = next(span for span in telemetry.spans if span.name == "worker.job.execute")
    assert job_span.attributes["trace_id"] == trace_id
    assert job_span.attributes["actor_id"] == str(actor_id)
    assert job_span.attributes["job_id"] == str(receipt.job_id)
    assert job_span.attributes["run_id"] == report.run_id
    assert job_span.attributes["task_id"] == report.task_id


async def test_priority_order_and_duplicate_submission(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    low = await queue.submit(JobSubmission("test.echo", {"value": "low"}, priority=1))
    high = await queue.submit(
        JobSubmission(
            "test.echo",
            {"value": "high"},
            priority=9,
            idempotency_key="same-request",
        )
    )
    duplicate = await queue.submit(
        JobSubmission(
            "test.echo",
            {"value": "different payload is ignored"},
            idempotency_key="same-request",
        )
    )

    claimed = await queue.claim_next(worker_id="worker", lease_s=30)
    assert claimed is not None and claimed.id == high.job_id
    assert duplicate.job_id == high.job_id
    assert duplicate.deduplicated is True
    assert low.job_id != high.job_id


async def test_lease_expiry_takeover_rejects_stale_finalize(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    receipt = await queue.submit(JobSubmission("test.echo", {"value": 1}))
    stale = await queue.claim_next(worker_id="worker-a", lease_s=5)
    assert stale is not None

    clock.advance(6)
    current = await queue.claim_next(worker_id="worker-b", lease_s=5)
    assert current is not None
    assert current.attempt == 2
    assert current.fencing_token != stale.fencing_token

    rejected = await queue.complete(stale, worker_id="worker-a", result={"stale": True})
    accepted = await queue.complete(current, worker_id="worker-b", result={"ok": True})
    record = await queue.get(receipt.job_id)

    assert rejected.accepted is False
    assert accepted.accepted is True
    assert record is not None and record.status == JobStatus.SUCCEEDED


async def test_worker_retries_then_succeeds(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    handler = FlakyHandler()
    runtime = WorkerRuntime(
        queue,
        _registry(handler),
        worker_id="worker",
        lease_s=10,
        heartbeat_interval_s=1,
        retry_policy=RetryPolicy(base_delay_s=2, max_delay_s=2),
        clock=clock,
    )
    receipt = await queue.submit(
        JobSubmission("test.flaky", {"value": "x"}, max_attempts=2)
    )

    first = await runtime.run_once()
    clock.advance(2)
    second = await runtime.run_once()
    record = await queue.get(receipt.job_id)

    assert first.status == WorkerTickStatus.RETRY_SCHEDULED
    assert second.status == WorkerTickStatus.SUCCEEDED
    assert record is not None and record.status == JobStatus.SUCCEEDED
    assert record.envelope.attempt == 2


async def test_timeout_is_durable_and_stops_the_handler(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    runtime = WorkerRuntime(
        queue,
        _registry(SlowHandler()),
        worker_id="worker",
        lease_s=0.1,
        heartbeat_interval_s=0.005,
        clock=clock,
    )
    receipt = await queue.submit(
        JobSubmission("test.slow", {}, max_attempts=1, timeout_s=0.02)
    )

    report = await runtime.run_once()
    record = await queue.get(receipt.job_id)

    assert report.status == WorkerTickStatus.FAILED
    assert record is not None and record.status == JobStatus.FAILED
    assert record.error == "job execution timed out"


async def test_running_cancellation_interrupts_and_finalizes(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    handler = BlockingHandler()
    runtime = WorkerRuntime(
        queue,
        _registry(handler),
        worker_id="worker",
        lease_s=0.2,
        heartbeat_interval_s=0.01,
        clock=clock,
    )
    receipt = await queue.submit(JobSubmission("test.blocking", {}))

    running = asyncio.create_task(runtime.run_once())
    await handler.started.wait()
    assert await queue.request_cancel(receipt.job_id) is True
    requested = await queue.get(receipt.job_id)
    assert requested is not None and requested.cancellation_requested is True
    report = await asyncio.wait_for(running, timeout=1)
    record = await queue.get(receipt.job_id)

    assert report.status == WorkerTickStatus.CANCELLED
    assert record is not None and record.status == JobStatus.CANCELLED


async def test_server_and_worker_restart_recover_durable_state(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    first_process = PostgresJobQueue(session_factory, clock=clock)
    receipt = await first_process.submit(JobSubmission("test.echo", {"value": "restart"}))
    crashed_claim = await first_process.claim_next(worker_id="crashed", lease_s=3)
    assert crashed_claim is not None

    clock.advance(4)
    restarted_queue = PostgresJobQueue(session_factory, clock=clock)
    restarted_worker = WorkerRuntime(
        restarted_queue,
        _registry(EchoHandler()),
        worker_id="restarted",
        lease_s=10,
        heartbeat_interval_s=1,
        clock=clock,
    )
    report = await restarted_worker.run_once()
    record = await restarted_queue.get(receipt.job_id)

    assert report.status == WorkerTickStatus.SUCCEEDED
    assert report.attempt == 2
    assert record is not None and record.status == JobStatus.SUCCEEDED


async def test_recovery_finalizes_exhausted_and_cancelled_crashed_claims(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    exhausted_receipt = await queue.submit(
        JobSubmission("test.echo", {"value": "exhausted"}, max_attempts=1)
    )
    exhausted = await queue.claim_next(worker_id="crashed-a", lease_s=2)
    assert exhausted is not None

    cancelled_receipt = await queue.submit(
        JobSubmission("test.echo", {"value": "cancelled"})
    )
    cancelled = await queue.claim_next(worker_id="crashed-b", lease_s=2)
    assert cancelled is not None
    assert await queue.request_cancel(cancelled_receipt.job_id) is True

    clock.advance(3)
    assert await queue.recover_expired() == 2
    exhausted_record = await queue.get(exhausted_receipt.job_id)
    cancelled_record = await queue.get(cancelled_receipt.job_id)

    assert exhausted_record is not None and exhausted_record.status == JobStatus.FAILED
    assert cancelled_record is not None and cancelled_record.status == JobStatus.CANCELLED


async def test_atomic_finalize_rolls_back_job_and_outbox_on_crash_gate(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db

    def crash(name: str) -> None:
        if name == CHECKPOINT_AFTER_JOB_STATE_WRITE:
            raise RuntimeError("simulated crash")

    queue = PostgresJobQueue(session_factory, clock=clock, checkpoint_hook=crash)
    receipt = await queue.submit(JobSubmission("test.echo", {"value": 1}))
    claimed = await queue.claim_next(worker_id="worker", lease_s=30)
    assert claimed is not None

    with pytest.raises(RuntimeError, match="simulated crash"):
        await queue.complete(claimed, worker_id="worker", result={"ok": True})
    record = await queue.get(receipt.job_id)
    counts = await OutboxStore(session_factory, clock=clock).count_by_status()

    assert record is not None and record.status == JobStatus.RUNNING
    assert counts == {}


async def test_fake_job_flows_through_outbox_to_realtime(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    hub = RealtimeHub()
    publisher = OutboxPublisher(
        OutboxStore(session_factory, clock=clock),
        hub,
        worker_id="events",
        clock=clock,
    )
    runtime = WorkerRuntime(
        queue,
        _registry(EchoHandler()),
        worker_id="worker",
        lease_s=30,
        heartbeat_interval_s=1,
        outbox_publisher=publisher,
        clock=clock,
    )
    receipt = await queue.submit(JobSubmission("test.echo", {"value": "hello"}))
    subscription = await hub.subscribe()

    report = await runtime.run_once()
    message = await subscription.next(timeout_s=1)
    await subscription.unsubscribe()

    assert report.status == WorkerTickStatus.SUCCEEDED
    assert report.outbox_published == 1
    assert message.event.event_type == "platform.job.succeeded"
    assert message.event.aggregate_id == receipt.job_id


async def test_queued_cancellation_is_idempotent(
    job_runtime_db: tuple[async_sessionmaker[AsyncSession], MutableClock],
) -> None:
    session_factory, clock = job_runtime_db
    queue = PostgresJobQueue(session_factory, clock=clock)
    receipt = await queue.submit(JobSubmission("test.echo"))

    assert await queue.request_cancel(receipt.job_id) is True
    assert await queue.request_cancel(receipt.job_id) is True
    assert await queue.claim_next(worker_id="worker", lease_s=10) is None
    record = await queue.get(receipt.job_id)
    assert record is not None and record.status == JobStatus.CANCELLED


def test_job_envelope_rejects_attempt_beyond_limit() -> None:
    with pytest.raises(ValueError, match="attempt cannot exceed"):
        JobEnvelope(
            id=EntityId.new(),
            job_type="test.echo",
            version=JobSubmission("test.echo").version,
            attempt=2,
            max_attempts=1,
        )
