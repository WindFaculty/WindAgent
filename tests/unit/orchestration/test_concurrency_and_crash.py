"""
Concurrency, Crash Injection, Lease Expiry, and Integration Tests for Orchestration V2 (Phase K).
"""

import pytest
import pytest_asyncio
import asyncio
from windagent_core.domain.models import WorkflowStep
from windagent_core.domain.types import StepId, TaskId, SessionId
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_orchestration import (
    OrchestrationV2Container, TaskState, WorkflowDefinition, WorkflowNode
)
from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter


@pytest_asyncio.fixture
async def in_memory_db():
    from windagent_storage.orm.v2_orchestration_models import BaseORM as V2BaseORM
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    await db_manager.create_tables(V2BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest.mark.asyncio
async def test_concurrent_lease_claims(in_memory_db):
    container = OrchestrationV2Container(uow_factory=in_memory_db.session_factory, runtime_port=FakeRuntimeAdapter())
    step = WorkflowStep(id=StepId.generate(), order=1, name="Concurrent Step", tool_name="exec_shell")
    run_id = "run_concurrent_99"

    # Simulate 10 workers claiming the same step concurrently
    tasks = [
        container.dispatcher.dispatch_step_durable(run_id, step, worker_id=f"w_{i}", ttl_seconds=30.0)
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)

    # Exactly ONE worker must succeed (True), all other 9 must fail (False) -> Zero duplicate execution
    success_count = sum(1 for r in results if r is True)
    assert success_count == 1


@pytest.mark.asyncio
async def test_crash_injection_state_persistence(in_memory_db):
    container = OrchestrationV2Container(uow_factory=in_memory_db.session_factory, runtime_port=FakeRuntimeAdapter())
    tid = TaskId.generate()
    sid = SessionId.generate()

    # Step 1: Transition to PLANNING
    await container.task_manager.transition_task_durable(tid, sid, TaskState.PLANNING)

    # Simulate crash before event broadcast -> DB state is preserved
    container2 = OrchestrationV2Container(uow_factory=in_memory_db.session_factory)
    loaded = await container2.task_manager.load_durable_facts(tid)
    assert loaded is not None
    assert loaded.current_state == TaskState.PLANNING
    assert loaded.version == 1
