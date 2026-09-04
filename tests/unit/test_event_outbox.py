"""Phase 6 unit tests: transactional outbox on isolated databases."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import ActorId, CausationId, CorrelationId, EntityId
from windagent.kernel.time import utc_now
from windagent.platform.events import (
    CHECKPOINT_AFTER_EVENT_WRITE,
    OUTBOX_STATUS_PENDING,
    TransactionalOutbox,
    outbox_table,
)
from windagent.platform.events.outbox import events_table
from windagent.platform.persistence import SqlUnitOfWork, UnitOfWorkNotActiveError
from windagent.platform.persistence.metadata import metadata


def make_envelope(**overrides: Any) -> EventEnvelope:
    values: dict[str, Any] = {
        "event_type": "studio.episode.planned",
        "aggregate_type": "episode",
        "aggregate_id": EntityId.new(),
        "sequence": 0,
        "payload": {"title": "ep1"},
    }
    values.update(overrides)
    return EventEnvelope(**values)


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


async def _scalar(
    session_factory: async_sessionmaker[AsyncSession], statement: Any
) -> Any:
    async with session_factory() as session:
        return (await session.execute(statement)).scalar()


async def _count(
    session_factory: async_sessionmaker[AsyncSession], table: Table
) -> int:
    result = await _scalar(session_factory, select(func.count()).select_from(table))
    return int(result)


async def test_record_appends_event_store_and_outbox_in_one_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        outbox = TransactionalOutbox(unit_of_work)
        recorded = await outbox.record(make_envelope())
        await unit_of_work.commit()

    assert recorded is True
    assert await _count(session_factory, events_table) == 1
    assert await _count(session_factory, outbox_table) == 1

    async with session_factory() as session:
        event_row = (await session.execute(select(events_table))).one()
        outbox_row = (await session.execute(select(outbox_table))).one()
    assert event_row.event_type == "studio.episode.planned"
    assert event_row.payload_json == '{"title": "ep1"}'
    assert outbox_row.status == OUTBOX_STATUS_PENDING
    assert outbox_row.attempt_count == 0
    assert outbox_row.deduplication_key is None


async def test_record_persists_causal_identifiers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    envelope = make_envelope(
        actor_id=ActorId.new(),
        correlation_id=CorrelationId.new(),
        causation_id=CausationId.new(),
    )

    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(envelope)
        await unit_of_work.commit()

    async with session_factory() as session:
        event_row = (await session.execute(select(events_table))).one()
    assert event_row.actor_id == str(envelope.actor_id)
    assert event_row.correlation_id == str(envelope.correlation_id)
    assert event_row.causation_id == str(envelope.causation_id)


async def test_deduplication_key_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    envelope = make_envelope()

    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        outbox = TransactionalOutbox(unit_of_work)
        first = await outbox.record(envelope, deduplication_key="finalize:job-1")
        second = await outbox.record(make_envelope(), deduplication_key="finalize:job-1")
        await unit_of_work.commit()

    assert first is True
    assert second is False
    assert await _count(session_factory, events_table) == 1
    assert await _count(session_factory, outbox_table) == 1


async def test_crash_gate_fires_between_event_and_outbox_write(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seen: list[str] = []
    unit_of_work = SqlUnitOfWork(
        session_factory, checkpoint_hook=lambda name: seen.append(name)
    )
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(make_envelope())
        await unit_of_work.commit()

    assert seen == [CHECKPOINT_AFTER_EVENT_WRITE, "before_commit"]


async def test_checkpoint_failure_rolls_back_both_writes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    def crash_gate(name: str) -> None:
        raise RuntimeError(f"crash at {name}")

    unit_of_work = SqlUnitOfWork(session_factory, checkpoint_hook=crash_gate)
    with pytest.raises(RuntimeError, match="crash at"):
        async with unit_of_work:
            await TransactionalOutbox(unit_of_work).record(make_envelope())
            await unit_of_work.commit()

    assert await _count(session_factory, events_table) == 0
    assert await _count(session_factory, outbox_table) == 0


async def test_rollback_discards_event_and_outbox(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(make_envelope())
        await unit_of_work.rollback()

    assert await _count(session_factory, events_table) == 0
    assert await _count(session_factory, outbox_table) == 0


async def test_record_outside_unit_of_work_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    outbox = TransactionalOutbox(SqlUnitOfWork(session_factory))

    with pytest.raises(UnitOfWorkNotActiveError):
        await outbox.record(make_envelope())


async def test_record_next_allocates_per_stream(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    aggregate = EntityId.new()
    other = EntityId.new()

    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        outbox = TransactionalOutbox(unit_of_work)
        await outbox.record_next(make_envelope(aggregate_id=aggregate))
        await outbox.record_next(make_envelope(aggregate_id=aggregate))
        await outbox.record_next(make_envelope(aggregate_id=other))
        await unit_of_work.commit()

    async with session_factory() as session:
        rows = (await session.execute(
            select(events_table.c.aggregate_id, events_table.c.sequence).order_by(
                events_table.c.aggregate_id, events_table.c.sequence
            )
        )).all()
    sequences = {
        aggregate_id: [int(row.sequence) for row in rows if row.aggregate_id == aggregate_id]
        for aggregate_id in {str(aggregate), str(other)}
    }
    assert sequences[str(aggregate)] == [0, 1]
    assert sequences[str(other)] == [0]
    assert await _count(session_factory, events_table) == 3


async def test_stream_sequence_conflict_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from sqlalchemy.exc import IntegrityError

    aggregate = EntityId.new()

    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work).record(make_envelope(aggregate_id=aggregate))
        await unit_of_work.commit()

    unit_of_work = SqlUnitOfWork(session_factory)
    with pytest.raises(IntegrityError):
        async with unit_of_work:
            await TransactionalOutbox(unit_of_work).record(
                make_envelope(aggregate_id=aggregate)
            )
            await unit_of_work.commit()


async def test_clock_controls_record_timestamps(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from windagent.kernel.time import FrozenClock
    from windagent.platform.events.outbox import as_utc

    frozen = FrozenClock(utc_now())
    unit_of_work = SqlUnitOfWork(session_factory)
    async with unit_of_work:
        await TransactionalOutbox(unit_of_work, clock=frozen).record(make_envelope())
        await unit_of_work.commit()

    async with session_factory() as session:
        row = (await session.execute(select(outbox_table))).one()
    assert as_utc(row.created_at) == frozen.now()
    assert as_utc(row.available_at) == frozen.now()
