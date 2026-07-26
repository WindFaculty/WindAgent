"""
Phase 2 Unit & Integration Tests — Transactional Worker Completion and Outbox Atomicity.

Verifies ban_ke_hoach.md §2 requirements:
- TRANSACTIONAL_TASK_COMPLETION_VERIFIED
  1. Atomic single-transaction task completion, result, outbox, and lease release.
  2. Strict CAS updates (WHERE task_id = ? AND version = ?).
  3. Stale result rejection (STALE_RESULT_REJECTED).
  4. Fault injection rollback (zero partial commits, zero lost terminal states).
  5. Idempotency key deduplication on outbox.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from windagent_core.contracts.finalization import (
    FinalizeTaskExecutionRequest,
    StaleResultRejectedError,
)
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM, OutboxRecordORM
from datetime import datetime, timezone

from windagent_storage.orm.v2_orchestration_models import (
    TaskRunORM,
    ExecutionLeaseORM,
    TaskExecutionResultORM,
)
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork


@pytest.fixture
async def db_manager():
    tmp = tempfile.mkdtemp(prefix="phase2_")
    db_url = f"sqlite+aiosqlite:///{Path(tmp) / 'phase2.db'}"
    db = DatabaseManager(db_url)
    await db.create_tables(BaseORM.metadata)
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_atomic_finalization_happy_path(db_manager):
    """Happy path: Task state, execution result, outbox, and lease release commit atomically."""
    # Seed DB
    now = datetime.now(timezone.utc)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-100", session_id="sess-100", state="running", version=1)
        lease = ExecutionLeaseORM(
            lease_id="lease-100",
            step_run_id="step-100",
            run_id="task-100",
            worker_id="wkr-1",
            fencing_token="fence-100",
            status="active",
            expires_at=now,
            idempotency_key="key-100",
        )
        uow.session.add(task)
        uow.session.add(lease)
        await uow.commit()

    # Execute finalization
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        req = FinalizeTaskExecutionRequest(
            task_id="task-100",
            worker_id="wkr-1",
            lease_id="lease-100",
            fencing_token="fence-100",
            expected_task_version=1,
            execution_result={"output": "success_data"},
            result_artifacts=[{"path": "/tmp/out.txt"}],
            terminal_event={"event_type": "task_completed", "task_id": "task-100"},
            attempt_id="att-1",
            fencing_generation=1,
            terminal_state="completed",
        )
        res = await uow.finalize_task_execution(req)

        assert res.status == "COMPLETED"
        assert res.new_version == 2
        assert res.already_finalized is False

    # Assertions on committed state
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-100"))).scalar_one()
        assert t.state == "completed"
        assert t.version == 2

        l = (await uow.session.execute(select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == "lease-100"))).scalar_one()
        assert l.status == "completed"

        r = (await uow.session.execute(select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == "task-100"))).scalar_one()
        assert r.execution_status == "completed"
        assert r.result_data == {"output": "success_data"}

        outbox_recs = (await uow.session.execute(select(OutboxRecordORM).where(OutboxRecordORM.deduplication_key == req.idempotency_key))).scalars().all()
        assert len(outbox_recs) == 1


@pytest.mark.asyncio
async def test_cas_stale_result_rejection(db_manager):
    """CAS check: A late result with stale version is rejected with STALE_RESULT_REJECTED."""
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-stale", session_id="sess-stale", state="completed", version=2)
        uow.session.add(task)
        await uow.commit()

    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        req = FinalizeTaskExecutionRequest(
            task_id="task-stale",
            worker_id="wkr-late",
            lease_id="lease-old",
            fencing_token="fence-old",
            expected_task_version=1,  # STALE version!
            execution_result={"output": "late_data"},
            terminal_state="completed",
        )
        with pytest.raises(StaleResultRejectedError):
            await uow.finalize_task_execution(req)


@pytest.mark.asyncio
async def test_idempotent_retry_deduplication(db_manager):
    """Retry with exact same idempotency_key returns already_finalized=True and produces 0 duplicates."""
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-idempotent", session_id="sess-idemp", state="running", version=1)
        uow.session.add(task)
        await uow.commit()

    req = FinalizeTaskExecutionRequest(
        task_id="task-idempotent",
        worker_id="wkr-1",
        lease_id="lease-idempotent",
        fencing_token="fence-1",
        expected_task_version=1,
        execution_result={"output": "retry_data"},
        attempt_id="att-idempotent",
        fencing_generation=1,
    )

    # First completion
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        res1 = await uow.finalize_task_execution(req)
        assert res1.status == "COMPLETED"
        assert res1.already_finalized is False

    # Second completion (retry)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        res2 = await uow.finalize_task_execution(req)
        assert res2.status == "COMPLETED"
        assert res2.already_finalized is True

    # Assert outbox records count = 1 (no duplicates)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        outbox = (await uow.session.execute(select(OutboxRecordORM).where(OutboxRecordORM.deduplication_key == req.idempotency_key))).scalars().all()
        assert len(outbox) == 1


@pytest.mark.asyncio
async def test_fault_injection_outbox_failure_rolls_back_entire_transaction(db_manager):
    """Fault injection: If outbox write fails, entire transaction is rolled back."""
    now = datetime.now(timezone.utc)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-fault", session_id="sess-fault", state="running", version=1)
        lease = ExecutionLeaseORM(
            lease_id="lease-fault",
            step_run_id="step-fault",
            run_id="task-fault",
            worker_id="wkr-1",
            fencing_token="fence-1",
            status="active",
            expires_at=now,
            idempotency_key="key-fault",
        )
        uow.session.add(task)
        uow.session.add(lease)
        await uow.commit()

    # Attempt finalization with broken outbox writer (simulate exception)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        # Patch record_outbox_event to raise RuntimeError
        async def _broken_outbox(event: EventEnvelope):
            raise RuntimeError("FAULT_INJECTION: Outbox database write failed!")

        uow.record_outbox_event = _broken_outbox  # type: ignore

        req = FinalizeTaskExecutionRequest(
            task_id="task-fault",
            worker_id="wkr-1",
            lease_id="lease-fault",
            fencing_token="fence-1",
            expected_task_version=1,
            execution_result={"output": "fault_data"},
        )

        with pytest.raises(RuntimeError, match="FAULT_INJECTION"):
            await uow.finalize_task_execution(req)

    # Verify DB rolled back completely: task state still running, version still 1, lease still active
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-fault"))).scalar_one()
        assert t.state == "running"
        assert t.version == 1

        l = (await uow.session.execute(select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == "lease-fault"))).scalar_one()
        assert l.status == "active"

        results = (await uow.session.execute(select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == "task-fault"))).scalars().all()
        assert len(results) == 0
