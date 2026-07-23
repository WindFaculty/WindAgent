"""
Unit Tests for Durable TaskManager & Optimistic Concurrency (Phase C).
"""

import pytest
import pytest_asyncio
from windagent_core.domain.types import TaskId, SessionId
from windagent_core.errors.exceptions import DomainError
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v2_orchestration_models import BaseORM as V2BaseORM
from windagent_orchestration.task_manager import TaskManager, DurableExecutionFacts
from windagent_orchestration.state_machine import TaskState


@pytest_asyncio.fixture
async def in_memory_db():
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest.mark.asyncio
async def test_durable_task_manager_persistence(in_memory_db):
    tm = TaskManager(uow_factory=in_memory_db.session_factory)
    tid = TaskId.generate()
    sid = SessionId.generate()

    # Initial facts transition
    facts = await tm.transition_task_durable(tid, sid, TaskState.PLANNING)
    assert facts.current_state == TaskState.PLANNING
    assert facts.version == 1

    # Transition to RUNNING
    facts2 = await tm.transition_task_durable(tid, sid, TaskState.RUNNING)
    assert facts2.current_state == TaskState.RUNNING
    assert facts2.version == 2

    # Load from DB in new TaskManager instance
    tm2 = TaskManager(uow_factory=in_memory_db.session_factory)
    loaded = await tm2.load_durable_facts(tid)
    assert loaded is not None
    assert loaded.current_state == TaskState.RUNNING
    assert loaded.version == 2
