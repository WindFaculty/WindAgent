"""Phase 3 Unit Tests: Durable Task Submission & Atomic Claiming.

Validates SqlWorkSubmissionAdapter, SqlDurableTaskQueue, atomic claiming,
lease renewal, lease expiry reclaim, fencing token generation, and rollback safety.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from windagent_core.contracts.workers.models import WorkSubmission
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM, OutboxRecordORM
from windagent_storage.orm.v2_orchestration_models import ExecutionLeaseORM, TaskRunORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_worker.runner import ProductionWorker


@pytest.fixture
async def db_manager():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        yield db
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_api_submit_task_creates_sql_queue_and_outbox_event(db_manager):
    """API submits task, SQL has queue record and TaskSubmitted outbox record in one transaction."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    req = WorkSubmission(
        prompt="Fix payment gateway race condition",
        tool_name="code_search",
        parameters={"query": "payment_gateway"},
        workflow_name="bugfix",
    )

    task_id = await submitter.submit(req)
    assert task_id.startswith("tsk_")

    async with db_manager.session_factory() as session:
        # Check task run ORM
        res_task = await session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        task_orm = res_task.scalar_one_or_none()
        assert task_orm is not None
        assert task_orm.state == "pending"

        # Check outbox record ORM
        res_outbox = await session.execute(
            select(OutboxRecordORM)
            .where(OutboxRecordORM.aggregate_id == task_id)
            .where(OutboxRecordORM.event_type == "TaskSubmitted")
        )
        outbox_orm = res_outbox.scalar_one_or_none()
        assert outbox_orm is not None
        assert outbox_orm.status == "pending"


@pytest.mark.asyncio
async def test_worker_claims_sql_task_atomically(db_manager):
    """Worker claims task from SQL queue via SqlDurableTaskQueue."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    task_id = await submitter.submit(WorkSubmission(prompt="Refactor database layer"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    claimed = await queue.claim_next(worker_id="wkr_01", lease_ttl_seconds=10)

    assert claimed is not None
    assert claimed.task_id == task_id
    assert claimed.worker_id == "wkr_01"
    assert claimed.lease_generation == 1
    assert claimed.fencing_token.startswith(f"fence_{task_id}_gen_1")


@pytest.mark.asyncio
async def test_two_workers_concurrent_claim(db_manager):
    """Two workers competing for a single task result in exactly one successful claim."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    await submitter.submit(WorkSubmission(prompt="Single available task"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)

    c1 = await queue.claim_next(worker_id="wkr_A")
    c2 = await queue.claim_next(worker_id="wkr_B")

    assert c1 is not None
    assert c1.worker_id == "wkr_A"
    assert c2 is None  # Second claim finds no pending task


@pytest.mark.asyncio
async def test_task_non_reclaimable_before_lease_expiry(db_manager):
    """Claimed task cannot be reclaimed before its lease expires."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    await submitter.submit(WorkSubmission(prompt="Active lease task"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    c1 = await queue.claim_next(worker_id="wkr_01", lease_ttl_seconds=60)
    assert c1 is not None

    # Immediate second claim attempt by another worker
    c2 = await queue.claim_next(worker_id="wkr_02", lease_ttl_seconds=60)
    assert c2 is None


@pytest.mark.asyncio
async def test_task_reclaimable_after_lease_expiry(db_manager):
    """Expired lease allows a new worker to reclaim task with incremented generation and new fencing token."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    await submitter.submit(WorkSubmission(prompt="Long running task"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    # Claim with 0 second TTL to simulate immediate expiry
    c1 = await queue.claim_next(worker_id="wkr_crasher", lease_ttl_seconds=-1)
    assert c1 is not None
    assert c1.lease_generation == 1

    # New worker claims expired task
    c2 = await queue.claim_next(worker_id="wkr_recoverer", lease_ttl_seconds=30)
    assert c2 is not None
    assert c2.worker_id == "wkr_recoverer"
    assert c2.lease_generation == 2
    assert c2.fencing_token != c1.fencing_token
    assert "gen_2" in c2.fencing_token
    # The reclaim must return the SAME persisted lease identity, never a
    # freshly generated unused lease ID.
    assert c2.lease_id == c1.lease_id


@pytest.mark.asyncio
async def test_fencing_token_validation_prevents_stale_renewal(db_manager):
    """Lease renewal with mismatched fencing token is rejected."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    task_id = await submitter.submit(WorkSubmission(prompt="Fencing validation test"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    c1 = await queue.claim_next(worker_id="wkr_01", lease_ttl_seconds=10)
    assert c1 is not None

    # Try to renew with bad fencing token
    renewed = await queue.renew(task_id, "wkr_01", fencing_token="stale_fake_fence")
    assert renewed is False

    # Renew with correct fencing token
    renewed_valid = await queue.renew(task_id, "wkr_01", fencing_token=c1.fencing_token)
    assert renewed_valid is True


@pytest.mark.asyncio
async def test_production_worker_durable_tick(db_manager):
    """ProductionWorker performs poll_and_execute_tick via SqlDurableTaskQueue.

    With the SQL UoW finalization enabled, the tick must atomically complete the
    task AND the exact claimed lease. A fresh session proves the durable state:
    task completed, exact lease completed with a non-null released_at.
    """
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    task_id = await submitter.submit(WorkSubmission(prompt="Worker tick test"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    worker = ProductionWorker(
        name="durable-test-worker",
        task_queue=queue,
        execution_registry=ExecutionRuntimeRegistry(allow_tool_simulation=True),
        uow_factory=db_manager.session_factory,
    )
    await worker.start()

    tick_res = await worker.poll_and_execute_tick()
    assert tick_res["status"] == "completed"
    assert tick_res["task_id"] == task_id
    await worker.stop()

    # Fresh session: the durable finalization committed task + exact lease.
    async with db_manager.session_factory() as session:
        task = (
            await session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        ).scalar_one()
        assert task.state == "completed"

        lease = (
            await session.execute(
                select(ExecutionLeaseORM).where(ExecutionLeaseORM.run_id == task_id)
            )
        ).scalar_one()
        assert lease.status == "completed"
        assert lease.released_at is not None
