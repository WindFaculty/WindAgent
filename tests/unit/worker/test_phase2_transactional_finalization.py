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


# ===========================================================================
# Extended Fault Injection Matrix (ban_ke_hoach.md §2 Test Matrix)
# Injection points 5-9 per spec
# ===========================================================================

@pytest.mark.asyncio
async def test_fault_injection_result_persistence_failure(db_manager):
    """Fault injection at step 4: Result ORM insert failure rolls back entire transaction.

    Spec: Task state, outbox, and lease must remain unchanged if result persistence fails.
    """
    now = datetime.now(timezone.utc)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-res-fail", session_id="sess-res", state="running", version=1)
        lease = ExecutionLeaseORM(
            lease_id="lease-res-fail",
            step_run_id="step-res",
            run_id="task-res-fail",
            worker_id="wkr-1",
            fencing_token="fence-res",
            status="active",
            expires_at=now,
            idempotency_key="key-res",
        )
        uow.session.add(task)
        uow.session.add(lease)
        await uow.commit()

    # Simulate failure by patching session.add to raise when TaskExecutionResultORM is added
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        original_add = uow.session.add

        def _broken_add(obj):
            if isinstance(obj, TaskExecutionResultORM):
                raise RuntimeError("FAULT_INJECTION: Result DB insert failed!")
            return original_add(obj)

        uow.session.add = _broken_add  # type: ignore

        req = FinalizeTaskExecutionRequest(
            task_id="task-res-fail",
            worker_id="wkr-1",
            lease_id="lease-res-fail",
            fencing_token="fence-res",
            expected_task_version=1,
            execution_result={"output": "res_fault_data"},
        )

        with pytest.raises(RuntimeError, match="FAULT_INJECTION"):
            await uow.finalize_task_execution(req)

    # Verify full rollback: task still running, lease still active, no result records
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-res-fail"))).scalar_one()
        assert t.state == "running"
        assert t.version == 1

        l = (await uow.session.execute(select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == "lease-res-fail"))).scalar_one()
        assert l.status == "active"

        results = (await uow.session.execute(select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == "task-res-fail"))).scalars().all()
        assert len(results) == 0


@pytest.mark.asyncio
async def test_fault_injection_event_store_failure(db_manager):
    """Fault injection at step 5/6: Event store write failure rolls back entire transaction.

    Spec: If event store insert fails, no partial commits — task stays running, no outbox records.
    """
    now = datetime.now(timezone.utc)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-evt-fail", session_id="sess-evt", state="running", version=1)
        uow.session.add(task)
        await uow.commit()

    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        # Patch events.append to raise
        original_append = uow.events.append

        async def _broken_events_append(event):
            raise RuntimeError("FAULT_INJECTION: Event store write failed!")

        uow.events.append = _broken_events_append  # type: ignore

        req = FinalizeTaskExecutionRequest(
            task_id="task-evt-fail",
            worker_id="wkr-1",
            lease_id="lease-evt-fail",
            fencing_token="fence-evt",
            expected_task_version=1,
            execution_result={"output": "evt_fault_data"},
        )

        with pytest.raises(RuntimeError, match="FAULT_INJECTION"):
            await uow.finalize_task_execution(req)

    # Verify full rollback
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-evt-fail"))).scalar_one()
        assert t.state == "running"
        assert t.version == 1

        outbox = (await uow.session.execute(select(OutboxRecordORM))).scalars().all()
        # No outbox records for this task
        task_outbox = [o for o in outbox if "task-evt-fail" in (o.payload or "")]
        assert len(task_outbox) == 0


@pytest.mark.asyncio
async def test_fault_injection_lease_release_failure(db_manager):
    """Fault injection at step 7: Lease status update failure rolls back entire transaction.

    Spec: If lease marking fails, lease must remain active and task state must remain running.
    Lease MUST NOT be left in a 'half-released' state.
    """
    now = datetime.now(timezone.utc)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-lease-fail", session_id="sess-lease", state="running", version=1)
        lease = ExecutionLeaseORM(
            lease_id="lease-lease-fail",
            step_run_id="step-lease",
            run_id="task-lease-fail",
            worker_id="wkr-1",
            fencing_token="fence-lease",
            status="active",
            expires_at=now,
            idempotency_key="key-lease",
        )
        uow.session.add(task)
        uow.session.add(lease)
        await uow.commit()

    from unittest.mock import patch, AsyncMock
    from windagent_storage.services import task_finalizer as tf_module

    # Patch lease status update inside TaskFinalizer to raise after CAS succeeds
    original_finalize = tf_module.TaskFinalizer.finalize_task_execution

    async def _broken_finalize(self_inner, request):
        # Run normally up to lease release, then raise
        from sqlalchemy import select, update
        from windagent_storage.orm.v2_orchestration_models import TaskRunORM as TR, ExecutionLeaseORM as EL

        session = self_inner.uow.session
        # Manually trigger the CAS step, then simulate a lease update failure
        stmt = (
            update(TR)
            .where(TR.id == request.task_id, TR.version == request.expected_task_version)
            .values(state=request.terminal_state, version=TR.version + 1)
        )
        res = await session.execute(stmt)
        if res.rowcount == 0:
            from windagent_core.contracts.finalization import StaleResultRejectedError
            raise StaleResultRejectedError(request.task_id, request.fencing_token, request.expected_task_version)

        # Simulate lease update failure
        raise RuntimeError("FAULT_INJECTION: Lease status update failed!")

    with patch.object(tf_module.TaskFinalizer, "finalize_task_execution", _broken_finalize):
        async with SqlUnitOfWork(db_manager.session_factory) as uow:
            req = FinalizeTaskExecutionRequest(
                task_id="task-lease-fail",
                worker_id="wkr-1",
                lease_id="lease-lease-fail",
                fencing_token="fence-lease",
                expected_task_version=1,
                execution_result={"output": "lease_fault_data"},
            )

            with pytest.raises(RuntimeError, match="FAULT_INJECTION"):
                await uow.finalize_task_execution(req)

    # Verify: full rollback — task back to running, lease still active
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-lease-fail"))).scalar_one()
        assert t.state == "running"
        assert t.version == 1

        l = (await uow.session.execute(select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == "lease-lease-fail"))).scalar_one()
        assert l.status == "active"


