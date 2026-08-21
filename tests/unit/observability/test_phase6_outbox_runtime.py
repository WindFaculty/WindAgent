"""Unit tests for Phase 6 — Outbox Runtime (Publisher, Retry, Replay & Shutdown Drain)."""

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import BaseORM, OutboxRecordORM, OutboxReplayAuditORM
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_observability.events.publisher import OutboxEventPublisher
from windagent_observability.events.dead_letter import DeadLetterReplayer
from windagent_observability.events.retry import NonRetryablePublicationError


@pytest.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


def _sample_record(event_id: str | None = None, aggregate_id: str = "agg-1") -> OutboxRecord:
    evt_id = event_id or str(uuid.uuid4())
    return OutboxRecord(
        id=f"outbox_{uuid.uuid4().hex[:12]}",
        event_id=evt_id,
        aggregate_id=aggregate_id,
        aggregate_type="task",
        event_type="TaskStatusUpdated",
        payload_json='{"status": "completed"}',
        schema_version="1.0",
        sequence_number=1,
        created_at=datetime.now(timezone.utc),
        available_at=datetime.now(timezone.utc),
        status="pending",
    )


@pytest.mark.asyncio
async def test_outbox_publisher_claims_and_publishes(session_factory):
    """Pending outbox record is claimed, dispatched, and marked published."""
    repo = SqlOutboxRepository(session_factory)
    record = _sample_record()
    await repo.save(record)

    dispatched = []

    def mock_dispatcher(env: EventEnvelope):
        dispatched.append(env)

    publisher = OutboxEventPublisher(
        outbox_repo=repo,
        dispatcher=mock_dispatcher,
        batch_size=10,
        publisher_id="worker-node-1",
    )

    published_count = await publisher.publish_pending()
    assert published_count == 1
    assert len(dispatched) == 1
    assert str(dispatched[0].event_id) == record.event_id

    counts = await repo.get_status_counts()
    assert counts["published"] == 1
    assert counts["pending"] == 0
    assert publisher.heartbeat.pending_count == 0
    assert publisher.heartbeat.last_success_at is not None


@pytest.mark.asyncio
async def test_outbox_publisher_transient_error_retries(session_factory):
    """Transient exception keeps record in pending/failed with exponential backoff."""
    repo = SqlOutboxRepository(session_factory)
    rec = _sample_record()
    await repo.save(rec)

    def failing_dispatcher(env: EventEnvelope):
        raise ConnectionError("Temporary network glitch")

    publisher = OutboxEventPublisher(
        outbox_repo=repo,
        dispatcher=failing_dispatcher,
        max_attempts=3,
        publisher_id="worker-node-1",
    )

    published_count = await publisher.publish_pending()
    assert published_count == 0

    # Record should remain pending (or failed retry available later)
    async with session_factory() as session:
        res = await session.execute(select(OutboxRecordORM).where(OutboxRecordORM.event_id == rec.event_id))
        orm = res.scalar_one()
        assert orm.status == "pending"
        assert orm.attempt_count == 1
        assert "Temporary network glitch" in (orm.last_error or "")


@pytest.mark.asyncio
async def test_outbox_publisher_non_retryable_error_dead_letters(session_factory):
    """Non-retryable exception immediately routes to dead_letter."""
    repo = SqlOutboxRepository(session_factory)
    rec = _sample_record()
    await repo.save(rec)

    def poison_dispatcher(env: EventEnvelope):
        raise NonRetryablePublicationError("Invalid schema payload")

    publisher = OutboxEventPublisher(
        outbox_repo=repo,
        dispatcher=poison_dispatcher,
        max_attempts=5,
        publisher_id="worker-node-1",
    )

    published_count = await publisher.publish_pending()
    assert published_count == 0

    counts = await repo.get_status_counts()
    assert counts["dead_letter"] == 1

    async with session_factory() as session:
        res = await session.execute(select(OutboxRecordORM).where(OutboxRecordORM.event_id == rec.event_id))
        orm = res.scalar_one()
        assert orm.status == "dead_letter"
        assert "Invalid schema payload" in (orm.last_error or "")


@pytest.mark.asyncio
async def test_dead_letter_replay_audited(session_factory):
    """DeadLetterReplayer queues record back to pending and records replay audit log."""
    repo = SqlOutboxRepository(session_factory)
    rec = _sample_record()
    await repo.save(rec)

    # Force record to dead_letter state
    async with session_factory() as session:
        res = await session.execute(select(OutboxRecordORM).where(OutboxRecordORM.event_id == rec.event_id))
        orm = res.scalar_one()
        orm.status = "dead_letter"
        orm.attempt_count = 5
        orm.last_error = "Permanent failure"
        await session.commit()

    replayer = DeadLetterReplayer(repo)
    dead_letters = await replayer.list_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0].event_id == rec.event_id

    replayed = await replayer.replay(rec.event_id, operator="admin@windagent.local")
    assert replayed is not None
    assert replayed.status == "pending"

    # Verify attempt_count and last_error are preserved (not silently wiped)
    assert replayed.attempt_count == 5

    # Check audit log in DB
    async with session_factory() as session:
        res_audit = await session.execute(
            select(OutboxReplayAuditORM).where(OutboxReplayAuditORM.event_id == rec.event_id)
        )
        audit = res_audit.scalar_one_or_none()
        assert audit is not None
        assert audit.operator == "admin@windagent.local"
        assert audit.previous_status == "dead_letter"


@pytest.mark.asyncio
async def test_publisher_shutdown_drain(session_factory):
    """Publisher stop(drain=True) processes all pending records before stopping."""
    repo = SqlOutboxRepository(session_factory)
    r1 = _sample_record()
    r2 = _sample_record()
    await repo.save(r1)
    await repo.save(r2)

    dispatched = []

    def mock_dispatcher(env: EventEnvelope):
        dispatched.append(env)

    publisher = OutboxEventPublisher(
        outbox_repo=repo,
        dispatcher=mock_dispatcher,
        batch_size=10,
        publisher_id="worker-node-1",
    )

    await publisher.start()
    assert publisher.is_running
    assert publisher.heartbeat.state == "running"

    await publisher.stop(drain=True)
    assert not publisher.is_running
    assert publisher.heartbeat.state == "stopped"
    assert len(dispatched) == 2
