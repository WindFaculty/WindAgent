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
from windagent_storage.orm.v2_orchestration_models import TaskRunORM, ExecutionLeaseORM

logger = logging.getLogger("windagent.storage.queue.sql")


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

                # Generate fencing token and lease ID
                raw_tid = task_orm.id
                fencing_token = f"fence_{raw_tid}_gen_{generation}_{uuid.uuid4().hex[:6]}"
                lease_id = f"lease_{raw_tid}_{uuid.uuid4().hex[:8]}"

                # Update task state to running
                task_orm.state = "running"
                task_orm.updated_at = now_naive

                # Upsert lease lock record
                stmt_existing_lease = select(ExecutionLeaseORM).where(ExecutionLeaseORM.run_id == raw_tid)
                res_lease = await session.execute(stmt_existing_lease)
                existing_lease = res_lease.scalar_one_or_none()

                if existing_lease:
                    existing_lease.worker_id = worker_id
                    existing_lease.status = "active"
                    existing_lease.expires_at = expires_at_naive
                    existing_lease.lease_generation = generation
                    existing_lease.fencing_token = fencing_token
                    existing_lease.updated_at = now_naive
                else:
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

                # Parse facts payload
                facts = json.loads(task_orm.facts_json) if task_orm.facts_json else {}
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
