"""
Durable Repositories for Orchestration V2 Storage Layer.
Implements SQL repositories with atomic conditional updates, optimistic concurrency, lease acquisition with fencing tokens, runtime executions, recovery leader lease, checkpoints, and outbox records.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_storage.orm.v2_orchestration_models import (
    TaskRunORM, ExecutionLeaseORM, WorkflowCheckpointORM,
    CancellationRequestORM, RuntimeExecutionORM, RecoveryLeaderLeaseORM,
    MemoryRecordORM,
)
from windagent_core.errors.exceptions import DomainError


def _ensure_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


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

        # Atomic conditional UPDATE check
        new_version = version + 1
        facts["version"] = new_version
        update_stmt = (
            update(TaskRunORM)
            .where(TaskRunORM.id == task_id, TaskRunORM.version == version)
            .values(
                state=state,
                version=new_version,
                priority=facts.get("priority", orm.priority),
                current_step=facts.get("current_step", orm.current_step),
                total_steps=facts.get("total_steps", orm.total_steps),
                pending_permission=facts.get("pending_permission", orm.pending_permission),
                retry_count=facts.get("retry_count", orm.retry_count),
                last_error=facts.get("last_error", orm.last_error),
                facts_json=json.dumps(facts),
                updated_at=now,
            )
        )
        result = await self._session.execute(update_stmt)
        if result.rowcount == 0:
            raise DomainError(
                message=f"Optimistic concurrency violation for task [{task_id}]: expected version {version}",
                code="WINDAGENT_ERR_OPTIMISTIC_CONCURRENCY_VIOLATION",
                details={"task_id": task_id, "expected_version": version},
            )

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
    ) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

        stmt = select(ExecutionLeaseORM).where(ExecutionLeaseORM.idempotency_key == idempotency_key)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing_exp = _ensure_naive_utc(existing.expires_at)
            now_naive = _ensure_naive_utc(now)
            if existing.status == "active" and existing_exp > now_naive:
                if existing.lease_id == lease_id:
                    return {
                        "lease_id": existing.lease_id,
                        "lease_generation": existing.lease_generation,
                        "fencing_token": existing.fencing_token,
                    }
                return None
            elif existing.status in ("released", "completed"):
                # Already finalized lease -> reject duplicate claim
                return None

            # Lease expired -> takeover by new worker, bump generation
            new_gen = (existing.lease_generation or 1) + 1
            fencing_token = f"fence_{existing.step_run_id}_gen_{new_gen}_{uuid.uuid4().hex[:6]}"
            existing.worker_id = worker_id
            existing.status = "active"
            existing.expires_at = expires_at
            existing.lease_generation = new_gen
            existing.fencing_token = fencing_token
            existing.updated_at = now
            return {
                "lease_id": existing.lease_id,
                "lease_generation": new_gen,
                "fencing_token": fencing_token,
            }

        fencing_token = f"fence_{step_run_id}_gen_1_{uuid.uuid4().hex[:6]}"
        new_lease = ExecutionLeaseORM(
            lease_id=lease_id,
            step_run_id=step_run_id,
            run_id=run_id,
            worker_id=worker_id,
            status="active",
            expires_at=expires_at,
            idempotency_key=idempotency_key,
            lease_generation=1,
            fencing_token=fencing_token,
            created_at=now,
            updated_at=now,
        )
        try:
            self._session.add(new_lease)
            await self._session.flush()
        except Exception:
            try:
                await self._session.rollback()
            except Exception:
                pass
            return None
        return {
            "lease_id": lease_id,
            "lease_generation": 1,
            "fencing_token": fencing_token,
        }

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
        now_naive = _ensure_naive_utc(now)
        stmt = select(ExecutionLeaseORM).where(
            ExecutionLeaseORM.status == "active",
        )
        res = await self._session.execute(stmt)
        active_leases = res.scalars().all()
        reclaimed_ids = []

        for lease in active_leases:
            if _ensure_naive_utc(lease.expires_at) <= now_naive:
                lease.status = "expired"
                lease.updated_at = now
                reclaimed_ids.append(lease.lease_id)

        return reclaimed_ids


class SqlRuntimeExecutionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_execution(
        self,
        execution_id: str,
        runtime_run_id: str,
        attempt_id: str,
        step_run_id: str,
        lease_generation: int,
        fencing_token: str,
        runtime_session_id: Optional[str] = None,
    ) -> RuntimeExecutionORM:
        now = datetime.now(timezone.utc)
        orm = RuntimeExecutionORM(
            id=execution_id,
            runtime_run_id=runtime_run_id,
            runtime_session_id=runtime_session_id,
            attempt_id=attempt_id,
            step_run_id=step_run_id,
            lease_generation=lease_generation,
            fencing_token=fencing_token,
            status="dispatched",
            heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )
        self._session.add(orm)
        return orm

    async def update_status_by_fencing_token(
        self,
        step_run_id: str,
        fencing_token: str,
        status: str,
        result_ref: Optional[str] = None,
        error_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        error_json = json.dumps(error_metadata) if error_metadata else None
        stmt = (
            update(RuntimeExecutionORM)
            .where(
                RuntimeExecutionORM.step_run_id == step_run_id,
                RuntimeExecutionORM.fencing_token == fencing_token,
            )
            .values(
                status=status,
                result_ref=result_ref,
                error_metadata_json=error_json,
                updated_at=now,
            )
        )
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def get_by_step_run_id(self, step_run_id: str) -> Optional[RuntimeExecutionORM]:
        stmt = select(RuntimeExecutionORM).where(RuntimeExecutionORM.step_run_id == step_run_id).order_by(RuntimeExecutionORM.created_at.desc())
        res = await self._session.execute(stmt)
        return res.scalars().first()


class SqlRecoveryLeaderLeaseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def acquire_leader_lease(self, leader_id: str, ttl_seconds: float = 30.0) -> bool:
        now = datetime.now(timezone.utc)
        now_naive = _ensure_naive_utc(now)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

        stmt = select(RecoveryLeaderLeaseORM).where(RecoveryLeaderLeaseORM.lease_name == "recovery_leader")
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            if _ensure_naive_utc(existing.expires_at) > now_naive:
                return existing.leader_id == leader_id
            existing.leader_id = leader_id
            existing.expires_at = expires_at
            existing.updated_at = now
            return True

        new_lease = RecoveryLeaderLeaseORM(
            lease_name="recovery_leader",
            leader_id=leader_id,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self._session.add(new_lease)
        return True


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


class SqlMemoryRecordRepository:
    """Phase 13C — Memory records repository (Memory != Database).

    Keeps ORM access in the storage layer so routers stay in the application
    layer without sqlalchemy / ORM imports (architecture boundary).
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_records(
        self,
        scope: Optional[str] = None,
        owner: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryRecordORM]:
        stmt = select(MemoryRecordORM).order_by(MemoryRecordORM.updated_at.desc()).limit(limit)
        if scope:
            stmt = stmt.where(MemoryRecordORM.memory_type == scope)
        if owner:
            stmt = stmt.where(MemoryRecordORM.session_id == owner)
        if memory_type:
            stmt = stmt.where(MemoryRecordORM.memory_type == memory_type)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_record(self, memory_id: str) -> Optional[MemoryRecordORM]:
        return await self._session.get(MemoryRecordORM, memory_id)

    async def create_record(
        self,
        record_id: str,
        session_id: Optional[str],
        memory_type: str,
        key: str,
        value_json: str,
        now: datetime,
    ) -> MemoryRecordORM:
        orm = MemoryRecordORM(
            id=record_id,
            session_id=session_id,
            memory_type=memory_type,
            key=key,
            value_json=value_json,
            created_at=now,
            updated_at=now,
        )
        self._session.add(orm)
        return orm

    async def search_records(
        self,
        scope: Optional[str] = None,
        owner: Optional[str] = None,
        limit: int = 20,
    ) -> List[MemoryRecordORM]:
        stmt = select(MemoryRecordORM).order_by(MemoryRecordORM.updated_at.desc()).limit(limit)
        if scope:
            stmt = stmt.where(MemoryRecordORM.memory_type == scope)
        if owner:
            stmt = stmt.where(MemoryRecordORM.session_id == owner)
        return list((await self._session.execute(stmt)).scalars().all())
