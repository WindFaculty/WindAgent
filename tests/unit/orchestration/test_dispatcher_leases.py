"""
Unit Tests for Durable Execution Leases, Idempotency Deduplication, and Worker Registry (Phase F).
"""

import pytest
import pytest_asyncio
from windagent_core.domain.models import WorkflowStep
from windagent_core.domain.types import StepId
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_orchestration.dispatcher import StepDispatcher, LeaseManager, WorkerRegistry
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
async def test_durable_lease_acquisition_and_deduplication(in_memory_db):
    lease_mgr = LeaseManager(uow_factory=in_memory_db.session_factory)
    dispatcher = StepDispatcher(lease_manager=lease_mgr, runtime_port=FakeRuntimeAdapter())
    step = WorkflowStep(id=StepId.generate(), order=1, name="Step 1", tool_name="write_file")
    run_id = "run_300"

    # First claim succeeds
    claimed = await dispatcher.dispatch_step_durable(run_id, step, worker_id="w1", ttl_seconds=30.0)
    assert claimed is True

    # Duplicate claim with same idempotency key fails
    claimed2 = await dispatcher.dispatch_step_durable(run_id, step, worker_id="w2", ttl_seconds=30.0)
    assert claimed2 is False


@pytest.mark.asyncio
async def test_worker_registry_heartbeat():
    registry = WorkerRegistry()
    registry.register("worker_alpha", runtime_type="local")

    assert registry.heartbeat("worker_alpha", active_leases=2)
    healthy = registry.get_healthy_workers()
    assert len(healthy) == 1
    assert healthy[0].active_leases == 2
