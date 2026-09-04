"""Phase 6 unit tests: outbox claim/finalize store semantics."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now
from windagent.platform.events import (
    OUTBOX_STATUS_DEAD_LETTER,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    OUTBOX_STATUS_PUBLISHING,
    OutboxStore,
    TransactionalOutbox,
    outbox_table,
)
from windagent.platform.persistence import SqlUnitOfWork
from windagent.platform.persistence.metadata import metadata


def make_envelope(aggregate_id: EntityId | None = None) -> EventEnvelope:
    return EventEnvelope(
        event_type="studio.episode.planned",
        aggregate_type="episode",
        aggregate_id=aggregate_id or EntityId.new(),
        sequence=0,
        payload={"title": "ep1"},
    )


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def seed_stream(
    session_factory: async_sessionmaker[AsyncSession],
    count: int = 3,
) -> list[str]:
    """Record ``count`` events of one aggregate stream (seq 0..count-1).

    Returns the event ids in stream order.
    """
    aggregate = EntityId.new()
    ids: list[str] = []
    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        outbox = TransactionalOutbox(unit_of_work)
        for _ in range(count):
            envelope = make_envelope(aggregate_id=aggregate)
            await outbox.record_next(envelope)
            ids.append(str(envelope.event_id))
        await unit_of_work.commit()
    return ids


async def _outbox_row(
    session_factory: async_sessionmaker[AsyncSession], event_id: str
) -> Any:
    async with session_factory() as session:
        return cast(
            "Any",
            (
                await session.execute(
                    select(outbox_table).where(
                        outbox_table.c.event_id == event_id
                    )
                )
            ).one(),
        )


async def _set_available_at(
    session_factory: async_sessionmaker[AsyncSession], event_id: str, when: datetime
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(outbox_table)
            .where(outbox_table.c.event_id == event_id)
            .values(available_at=when)
        )
        await session.commit()


async def test_claim_batch_returns_pending_records_with_lease(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = await seed_stream(session_factory)

    store = OutboxStore(session_factory)
    claimed = await store.claim_batch(worker_id="worker-1", limit=10, lease_s=30.0)

    assert [record.event_id.value for record in claimed] == event_ids  # stream order
    for record in claimed:
        assert record.status == OUTBOX_STATUS_PUBLISHING
        assert record.claimed_by == "worker-1"
        assert record.claim_token is not None
        assert record.claim_expires_at is not None

    async with session_factory() as session:
        statuses = (
            (await session.execute(select(outbox_table.c.status))).scalars().all()
        )
    assert set(statuses) == {OUTBOX_STATUS_PUBLISHING}


async def test_claim_batch_is_exclusive_and_respects_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_stream(session_factory, count=3)

    store = OutboxStore(session_factory)
    first = await store.claim_batch(worker_id="worker-1", limit=2)
    second = await store.claim_batch(worker_id="worker-2", limit=2)
    third = await store.claim_batch(worker_id="worker-3", limit=2)

    assert len(first) == 2
    assert len(second) == 1
    assert third == ()
    assert {record.claimed_by for record in first} == {"worker-1"}


async def test_claim_batch_skips_future_available_records(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = await seed_stream(session_factory, count=1)

    await _set_available_at(
        session_factory, event_ids[0], utc_now() + timedelta(hours=1)
    )

    store = OutboxStore(session_factory)
    claimed = await store.claim_batch(worker_id="worker-1")

    assert claimed == ()


async def test_mark_published_requires_the_claim_token(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = await seed_stream(session_factory, count=1)
    store = OutboxStore(session_factory)
    (record,) = await store.claim_batch(worker_id="worker-1")

    assert record.claim_token is not None
    wrong_token = await store.mark_published(
        record.id, claim_token=str(uuid.uuid4())
    )
    assert wrong_token is False

    published = await store.mark_published(record.id, claim_token=record.claim_token)
    assert published is True

    row = await _outbox_row(session_factory, event_ids[0])
    assert row.status == OUTBOX_STATUS_PUBLISHED
    assert row.published_at is not None
    assert row.claim_token is None


async def test_mark_failed_retries_then_dead_letters(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = await seed_stream(session_factory, count=1)
    store = OutboxStore(session_factory)

    for attempt in range(4):  # attempts 1..4 go back to pending
        (record,) = await store.claim_batch(worker_id="worker-1")
        assert record.claim_token is not None
        finalized = await store.mark_failed(
            record.id,
            claim_token=record.claim_token,
            error=f"boom {attempt}",
            max_attempts=5,
            backoff_s=0.0,
        )
        assert finalized is True
        row = await _outbox_row(session_factory, event_ids[0])
        assert row.status == OUTBOX_STATUS_PENDING
        assert row.attempt_count == attempt + 1
        assert row.last_error == f"boom {attempt}"

    (record,) = await store.claim_batch(worker_id="worker-1")
    assert record.claim_token is not None
    finalized = await store.mark_failed(
        record.id,
        claim_token=record.claim_token,
        error="boom final",
        max_attempts=5,
        backoff_s=0.0,
    )
    assert finalized is True

    row = await _outbox_row(session_factory, event_ids[0])
    assert row.status == OUTBOX_STATUS_DEAD_LETTER
    assert row.attempt_count == 5


async def test_stale_claim_cannot_finalize(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = await seed_stream(session_factory, count=1)
    store = OutboxStore(session_factory)

    (first,) = await store.claim_batch(worker_id="worker-1", lease_s=0.01)
    await asyncio.sleep(0.05)
    await store.reclaim_expired_claims()
    (second,) = await store.claim_batch(worker_id="worker-2")

    assert first.claim_token != second.claim_token
    assert (
        await store.mark_published(first.id, claim_token=first.claim_token or "")
        is False
    )
    assert (
        await store.mark_published(first.id, claim_token=second.claim_token or "")
        is True
    )
    row = await _outbox_row(session_factory, event_ids[0])
    assert row.status == OUTBOX_STATUS_PUBLISHED


async def test_reclaim_expired_claims_returns_records_to_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_stream(session_factory, count=2)
    store = OutboxStore(session_factory)

    (first,) = await store.claim_batch(worker_id="worker-1", limit=1, lease_s=0.01)
    (second,) = await store.claim_batch(worker_id="worker-1", limit=1, lease_s=30.0)
    assert first.id != second.id

    await asyncio.sleep(0.05)
    reclaimed = await store.reclaim_expired_claims()

    assert reclaimed == 1
    row = await _outbox_row(session_factory, first.event_id.value)
    assert row.status == OUTBOX_STATUS_PENDING


async def test_count_by_status_reports_distribution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_stream(session_factory, count=2)
    store = OutboxStore(session_factory)
    (record,) = await store.claim_batch(worker_id="worker-1", limit=1)
    assert record.claim_token is not None
    await store.mark_published(record.id, claim_token=record.claim_token)

    counts = await store.count_by_status()

    assert counts == {
        OUTBOX_STATUS_PENDING: 1,
        OUTBOX_STATUS_PUBLISHED: 1,
    }
