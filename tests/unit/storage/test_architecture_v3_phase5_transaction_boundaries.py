"""
Architecture V3 Phase 5A — canonical transaction checkpoints and crash gate.

Proves, against the real SQLite SQL UoW (no mocks), that crashes at every
required transaction boundary never create split state:

- the happy path fires the five canonical checkpoints in exact order;
- a crash at any of the four pre-commit checkpoints leaves every durable
  surface at its seeded pre-finalization state (task state/version/facts
  unchanged, zero execution result, zero terminal domain event, zero terminal
  outbox event, lease still active/unreleased);
- a crash at ``after_commit`` keeps all five durable surfaces committed
  together and a subsequent retry is idempotent (``already_finalized=True``)
  with exactly one row on every surface.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from windagent_core.contracts.finalization import (
    FinalizationCheckpoint,
    FinalizeTaskExecutionRequest,
    StaleResultRejectedError,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import (
    BaseORM,
    ExecutionEventORM,
    OutboxRecordORM,
)
from windagent_storage.orm.v2_orchestration_models import (
    ExecutionLeaseORM,
    TaskExecutionResultORM,
    TaskRunORM,
    WorkflowRunV2ORM,
    WorkflowStepRunORM,
)
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork


async def _seed_step_run(session, step_run_id: str) -> None:
    """Seed the workflow_step_runs + v2_workflow_runs_v2 graph the lease FK requires.

    ``execution_leases.step_run_id`` references ``workflow_step_runs.id`` and
    ``workflow_step_runs.workflow_run_id`` references ``v2_workflow_runs_v2.run_id``;
    with FK enforcement enabled the parent rows must exist before a lease insert.
    """
    run_id = f"wf-{step_run_id}"
    session.add(
        WorkflowRunV2ORM(
            run_id=run_id,
            workflow_id=run_id,
            session_id="sess-graph",
            state="running",
            version=1,
        )
    )
    session.add(
        WorkflowStepRunORM(
            id=step_run_id,
            workflow_run_id=run_id,
            step_order=1,
            name=step_run_id,
            tool_name="read_file",
            state="running",
        )
    )
    await session.flush()


async def _seed_task(
    db_manager,
    task_id: str,
    facts_json: str = "{}",
    lease_id: str | None = None,
    fencing_token: str = "fence-p5a",
    worker_id: str = "wkr-p5a",
) -> str:
    """Seed a running task + active lease at version 1 (pre-finalization state)."""
    now = datetime.now(timezone.utc)
    step_run_id = f"step-{task_id}"
    lease_id = lease_id or f"lease-{task_id}"
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = TaskRunORM(
            id=task_id,
            session_id=f"sess-{task_id}",
            state="running",
            version=1,
            facts_json=facts_json,
        )
        await _seed_step_run(uow.session, step_run_id)
        lease = ExecutionLeaseORM(
            lease_id=lease_id,
            step_run_id=step_run_id,
            run_id=task_id,
            worker_id=worker_id,
            fencing_token=fencing_token,
            status="active",
            expires_at=now,
            idempotency_key=f"key-{task_id}",
        )
        uow.session.add(task)
        uow.session.add(lease)
        await uow.commit()
    return lease_id


def _make_request(task_id: str) -> FinalizeTaskExecutionRequest:
    return FinalizeTaskExecutionRequest(
        task_id=task_id,
        worker_id="wkr-p5a",
        lease_id=f"lease-{task_id}",
        fencing_token="fence-p5a",
        expected_task_version=1,
        execution_result={"output": "phase5a_output"},
        result_artifacts=[{"path": "/tmp/p5a.txt"}],
        terminal_event={"event_type": "task_completed", "task_id": task_id},
        attempt_id=f"att-{task_id}",
        fencing_generation=1,
        terminal_state="completed",
    )


async def _assert_seeded_state(
    db_manager, task_id: str, lease_id: str, expected_facts: str = "{}"
) -> None:
    """Assert every durable surface is still at its seeded pre-finalization state."""
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = (
            await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        ).scalar_one()
        assert task.state == "running"
        assert task.version == 1
        assert task.facts_json == expected_facts

        results = (
            await uow.session.execute(
                select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == task_id)
            )
        ).scalars().all()
        assert len(results) == 0

        events = (
            await uow.session.execute(
                select(ExecutionEventORM).where(
                    ExecutionEventORM.event_type == "task_completed",
                    ExecutionEventORM.data_json.contains(task_id),
                )
            )
        ).scalars().all()
        assert len(events) == 0

        outbox = (
            await uow.session.execute(
                select(OutboxRecordORM).where(
                    OutboxRecordORM.deduplication_key == _make_request(task_id).idempotency_key
                )
            )
        ).scalars().all()
        assert len(outbox) == 0

        lease = (
            await uow.session.execute(
                select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == lease_id)
            )
        ).scalar_one()
        assert lease.status == "active"
        assert lease.released_at is None


class RecordingHook:
    """Checkpoint hook that records every fired checkpoint in order."""

    def __init__(self) -> None:
        self.checkpoints: list[str] = []

    def __call__(self, checkpoint: FinalizationCheckpoint) -> None:
        self.checkpoints.append(checkpoint.value)


class CrashHook:
    """Checkpoint hook that raises a checkpoint-specific exception at one point."""

    def __init__(self, crash_at: FinalizationCheckpoint, message: str) -> None:
        self.crash_at = crash_at
        self.message = message
        self.fired: list[str] = []

    def __call__(self, checkpoint: FinalizationCheckpoint) -> None:
        self.fired.append(checkpoint.value)
        if checkpoint == self.crash_at:
            raise RuntimeError(self.message)


@pytest.fixture
async def db_manager(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'p5a.db'}"
    db = DatabaseManager(db_url)
    await db.create_tables(BaseORM.metadata)
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_happy_path_checkpoint_order_exactly_five(db_manager):
    """Happy path fires the five canonical checkpoints in exact order."""
    task_id = "task-p5a-order"
    await _seed_task(db_manager, task_id, facts_json='{"seed": 1}')
    hook = RecordingHook()
    req = _make_request(task_id)

    async with SqlUnitOfWork(db_manager.session_factory, checkpoint_hook=hook) as uow:
        res = await uow.finalize_task_execution(req)
        assert res.status == "COMPLETED"
        assert res.already_finalized is False

    assert hook.checkpoints == [
        "before_write",
        "after_state_write",
        "after_event_write",
        "before_commit",
        "after_commit",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "checkpoint",
    [
        FinalizationCheckpoint.BEFORE_WRITE,
        FinalizationCheckpoint.AFTER_STATE_WRITE,
        FinalizationCheckpoint.AFTER_EVENT_WRITE,
        FinalizationCheckpoint.BEFORE_COMMIT,
    ],
    ids=lambda c: c.value,
)
async def test_pre_commit_crash_leaves_seeded_state(db_manager, checkpoint):
    """A crash at any pre-commit checkpoint leaves every durable surface untouched."""
    task_id = f"task-p5a-crash-{checkpoint.value}"
    seeded_facts = '{"seed": "p5a"}'
    lease_id = await _seed_task(db_manager, task_id, facts_json=seeded_facts)
    message = f"P5A_CRASH:{checkpoint.value}"
    hook = CrashHook(checkpoint, message)
    req = _make_request(task_id)

    async with SqlUnitOfWork(db_manager.session_factory, checkpoint_hook=hook) as uow:
        with pytest.raises(RuntimeError, match=re.escape(message)):
            await uow.finalize_task_execution(req)

    assert hook.fired[-1] == checkpoint.value
    await _assert_seeded_state(db_manager, task_id, lease_id, expected_facts=seeded_facts)


@pytest.mark.asyncio
async def test_after_commit_crash_is_durable_and_retry_idempotent(db_manager):
    """A crash at after_commit keeps all five surfaces committed; retry is idempotent."""
    task_id = "task-p5a-after-commit"
    lease_id = await _seed_task(db_manager, task_id)
    message = "P5A_CRASH:after_commit"
    hook = CrashHook(FinalizationCheckpoint.AFTER_COMMIT, message)
    req = _make_request(task_id)

    async with SqlUnitOfWork(db_manager.session_factory, checkpoint_hook=hook) as uow:
        with pytest.raises(RuntimeError, match=re.escape(message)):
            await uow.finalize_task_execution(req)

    # All five durable surfaces are committed together.
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = (
            await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        ).scalar_one()
        assert task.state == "completed"
        assert task.version == 2
        facts = json.loads(task.facts_json)
        assert facts["terminal_state"] == "completed"
        assert facts["result"] == {"output": "phase5a_output"}

        results = (
            await uow.session.execute(
                select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == task_id)
            )
        ).scalars().all()
        assert len(results) == 1

        events = (
            await uow.session.execute(
                select(ExecutionEventORM).where(
                    ExecutionEventORM.event_type == "task_completed",
                    ExecutionEventORM.data_json.contains(task_id),
                )
            )
        ).scalars().all()
        assert len(events) == 1

        outbox = (
            await uow.session.execute(
                select(OutboxRecordORM).where(
                    OutboxRecordORM.deduplication_key == req.idempotency_key
                )
            )
        ).scalars().all()
        assert len(outbox) == 1

        lease = (
            await uow.session.execute(
                select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == lease_id)
            )
        ).scalar_one()
        assert lease.status == "completed"
        assert lease.released_at is not None

    # Retry without a crashing hook: idempotent, no duplicate rows anywhere.
    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        res = await uow.finalize_task_execution(req)
        assert res.status == "COMPLETED"
        assert res.already_finalized is True

    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        task = (
            await uow.session.execute(select(TaskRunORM).where(TaskRunORM.id == task_id))
        ).scalar_one()
        assert task.state == "completed"
        assert task.version == 2

        results = (
            await uow.session.execute(
                select(TaskExecutionResultORM).where(TaskExecutionResultORM.task_id == task_id)
            )
        ).scalars().all()
        assert len(results) == 1

        events = (
            await uow.session.execute(
                select(ExecutionEventORM).where(
                    ExecutionEventORM.event_type == "task_completed",
                    ExecutionEventORM.data_json.contains(task_id),
                )
            )
        ).scalars().all()
        assert len(events) == 1

        outbox = (
            await uow.session.execute(
                select(OutboxRecordORM).where(
                    OutboxRecordORM.deduplication_key == req.idempotency_key
                )
            )
        ).scalars().all()
        assert len(outbox) == 1

        lease = (
            await uow.session.execute(
                select(ExecutionLeaseORM).where(ExecutionLeaseORM.lease_id == lease_id)
            )
        ).scalar_one()
        assert lease.status == "completed"
        assert lease.released_at is not None


@pytest.mark.asyncio
async def test_wrong_lease_id_rejected_leaves_seeded_state(db_manager):
    """A finalization targeting a wrong lease ID fails closed before any mutation.

    The exact lease identity is the fencing contract: a request that names a
    lease that does not exist must be rejected as stale and every durable
    surface must remain at its seeded pre-finalization state.
    """
    task_id = "task-p5b-wrong-lease"
    seeded_facts = '{"seed": "p5b"}'
    lease_id = await _seed_task(db_manager, task_id, facts_json=seeded_facts)
    req = _make_request(task_id)
    req.lease_id = "lease-does-not-exist"

    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        with pytest.raises(StaleResultRejectedError):
            await uow.finalize_task_execution(req)

    await _assert_seeded_state(db_manager, task_id, lease_id, expected_facts=seeded_facts)


@pytest.mark.asyncio
async def test_wrong_lease_generation_rejected_leaves_seeded_state(db_manager):
    """A finalization with a mismatched lease generation fails closed before any mutation.

    The claimed lease carries a generation; a request whose fencing_generation
    differs must be rejected as stale and every durable surface must remain at
    its seeded pre-finalization state.
    """
    task_id = "task-p5b-wrong-gen"
    seeded_facts = '{"seed": "p5b"}'
    lease_id = await _seed_task(db_manager, task_id, facts_json=seeded_facts)
    req = _make_request(task_id)
    req.fencing_generation = 99

    async with SqlUnitOfWork(db_manager.session_factory) as uow:
        with pytest.raises(StaleResultRejectedError):
            await uow.finalize_task_execution(req)

    await _assert_seeded_state(db_manager, task_id, lease_id, expected_facts=seeded_facts)