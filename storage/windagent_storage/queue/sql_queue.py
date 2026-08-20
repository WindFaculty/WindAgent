"""SQL-backed durable task queue adapter supporting atomic claiming."""

from __future__ import annotations
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.contracts.workers.queue import ClaimedTask, DurableTaskQueuePort
from windagent_core.contracts.workers.leases import TaskLeasePort
from windagent_storage.orm.v2_orchestration_models import (
    TaskRunORM,
    ExecutionLeaseORM,
    WorkflowRunV2ORM,
    WorkflowStepRunORM,
)

logger = logging.getLogger("windagent.storage.queue.sql")


async def _ensure_step_run_graph(session: AsyncSession, task_orm: TaskRunORM, now_naive: datetime) -> None:
    """Ensure the durable execution graph exists before a lease references it.

    ``execution_leases.step_run_id`` has a foreign key to
    ``workflow_step_runs.id`` (and ``workflow_step_runs.workflow_run_id`` to
    ``v2_workflow_runs_v2.run_id``).  The worker's ``ExecutionRequest`` treats a
    claimed task as a single-step workflow (``step_run_id=<task_id>``,
    ``workflow_run_id=wf_<task_id>``), so the graph rows are created idempotently
    here — inside the same claim transaction — instead of letting the lease
    insert violate the FK.

    Idempotent: a re-claim (expired lease takeover) finds the rows already
    present and leaves them untouched.
    """
    workflow_run_id = f"wf_{task_orm.id}"
    facts = json.loads(task_orm.facts_json) if task_orm.facts_json else {}

    existing_run = (
        await session.execute(select(WorkflowRunV2ORM).where(WorkflowRunV2ORM.run_id == workflow_run_id))
    ).scalar_one_or_none()
    if existing_run is None:
        session.add(
            WorkflowRunV2ORM(
                run_id=workflow_run_id,
                workflow_id=workflow_run_id,
                session_id=task_orm.session_id,
                task_run_id=task_orm.id,
                state="running",
                version=1,
                checkpoint_cursor=0,
                definition_json="{}",
                created_at=now_naive,
                updated_at=now_naive,
            )
        )

    existing_step = (
        await session.execute(select(WorkflowStepRunORM).where(WorkflowStepRunORM.id == task_orm.id))
    ).scalar_one_or_none()
    if existing_step is None:
        session.add(
            WorkflowStepRunORM(
                id=task_orm.id,
                workflow_run_id=workflow_run_id,
                step_order=1,
                name=task_orm.id,
                tool_name=facts.get("tool_name", "read_file"),
                params_json=json.dumps(facts.get("parameters", {})),
                state="running",
                ready_at=now_naive,
                priority=task_orm.priority,
                updated_at=now_naive,
            )
        )

    # Flush now so the parent rows are physically inserted BEFORE the lease
    # insert below. SQLAlchemy does not reorder plain INSERTs by table-level FK
    # constraints (no relationship()), so without this the lease would violate
    # the step_run_id FK.  Still within the same claim transaction.
    await session.flush()

    logger.debug(f"Execution graph ensured for task [{task_orm.id}] (run={workflow_run_id})")


