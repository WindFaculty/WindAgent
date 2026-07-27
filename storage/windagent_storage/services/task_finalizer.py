"""
Transactional Task Execution Finalizer for WindAgent Storage Layer (Phase 2).
Enforces single-transaction atomic task completion, CAS state update, result persistence,
terminal event & outbox insertion, and lease release (ban_ke_hoach.md §2).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING
from sqlalchemy import select, update, text

from windagent_core.contracts.finalization import (
    FinalizeTaskExecutionRequest,
    FinalizeTaskExecutionResult,
    StaleResultRejectedError,
)
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.orm.v2_orchestration_models import TaskRunORM, ExecutionLeaseORM, TaskExecutionResultORM

if TYPE_CHECKING:
    from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

logger = logging.getLogger("windagent.storage.task_finalizer")


class TaskFinalizer:
    """Helper for executing atomic task finalization within a SqlUnitOfWork context."""

    def __init__(self, uow: SqlUnitOfWork):
        self.uow = uow

    async def finalize_task_execution(
        self, request: FinalizeTaskExecutionRequest
    ) -> FinalizeTaskExecutionResult:
        """Executes task finalization within the active UnitOfWork transaction.

        Must be called inside an active `async with uow:` context.
        Rolls back the entire transaction if any failure occurs.
        """
        if not self.uow.session:
            raise RuntimeError("SqlUnitOfWork context is not active.")

        session = self.uow.session
        now_utc = datetime.now(timezone.utc)

        # ------------------------------------------------------------------ #
        # 1. Idempotency Check (Outbox or task completion check)
        # ------------------------------------------------------------------ #
        existing_outbox = (
            await session.execute(
                select(OutboxRecordORM).where(
                    OutboxRecordORM.deduplication_key == request.idempotency_key
                )
            )
        ).scalar_one_or_none()

        if existing_outbox:
            logger.info(f"Task finalization already processed idempotently: {request.idempotency_key}")
            return FinalizeTaskExecutionResult(
                status="COMPLETED",
                task_id=request.task_id,
                new_version=request.expected_task_version,
                idempotency_key=request.idempotency_key,
                already_finalized=True,
            )

        # ------------------------------------------------------------------ #
        # 2. Lease & Fencing Token Validation
        # ------------------------------------------------------------------ #
        lease = (
            await session.execute(
                select(ExecutionLeaseORM).where(
                    ExecutionLeaseORM.lease_id == request.lease_id,
                )
            )
        ).scalar_one_or_none()

        if lease is None:
            # Check if lease exists under run_id / task_id
            lease = (
                await session.execute(
                    select(ExecutionLeaseORM).where(ExecutionLeaseORM.run_id == request.task_id)
                )
            ).scalar_one_or_none()

        if lease is not None and hasattr(lease, "fencing_token"):
            if lease.fencing_token and lease.fencing_token != request.fencing_token:
                logger.warning(
                    f"Fencing token mismatch: expected {lease.fencing_token}, got {request.fencing_token}"
                )
                raise StaleResultRejectedError(
                    request.task_id, request.fencing_token, request.expected_task_version
                )

        # ------------------------------------------------------------------ #
        # 3. Conditional Compare-And-Swap (CAS) Task State & Version Update
        # ------------------------------------------------------------------ #
        task = (
            await session.execute(
                select(TaskRunORM).where(TaskRunORM.id == request.task_id)
            )
        ).scalar_one_or_none()

        if task is None:
            raise ValueError(f"Task '{request.task_id}' not found for finalization.")

        if task.state != "running" and task.state != "pending" and task.state != "received":
            if task.version >= request.expected_task_version:
                # Already finalized by another attempt or recovery
                logger.warning(f"Task '{request.task_id}' state is '{task.state}' (not running). Rejecting stale result.")
                raise StaleResultRejectedError(
                    request.task_id, request.fencing_token, request.expected_task_version
                )

        # Perform CAS update
        stmt = (
            update(TaskRunORM)
            .where(
                TaskRunORM.id == request.task_id,
                TaskRunORM.version == request.expected_task_version,
            )
            .values(
                state=request.terminal_state,
                version=TaskRunORM.version + 1,
                updated_at=now_utc,
            )
        )
        res = await session.execute(stmt)
        if res.rowcount == 0:
            # Re-fetch task to check actual version
            latest = (
                await session.execute(
                    select(TaskRunORM).where(TaskRunORM.id == request.task_id)
                )
            ).scalar_one_or_none()
            curr_ver = latest.version if latest else -1
            logger.warning(
                f"CAS update failed for task {request.task_id}. Expected version {request.expected_task_version}, current {curr_ver}."
            )
            raise StaleResultRejectedError(
                request.task_id, request.fencing_token, request.expected_task_version
            )

        new_version = request.expected_task_version + 1

        # ------------------------------------------------------------------ #
        # 4. Persist Execution Result & Artifact References
        # ------------------------------------------------------------------ #
        result_orm = TaskExecutionResultORM(
            id=f"res-{request.task_id}-{new_version}",
            task_id=request.task_id,
            worker_id=request.worker_id,
            execution_status=request.terminal_state,
            result_data=request.execution_result,
            artifacts_data=request.result_artifacts,
            created_at=now_utc,
        )
        session.add(result_orm)

        # Also update the task facts with the result so API can read it
        existing_facts = json.loads(task.facts_json) if task.facts_json else {}
        existing_facts.update({
            "result": request.execution_result,
            "terminal_state": request.terminal_state,
            "completed_at": now_utc.isoformat(),
        })
        task.facts_json = json.dumps(existing_facts)

        # ------------------------------------------------------------------ #
        # 5. Insert Terminal Event & Outbox Record with Idempotency Key
        # ------------------------------------------------------------------ #
        event_dict = request.terminal_event or {
            "event_type": "task_completed",
            "task_id": request.task_id,
            "worker_id": request.worker_id,
            "terminal_state": request.terminal_state,
            "version": new_version,
        }

        from windagent_core.domain.types import EventId

        envelope = EventEnvelope(
            event_id=EventId.generate(),
            event_type=event_dict.get("event_type", "task_completed"),
            aggregate_id=request.task_id,
            payload=event_dict,
            metadata={"idempotency_key": request.idempotency_key},
        )

        await self.uow.record_outbox_event(envelope)

        # ------------------------------------------------------------------ #
        # 6. Mark Lease Released / Completed
        # ------------------------------------------------------------------ #
        if lease:
            lease.status = "completed"
            lease.released_at = now_utc

        # ------------------------------------------------------------------ #
        # 7. Commit Transaction
        # ------------------------------------------------------------------ #
        await self.uow.commit()

        return FinalizeTaskExecutionResult(
            status="COMPLETED",
            task_id=request.task_id,
            new_version=new_version,
            idempotency_key=request.idempotency_key,
            already_finalized=False,
        )
