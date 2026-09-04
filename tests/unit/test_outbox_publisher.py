"""Phase 6 unit tests: outbox publisher drain loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.platform.events import (
    OUTBOX_STATUS_DEAD_LETTER,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    OutboxPublisher,
    OutboxStore,
    PublishReport,
    TransactionalOutbox,
    outbox_table,
)
from windagent.platform.persistence import SqlUnitOfWork
from windagent.platform.persistence.metadata import metadata


class TransportPublisher:
    """Fake delivery transport implementing the EventPublisher contract."""

    def __init__(self, failures: dict[str, int] | None = None) -> None:
        self.delivered: list[EventEnvelope] = []
        self.failures = failures or {}

    async def publish(self, event: EventEnvelope) -> None:
        remaining = self.failures.get(event.event_type, 0)
        if remaining > 0:
            self.failures[event.event_type] = remaining - 1
            raise RuntimeError(f"transport down for {event.event_type}")
        self.delivered.append(event)


def make_envelope(event_type: str = "studio.episode.planned") -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
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


async def seed_one(
    session_factory: async_sessionmaker[AsyncSession],
    event_type: str = "studio.episode.planned",
) -> str:
    envelope = make_envelope(event_type)
    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(envelope)
        await unit_of_work.commit()
    return str(envelope.event_id)


async def _outbox_row(
    session_factory: async_sessionmaker[AsyncSession], event_id: str
) -> Any:
    async with session_factory() as session:
        return (
            await session.execute(
                select(outbox_table).where(outbox_table.c.event_id == event_id)
            )
        ).one()


async def test_publisher_drains_claimed_records(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = [await seed_one(session_factory) for _ in range(2)]
    transport = TransportPublisher()
    publisher = OutboxPublisher(OutboxStore(session_factory), transport)

    report = await publisher.publish_pending()

    assert report == PublishReport(claimed=2, published=2, retried=0, dead_lettered=0)
    assert sorted(envelope.event_id.value for envelope in transport.delivered) == sorted(
        event_ids
    )

    async with session_factory() as session:
        statuses = (await session.execute(select(outbox_table.c.status))).scalars().all()
    assert set(statuses) == {OUTBOX_STATUS_PUBLISHED}


async def test_publisher_restores_envelope_causality(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from windagent.kernel.ids import ActorId, CausationId, CorrelationId

    envelope = EventEnvelope(
        event_type="studio.episode.planned",
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
        sequence=3,
        payload={"title": "ep1"},
        actor_id=ActorId.new(),
        correlation_id=CorrelationId.new(),
        causation_id=CausationId.new(),
    )
    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(envelope)
        await unit_of_work.commit()

    transport = TransportPublisher()
    await OutboxPublisher(OutboxStore(session_factory), transport).publish_pending()

    delivered = transport.delivered[0]
    assert delivered.event_id == envelope.event_id
    assert delivered.sequence == 3
    assert delivered.actor_id == envelope.actor_id
    assert delivered.correlation_id == envelope.correlation_id
    assert delivered.causation_id == envelope.causation_id
    assert delivered.payload == envelope.payload


async def test_failed_delivery_is_retried_then_published(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = await seed_one(session_factory)
    transport = TransportPublisher(failures={"studio.episode.planned": 1})
    publisher = OutboxPublisher(
        OutboxStore(session_factory),
        transport,
        backoff_s=0.0,
    )

    first = await publisher.publish_pending()
    assert first == PublishReport(claimed=1, published=0, retried=1, dead_lettered=0)

    row = await _outbox_row(session_factory, event_id)
    assert row.status == OUTBOX_STATUS_PENDING
    assert row.attempt_count == 1
    assert "transport down" in row.last_error

    second = await publisher.publish_pending()
    assert second == PublishReport(claimed=1, published=1, retried=0, dead_lettered=0)
    assert len(transport.delivered) == 1


async def test_max_attempts_moves_record_to_dead_letter(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = await seed_one(session_factory)
    dead_letters: list[str] = []
    transport = TransportPublisher(failures={"studio.episode.planned": 99})
    publisher = OutboxPublisher(
        OutboxStore(session_factory),
        transport,
        max_attempts=2,
        backoff_s=0.0,
        on_dead_letter=lambda record: dead_letters.append(record.event_id.value),
    )

    first = await publisher.publish_pending()
    assert first.retried == 1
    second = await publisher.publish_pending()
    assert second.dead_lettered == 1

    row = await _outbox_row(session_factory, event_id)
    assert row.status == OUTBOX_STATUS_DEAD_LETTER
    assert row.attempt_count == 2
    assert dead_letters == [event_id]

    # Dead-lettered records are never claimed again.
    third = await publisher.publish_pending()
    assert third.idle is True


async def test_run_exits_when_stop_is_set(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transport = TransportPublisher()
    publisher = OutboxPublisher(OutboxStore(session_factory), transport)
    stop = asyncio.Event()
    stop.set()

    total = await publisher.run(interval_s=0.01, stop=stop)

    assert total == 0


async def test_run_drains_until_stopped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = await seed_one(session_factory)
    transport = TransportPublisher()
    store = OutboxStore(session_factory)
    publisher = OutboxPublisher(store, transport)
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.2, stop.set)

    total = await publisher.run(interval_s=0.05, stop=stop)

    assert total == 1
    row = await _outbox_row(session_factory, event_id)
    assert row.status == OUTBOX_STATUS_PUBLISHED