@pytest.mark.asyncio
async def test_fault_injection_commit_failure(db_manager):
    """Fault injection at step 8: Commit failure leaves DB in pre-commit state.

    Spec: If commit raises, task must remain running, outbox must remain empty,
    lease must remain active. No partial state may persist.
    """
    now = datetime.now(timezone.utc)
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-commit-fail", session_id="sess-commit", state="running", version=1)
        lease = ExecutionLeaseORM(
            lease_id="lease-commit-fail",
            step_run_id="step-commit",
            run_id="task-commit-fail",
            worker_id="wkr-1",
            fencing_token="fence-commit",
            status="active",
            expires_at=now,
            idempotency_key="key-commit",
        )
        uow.session.add(task)
        uow.session.add(lease)
        await uow.commit()

    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        # Patch commit to raise after all writes are staged
        original_commit = uow.commit

        async def _broken_commit():
            # Simulate commit failure (e.g. connection lost, serialization failure)
            raise RuntimeError("FAULT_INJECTION: Database commit failed!")

        uow.commit = _broken_commit  # type: ignore

        req = FinalizeTaskExecutionRequest(
            task_id="task-commit-fail",
            worker_id="wkr-1",
            lease_id="lease-commit-fail",
            fencing_token="fence-commit",
            expected_task_version=1,
            execution_result={"output": "commit_fault_data"},
            attempt_id="att-commit",
            fencing_generation=1,
        )

        with pytest.raises(RuntimeError, match="FAULT_INJECTION"):
            await uow.finalize_task_execution(req)

    # Verify: no changes persisted — task still running, lease still active, no outbox
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-commit-fail"))).scalar_one()
        assert t.state == "running"
        assert t.version == 1

        l = (await uow.session.execute(select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == "lease-commit-fail"))).scalar_one()
        assert l.status == "active"

        results = (await uow.session.execute(select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == "task-commit-fail"))).scalars().all()
        assert len(results) == 0


@pytest.mark.asyncio
async def test_crash_after_commit_idempotent_recovery(db_manager):
    """Crash recovery at step 9: Worker crash AFTER commit produces idempotent recovery.

    Simulates: commit succeeded, worker process died before sending internal ACK.
    Recovery scenario: the same worker (or recovery leader) retries with the same
    idempotency key and receives already_finalized=True — no duplicate records created.

    Spec §2.5 & §2.6: Retry of the same transaction MUST NOT create duplicate completion
    records, events, outbox entries, or artifact links.
    """
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(id="task-crash-recover", session_id="sess-crash", state="running", version=1)
        uow.session.add(task)
        await uow.commit()

    req = FinalizeTaskExecutionRequest(
        task_id="task-crash-recover",
        worker_id="wkr-recover",
        lease_id="lease-crash-recover",
        fencing_token="fence-crash",
        expected_task_version=1,
        execution_result={"output": "crash_recover_data"},
        attempt_id="att-crash-recover",
        fencing_generation=1,
        terminal_state="completed",
    )

    # First finalization — simulates the commit that succeeded before crash
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        res1 = await uow.finalize_task_execution(req)
        assert res1.status == "COMPLETED"
        assert res1.already_finalized is False

    # Simulate worker restart — retry with the SAME idempotency key
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        res2 = await uow.finalize_task_execution(req)
        assert res2.status == "COMPLETED"
        assert res2.already_finalized is True  # idempotent — worker recognized it was already done

    # Assert no duplicate records: exactly 1 outbox, 1 result, task version unchanged at 2
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        t = (await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == "task-crash-recover"))).scalar_one()
        assert t.state == "completed"
        assert t.version == 2  # incremented exactly once

        outbox = (await uow.session.execute(
            select(OutboxRecordORM).where(OutboxRecordORM.deduplication_key == req.idempotency_key)
        )).scalars().all()
        assert len(outbox) == 1  # no duplicate outbox records

        results = (await uow.session.execute(
            select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == "task-crash-recover")
        )).scalars().all()
        assert len(results) == 1  # exactly one result record

