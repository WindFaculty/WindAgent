"""
Durable Repositories for Orchestration V2 Storage Layer.
Implements SQL repositories with optimistic concurrency, atomic lease acquisition, checkpoints, worker registries, and outbox records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_storage.orm.v2_orchestration_models import (
    TaskRunORM, WorkflowRunV2ORM, WorkflowStepRunORM,
    ExecutionLeaseORM, ExecutionAttemptORM, WorkflowCheckpointORM,
    CancellationRequestORM, WorkerRegistrationORM
)
from windagent_storage.orm.models import OutboxRecordORM
from windagent_core.errors.exceptions import DomainError


class SqlTaskRunRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(TaskRunORM).where(TaskRunORM.id == task_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        return {
            "id": orm.id,
            "session_id": orm.session_id,
            "state": orm.state,
            "version": orm.version,
            "priority": orm.priority,
            "current_step": orm.current_step,
            "total_steps": orm.total_steps,
            "pending_permission": orm.pending_permission,
            "retry_count": orm.retry_count,
            "last_error": orm.last_error,
            "project_id": orm.project_id,
            "worktree_id": orm.worktree_id,
            "facts": json.loads(orm.facts_json) if orm.facts_json else {},
            "created_at": orm.created_at,
            "updated_at": orm.updated_at,
        }

    async def save_facts(self, task_id: str, session_id: str, state: str, version: int, facts: Dict[str, Any]) -> int:
        now = datetime.now(timezone.utc)
        facts_json_str = json.dumps(facts)

        stmt = select(TaskRunORM).where(TaskRunORM.id == task_id)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()

        if not orm:
            new_orm = TaskRunORM(
                id=task_id,
                session_id=session_id,
                state=state,
                version=1,
                priority=facts.get("priority", 2),
                current_step=facts.get("current_step", 0),
                total_steps=facts.get("total_steps", 0),
                pending_permission=facts.get("pending_permission", False),
                retry_count=facts.get("retry_count", 0),
                last_error=facts.get("last_error"),
                project_id=facts.get("project_id"),
                worktree_id=facts.get("worktree_id"),
                facts_json=facts_json_str,
                created_at=now,
                updated_at=now,
            )
            self._session.add(new_orm)
            return 1

        # Optimistic concurrency check
        if orm.version != version:
            raise DomainError(
                message=f"Optimistic concurrency violation for task [{task_id}]: expected version {version}, found {orm.version}",
                code="WINDAGENT_ERR_OPTIMISTIC_CONCURRENCY_VIOLATION",
                details={"task_id": task_id, "expected_version": version, "actual_version": orm.version},
            )

        new_version = version + 1
        facts["version"] = new_version

        orm.state = state
        orm.version = new_version
        orm.priority = facts.get("priority", orm.priority)
        orm.current_step = facts.get("current_step", orm.current_step)
        orm.total_steps = facts.get("total_steps", orm.total_steps)
        orm.pending_permission = facts.get("pending_permission", orm.pending_permission)
        orm.retry_count = facts.get("retry_count", orm.retry_count)
        orm.last_error = facts.get("last_error", orm.last_error)
        orm.facts_json = json.dumps(facts)
        orm.updated_at = now

        return new_version

    async def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        stmt = select(TaskRunORM).where(TaskRunORM.session_id == session_id).order_by(TaskRunORM.created_at.asc())
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [
            {
                "id": o.id,
                "session_id": o.session_id,
                "state": o.state,
                "version": o.version,
                "priority": o.priority,
                "facts": json.loads(o.facts_json) if o.facts_json else {},
                "created_at": o.created_at,
            }
            for o in orms
        ]


class SqlExecutionLeaseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def acquire_lease(
        self,
        lease_id: str,
        step_run_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: float,
        idempotency_key: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

        # Deduplication / Idempotency check
        stmt = select(ExecutionLeaseORM).where(ExecutionLeaseORM.idempotency_key == idempotency_key)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            if existing.status == "active" and existing.expires_at > now:
                return existing.lease_id == lease_id
            # Lease expired -> update lease to new worker
            existing.worker_id = worker_id
            existing.status = "active"
            existing.expires_at = expires_at
            existing.updated_at = now
            return True

        new_lease = ExecutionLeaseORM(
            lease_id=lease_id,
            step_run_id=step_run_id,
            run_id=run_id,
            worker_id=worker_id,
            status="active",
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self._session.add(new_lease)
        return True

    async def release_lease(self, lease_id: str, worker_id: str) -> bool:
        stmt = select(ExecutionLeaseORM).where(
            ExecutionLeaseORM.lease_id == lease_id,
            ExecutionLeaseORM.worker_id == worker_id,
        )
        res = await self._session.execute(stmt)
        lease = res.scalar_one_or_none()
        if lease:
            lease.status = "released"
            lease.updated_at = datetime.now(timezone.utc)
            return True
        return False

    async def reclaim_expired_leases(self) -> List[str]:
        now = datetime.now(timezone.utc)
        stmt = select(ExecutionLeaseORM).where(
            ExecutionLeaseORM.status == "active",
            ExecutionLeaseORM.expires_at <= now,
        )
        res = await self._session.execute(stmt)
        expired_leases = res.scalars().all()
        reclaimed_ids = []

        for lease in expired_leases:
            lease.status = "expired"
            lease.updated_at = now
            reclaimed_ids.append(lease.lease_id)

        return reclaimed_ids


class SqlWorkflowCheckpointRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_checkpoint(self, checkpoint_id: str, run_id: str, step_id: str, cursor: int, state_data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        ckpt = WorkflowCheckpointORM(
            id=checkpoint_id,
            run_id=run_id,
            step_id=step_id,
            cursor=cursor,
            state_json=json.dumps(state_data),
            created_at=now,
        )
        self._session.add(ckpt)

    async def get_latest_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(WorkflowCheckpointORM).where(WorkflowCheckpointORM.run_id == run_id).order_by(WorkflowCheckpointORM.cursor.desc()).limit(1)
        res = await self._session.execute(stmt)
        ckpt = res.scalar_one_or_none()
        if not ckpt:
            return None
        return {
            "id": ckpt.id,
            "run_id": ckpt.run_id,
            "step_id": ckpt.step_id,
            "cursor": ckpt.cursor,
            "state_data": json.loads(ckpt.state_json),
            "created_at": ckpt.created_at,
        }


class SqlCancellationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def request_cancellation(self, req_id: str, target_id: str, target_type: str, reason: str, requested_by: str = "user") -> None:
        now = datetime.now(timezone.utc)
        req = CancellationRequestORM(
            id=req_id,
            target_id=target_id,
            target_type=target_type,
            reason=reason,
            requested_by=requested_by,
            status="pending",
            created_at=now,
        )
        self._session.add(req)

    async def is_cancelled(self, target_id: str) -> bool:
        stmt = select(CancellationRequestORM).where(CancellationRequestORM.target_id == target_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None
