"""
Unit Tests for Crash Recovery, Destructive Replay Guard, and Run ID Preservation (Phase H).
"""

import pytest
import pytest_asyncio
from windagent_core.domain.types import SessionId, EventId
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration.recovery import RecoveryManager
from windagent_orchestration.state_machine import TaskState


@pytest_asyncio.fixture
async def in_memory_db():
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest.mark.asyncio
async def test_recovery_destructive_tool_interrupted(in_memory_db):
    sid = SessionId.generate()

    # Record event stream containing an interrupted destructive tool call (write_file)
    async with SqlUnitOfWork(in_memory_db.session_factory) as uow:
        env = EventEnvelope(
            event_id=EventId.generate(),
            event_type="step.started",
            session_id=sid,
            sequence=1,
            payload={"run_id": "run_preserve_123", "tool_name": "write_file", "path": "test.txt"},
        )
        await uow.events.append_event(env)
        await uow.commit()

    rec_manager = RecoveryManager(uow_factory=lambda: SqlUnitOfWork(in_memory_db.session_factory))
    results = await rec_manager.scan_and_reconcile_in_flight_runs(sid)

    assert len(results) == 1
    run_id, state, msg = results[0]
    # Verify original run_id was PRESERVED
    assert run_id == "run_preserve_123"
    # Interrupted destructive step must fail closed, NOT auto-replay
    assert state == TaskState.FAILED
    assert "destructive tool" in msg.lower()
