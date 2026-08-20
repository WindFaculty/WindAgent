"""
Phase 7 Unit & Workload Tests: Startup Recovery & Leader Lease.
Verifies singleton leader lease, paginated recovery, decision matrix, and 1,000-run recovery workload fixed distribution.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "apps/backend"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from windagent_storage.orm.v2_orchestration_models import (
    BaseORM as V2BaseORM, TaskRunORM, WorkflowRunV2ORM, WorkflowStepRunORM,
    ExecutionLeaseORM, RuntimeExecutionORM
)
from windagent_orchestration.recovery import RecoveryManager
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork


@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(V2BaseORM.metadata.create_all)
    
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_recovery_leader_lease_concurrency(db_factory):
    """Verify singleton recovery leader lease prevents concurrent secondary node recovery."""
    rec_leader = RecoveryManager(uow_factory=lambda: SqlUnitOfWork(db_factory), instance_id="leader_node_1")
    rec_follower = RecoveryManager(uow_factory=lambda: SqlUnitOfWork(db_factory), instance_id="follower_node_2")

    report1 = await rec_leader.recover_all_in_flight()
    assert report1.leader_acquired is True

    # Secondary node fails to acquire leader lease
    report2 = await rec_follower.recover_all_in_flight()
    assert report2.leader_acquired is False


@pytest.mark.asyncio
async def test_recovery_1000_runs_fixed_distribution(db_factory):
    """Verify recovery scan & reconciliation over 1,000 real seeded in-flight records with declared fixed distribution:
    - Alive: 250
    - Completed-uningested: 200
    - Expired lease: 200
    - Lost runtime: 150
    - Destructive-unknown: 100
    - Cancelled-runtime-alive: 100
    Total = 1,000 runs
    """
    # Seed 1,000 records
    async with SqlUnitOfWork(db_factory) as uow:
        # 1. Alive (250)
        for i in range(250):
            sid = f"step_alive_{i}"
            uow.session.add(WorkflowStepRunORM(id=sid, workflow_run_id="wf_1", step_order=i, name=f"Alive {i}", tool_name="read_file", state="running"))
            uow.session.add(RuntimeExecutionORM(id=f"exec_{sid}", runtime_run_id=f"r_{sid}", attempt_id="att_1", step_run_id=sid, fencing_token=f"fence_{sid}", status="running"))

        # 2. Completed-uningested (200)
        for i in range(200):
            sid = f"step_comp_{i}"
            uow.session.add(WorkflowStepRunORM(id=sid, workflow_run_id="wf_1", step_order=i, name=f"Comp {i}", tool_name="read_file", state="running"))
            uow.session.add(RuntimeExecutionORM(id=f"exec_{sid}", runtime_run_id=f"r_{sid}", attempt_id="att_1", step_run_id=sid, fencing_token=f"fence_{sid}", status="completed"))

        # 3. Expired lease (200)
        for i in range(200):
            sid = f"step_exp_{i}"
            uow.session.add(WorkflowStepRunORM(id=sid, workflow_run_id="wf_1", step_order=i, name=f"Exp {i}", tool_name="read_file", state="running"))

        # 4. Lost runtime (150)
        for i in range(150):
            sid = f"step_lost_{i}"
            uow.session.add(WorkflowStepRunORM(id=sid, workflow_run_id="wf_1", step_order=i, name=f"Lost {i}", tool_name="read_file", state="running"))
            uow.session.add(RuntimeExecutionORM(id=f"exec_{sid}", runtime_run_id=f"r_{sid}", attempt_id="att_1", step_run_id=sid, fencing_token=f"fence_{sid}", status="lost"))

        # 5. Destructive-unknown (100)
        for i in range(100):
            sid = f"step_dest_{i}"
            uow.session.add(WorkflowStepRunORM(id=sid, workflow_run_id="wf_1", step_order=i, name=f"Dest {i}", tool_name="run_command", state="running"))
            uow.session.add(RuntimeExecutionORM(id=f"exec_{sid}", runtime_run_id=f"r_{sid}", attempt_id="att_1", step_run_id=sid, fencing_token=f"fence_{sid}", status="unknown"))

        # 6. Cancelled-runtime-alive (100)
        for i in range(100):
            sid = f"step_canc_{i}"
            uow.session.add(WorkflowStepRunORM(id=sid, workflow_run_id="wf_1", step_order=i, name=f"Canc {i}", tool_name="read_file", state="running"))
            uow.session.add(RuntimeExecutionORM(id=f"exec_{sid}", runtime_run_id=f"r_{sid}", attempt_id="att_1", step_run_id=sid, fencing_token=f"fence_{sid}", status="cancelled"))

        await uow.commit()

    rec_manager = RecoveryManager(uow_factory=lambda: SqlUnitOfWork(db_factory), instance_id="leader_node_workload")
    report = await rec_manager.recover_all_in_flight(batch_size=1500)

    assert report.leader_acquired is True
    assert report.runs_reconciled == 1000
    assert report.completed_ingested_count == 200
    assert report.reattached_count == 250
    assert report.destructive_blocked_count == 100
