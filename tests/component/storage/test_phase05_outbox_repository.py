"""Phase 5 Unit Tests: Outbox Repository Contract & Transaction Semantics.

Validates dual-mode SqlOutboxRepository (session vs session_factory),
transactional append, rollback safety, get_pending filtering, and status updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM, OutboxRecordORM
from windagent_storage.orm.v2_orchestration_models import TaskRunORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.sql_repository import SqlOutboxRepository


@pytest.fixture
async def db_manager():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        yield db
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_outbox_repository_instantiation_with_session_factory(db_manager):
    """SqlOutboxRepository instantiated with session_factory works without crash (Publisher mode)."""
    repo = SqlOutboxRepository(db_manager.session_factory)
    rec = OutboxRecord(
        id=f"out_{uuid.uuid4().hex[:8]}",
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        aggregate_id="agg_1",
        aggregate_type="task",
        event_type="TestCreated",
        payload_json='{"key": "val"}',
        status="pending",
    )

    await repo.save(rec)

    pending = await repo.get_pending(limit=10)
    assert len(pending) == 1
    assert pending[0].id == rec.id


@pytest.mark.asyncio
async def test_outbox_repository_instantiation_with_session(db_manager):
    """SqlOutboxRepository instantiated with AsyncSession works within active session (UOW mode)."""
    async with db_manager.session_factory() as session:
        async with session.begin():
            repo = SqlOutboxRepository(session)
            rec = OutboxRecord(
                id=f"out_{uuid.uuid4().hex[:8]}",
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                aggregate_id="agg_2",
                aggregate_type="task",
                event_type="TestCreated",
                payload_json='{"key": "val"}',
                status="pending",
            )
            await repo.save(rec)

        # Query back
        pending = await repo.get_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].id == rec.id


@pytest.mark.asyncio
async def test_transactional_append_commits_both_records(db_manager):
    """Domain record (TaskRunORM) and outbox record commit together in a single transaction."""
    task_id = f"tsk_{uuid.uuid4().hex[:8]}"
    outbox_id = f"out_{uuid.uuid4().hex[:8]}"
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    async with db_manager.session_factory() as session:
        async with session.begin():
            # Add domain record
            task_orm = TaskRunORM(
                id=task_id,
                session_id="sess_01",
                state="pending",
                created_at=now_naive,
                updated_at=now_naive,
            )
            session.add(task_orm)

            # Add outbox record using SqlOutboxRepository
            repo = SqlOutboxRepository(session)
            rec = OutboxRecord(
                id=outbox_id,
                event_id=f"evt_{task_id}",
                aggregate_id=task_id,
                aggregate_type="task",
                event_type="TaskSubmitted",
                payload_json='{"prompt": "Transactional test"}',
                status="pending",
            )
            await repo.save(rec)

    # Verify both records persist
    async with db_manager.session_factory() as session:
        res_task = await session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        assert res_task.scalar_one_or_none() is not None

        res_outbox = await session.execute(select(OutboxRecordORM).where(OutboxRecordORM.id == outbox_id))
        assert res_outbox.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_transactional_append_rollback_leaves_zero_records(db_manager):
    """Transaction rollback leaves zero records in both domain and outbox tables."""
    task_id = f"tsk_rollback_{uuid.uuid4().hex[:6]}"
    outbox_id = f"out_rollback_{uuid.uuid4().hex[:6]}"
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        async with db_manager.session_factory() as session:
            async with session.begin():
                session.add(TaskRunORM(id=task_id, session_id="s1", state="pending", created_at=now_naive, updated_at=now_naive))
                repo = SqlOutboxRepository(session)
                await repo.save(OutboxRecord(
                    id=outbox_id,
                    event_id="evt_rb",
                    aggregate_id=task_id,
                    aggregate_type="task",
                    event_type="TaskSubmitted",
                    payload_json="{}",
                    status="pending",
                ))
                raise RuntimeError("Simulated transaction failure!")
    except RuntimeError:
        pass

    # Verify zero records created
    async with db_manager.session_factory() as session:
        res_task = await session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        assert res_task.scalar_one_or_none() is None

        res_outbox = await session.execute(select(OutboxRecordORM).where(OutboxRecordORM.id == outbox_id))
        assert res_outbox.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_get_pending_filters_by_available_at(db_manager):
    """get_pending() only returns records where status == 'pending' and available_at <= now."""
    repo = SqlOutboxRepository(db_manager.session_factory)
    now = datetime.now(timezone.utc)

    rec_ready = OutboxRecord(
        id="out_ready",
        event_id="evt_1",
        aggregate_id="a1",
        aggregate_type="task",
        event_type="ReadyEvent",
        payload_json="{}",
        status="pending",
        available_at=now - timedelta(seconds=10),
    )
    rec_future = OutboxRecord(
        id="out_future",
        event_id="evt_2",
        aggregate_id="a2",
        aggregate_type="task",
        event_type="FutureEvent",
        payload_json="{}",
        status="pending",
        available_at=now + timedelta(seconds=300),
    )

    await repo.save(rec_ready)
    await repo.save(rec_future)

    pending = await repo.get_pending(limit=10, now=now)
    assert len(pending) == 1
    assert pending[0].id == "out_ready"


@pytest.mark.asyncio
async def test_mark_published_and_mark_failed(db_manager):
    """mark_published() and mark_failed() accurately update status in SQL."""
    repo = SqlOutboxRepository(db_manager.session_factory)
    rec1 = OutboxRecord(
        id="out_pub",
        event_id="evt_pub",
        aggregate_id="a1",
        aggregate_type="task",
        event_type="PubEvent",
        payload_json="{}",
        status="pending",
    )
    rec2 = OutboxRecord(
        id="out_fail",
        event_id="evt_fail",
        aggregate_id="a2",
        aggregate_type="task",
        event_type="FailEvent",
        payload_json="{}",
        status="pending",
    )

    await repo.save(rec1)
    await repo.save(rec2)

    # Mark rec1 as published
    pub_time = datetime.now(timezone.utc)
    await repo.mark_published("out_pub", published_at=pub_time)
    r1 = await repo.get_by_id("out_pub")
    assert r1.status == "published"

    # Mark rec2 as failed with retry delay
    future_retry = pub_time + timedelta(seconds=60)
    await repo.mark_failed("out_fail", error="Network timeout", next_available_at=future_retry)
    r2 = await repo.get_by_id("out_fail")
    assert r2.status == "pending"
    assert r2.attempt_count == 1
    assert r2.last_error == "Network timeout"