class SqlDurableTaskQueue(DurableTaskQueuePort, TaskLeasePort):
    """SQL adapter for atomic task claiming, fencing token generation, and lease locks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def claim_next(
        self,
        worker_id: str,
        lease_ttl_seconds: int = 30,
    ) -> Optional[ClaimedTask]:
        """Atomically claims the next pending or expired task in a single SQL transaction."""
        now = datetime.now(timezone.utc)
        now_naive = now.replace(tzinfo=None)
        expires_at = now + timedelta(seconds=lease_ttl_seconds)
        expires_at_naive = expires_at.replace(tzinfo=None)

        from sqlalchemy.exc import IntegrityError

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    # 1. Search for pending/received task
                    stmt = (
                        select(TaskRunORM)
                        .where(TaskRunORM.state.in_(["pending", "received"]))
                        .order_by(TaskRunORM.priority.desc(), TaskRunORM.created_at.asc())
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    res = await session.execute(stmt)
                    task_orm = res.scalar_one_or_none()

                    generation = 1
                    if task_orm is None:
                        # 2. Check for expired task lease in running state
                        stmt_expired = (
                            select(TaskRunORM, ExecutionLeaseORM)
                            .join(ExecutionLeaseORM, TaskRunORM.id == ExecutionLeaseORM.run_id)
                            .where(TaskRunORM.state == "running")
                            .where(ExecutionLeaseORM.status == "active")
                            .where(ExecutionLeaseORM.expires_at < now_naive)
                            .limit(1)
                            .with_for_update(skip_locked=True)
                        )
                        res_expired = await session.execute(stmt_expired)
                        row = res_expired.first()
                        if row is None:
                            return None
                        task_orm, lease_orm = row[0], row[1]
                        generation = (lease_orm.lease_generation or 1) + 1

                    # Parse facts payload once so both the execution graph and the
                    # ClaimedTask below can reuse it.
                    facts = json.loads(task_orm.facts_json) if task_orm.facts_json else {}

                    # GAP A: the lease's step_run_id FK requires a workflow_step_runs
                    # row (and its v2_workflow_runs_v2 parent). Create the graph
                    # idempotently in this same transaction before inserting the lease.
                    await _ensure_step_run_graph(session, task_orm, now_naive)

                    # Generation and fencing token
                    raw_tid = task_orm.id
                    fencing_token = f"fence_{raw_tid}_gen_{generation}_{uuid.uuid4().hex[:6]}"

                    # Atomic CAS guard & active lease check
                    stmt_existing_lease = select(ExecutionLeaseORM).where(ExecutionLeaseORM.run_id == raw_tid)
                    res_lease = await session.execute(stmt_existing_lease)
                    existing_lease = res_lease.scalar_one_or_none()

                    if existing_lease:
                        # If lease is active and unexpired, another worker won the race
                        if existing_lease.status == "active" and existing_lease.expires_at >= now_naive:
                            return None

                        existing_lease.worker_id = worker_id
                        existing_lease.status = "active"
                        existing_lease.expires_at = expires_at_naive
                        existing_lease.lease_generation = generation
                        existing_lease.fencing_token = fencing_token
                        existing_lease.updated_at = now_naive
                        lease_id = existing_lease.lease_id
                    else:
                        if generation > 1:
                            return None
                        lease_id = f"lease_{raw_tid}_{uuid.uuid4().hex[:8]}"
                        new_lease = ExecutionLeaseORM(
                            lease_id=lease_id,
                            step_run_id=raw_tid,
                            run_id=raw_tid,
                            worker_id=worker_id,
                            status="active",
                            expires_at=expires_at_naive,
                            idempotency_key=f"claim_{raw_tid}_{generation}",
                            lease_generation=generation,
                            fencing_token=fencing_token,
                            created_at=now_naive,
                            updated_at=now_naive,
                        )
                        session.add(new_lease)

                    # Update task state to running
                    task_orm.state = "running"
                    task_orm.updated_at = now_naive

                    prompt = facts.get("prompt", "")
                    tool_name = facts.get("tool_name", "read_file")
                    parameters = facts.get("parameters", {})

                    logger.info(f"Worker [{worker_id}] atomically claimed task [{raw_tid}] (gen: {generation}, fence: {fencing_token})")

                    return ClaimedTask(
                        task_id=raw_tid,
                        worker_id=worker_id,
                        lease_id=lease_id,
                        fencing_token=fencing_token,
                        lease_generation=generation,
                        tool_name=tool_name,
                        prompt=prompt,
                        parameters=parameters,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
        except IntegrityError:
            logger.debug(f"Worker [{worker_id}] lost atomic claim race to concurrent worker.")
            return None

    async def renew(self, task_id: str, worker_id: str, fencing_token: str, extension_seconds: int = 30) -> bool:
        """Renews an active lease if the fencing token matches."""
        now = datetime.now(timezone.utc)
        now_naive = now.replace(tzinfo=None)
        new_expires_at_naive = (now + timedelta(seconds=extension_seconds)).replace(tzinfo=None)

        async with self._session_factory() as session:
            async with session.begin():
                stmt = (
                    select(ExecutionLeaseORM)
                    .where(ExecutionLeaseORM.run_id == task_id)
                    .where(ExecutionLeaseORM.status == "active")
                    .where(ExecutionLeaseORM.fencing_token == fencing_token)
                )
                res = await session.execute(stmt)
                lease = res.scalar_one_or_none()
                if not lease:
                    logger.warning(f"Lease renewal rejected for task [{task_id}]: fencing token mismatch or inactive lease.")
                    return False

                lease.expires_at = new_expires_at_naive
                lease.updated_at = now_naive
                return True

    async def release(self, task_id: str, worker_id: str, fencing_token: str) -> bool:
        """Releases an active lease lock on task completion."""
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        async with self._session_factory() as session:
            async with session.begin():
                stmt = (
                    select(ExecutionLeaseORM)
                    .where(ExecutionLeaseORM.run_id == task_id)
                    .where(ExecutionLeaseORM.fencing_token == fencing_token)
                )
                res = await session.execute(stmt)
                lease = res.scalar_one_or_none()
                if not lease:
                    return False

                lease.status = "released"
                lease.updated_at = now_naive
                return True

    async def fail(self, task_id: str, worker_id: str, fencing_token: str, error: str) -> bool:
        """Marks a task as failed and releases lease lock."""
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        async with self._session_factory() as session:
            async with session.begin():
                # Update task state
                stmt_task = select(TaskRunORM).where(TaskRunORM.id == task_id)
                res_task = await session.execute(stmt_task)
                task_orm = res_task.scalar_one_or_none()
                if task_orm:
                    task_orm.state = "failed"
                    task_orm.last_error = error
                    task_orm.updated_at = now_naive

                # Release lease
                stmt_lease = (
                    select(ExecutionLeaseORM)
                    .where(ExecutionLeaseORM.run_id == task_id)
                    .where(ExecutionLeaseORM.fencing_token == fencing_token)
                )
                res_lease = await session.execute(stmt_lease)
                lease = res_lease.scalar_one_or_none()
                if lease:
                    lease.status = "released"
                    lease.updated_at = now_naive

                return True
