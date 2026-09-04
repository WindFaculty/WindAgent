"""Durable outbox-backed audit sink contracts."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from windagent.kernel.ids import ActorId
from windagent.platform.events import outbox_table
from windagent.platform.events.outbox import events_table
from windagent.platform.persistence import Database
from windagent.platform.persistence.metadata import metadata
from windagent.platform.security import AuditEvent, InMemoryAuditSink, PolicyEffect
from windagent_api.bootstrap import AUDIT_EVENT_TYPE, OutboxAuditSink


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    database = Database(engine, session_factory, "sqlite+aiosqlite:///:memory:")
    yield database
    await engine.dispose()


def _event() -> AuditEvent:
    return AuditEvent(
        action="job:submit",
        resource_type="job",
        outcome=PolicyEffect.DENY.value,
        actor_id=ActorId.new(),
        reason="frozen",
        details={"policy_id": "default-deny"},
    )


async def _count(database: Database, table: Table) -> int:
    session_factory = database.session_factory
    async with session_factory() as session:
        result = await session.execute(select(func.count()).select_from(table))
        value = result.scalar()
        return int(value) if value is not None else 0


async def test_recorded_audit_events_land_in_event_store_and_outbox(
    database: Database,
) -> None:
    sink = OutboxAuditSink(database)
    event = _event()
    await sink.record(event)
    assert await _count(database, events_table) == 1
    assert await _count(database, outbox_table) == 1


async def test_audit_recording_is_idempotent_per_event(database: Database) -> None:
    sink = OutboxAuditSink(database)
    event = _event()
    await sink.record(event)
    await sink.record(event)
    assert await _count(database, events_table) == 1
    assert await _count(database, outbox_table) == 1


async def test_recorded_audit_payload_round_trips(database: Database) -> None:
    sink = OutboxAuditSink(database)
    event = _event()
    await sink.record(event)
    session_factory = database.session_factory
    async with session_factory() as session:
        row = (await session.execute(select(events_table))).one()
    assert row.event_type == AUDIT_EVENT_TYPE
    assert row.actor_id == str(event.actor_id)
    payload = json.loads(row.payload_json)
    assert payload["action"] == "job:submit"
    assert payload["outcome"] == "deny"


async def test_sink_rejects_non_events(database: Database) -> None:
    sink = OutboxAuditSink(database)
    with pytest.raises(TypeError):
        await sink.record("not-an-event")  # type: ignore[arg-type]


async def test_in_memory_sink_satisfies_the_same_contract() -> None:
    sink: InMemoryAuditSink = InMemoryAuditSink()
    event = _event()
    await sink.record(event)
    assert sink.events[0].action == "job:submit"
