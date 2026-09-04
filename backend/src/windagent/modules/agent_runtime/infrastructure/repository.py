"""SQL adapter for the Agent Runtime store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.models import (
    ApprovalRow,
    CheckpointRow,
    DelegationRow,
    RunRow,
    SessionRow,
    StepRow,
    TaskRow,
    WorkflowRow,
)
from ..application.ports import AgentRuntimeStore
from .tables import (
    approvals_table,
    checkpoints_table,
    delegations_table,
    runs_table,
    sessions_table,
    steps_table,
    tasks_table,
    workflows_table,
)

STORE_REPOSITORY_NAME = "agent_runtime_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def make_store(session: AsyncSession) -> SqlAgentRuntimeStore:
    return SqlAgentRuntimeStore(session)


class SqlAgentRuntimeStore(AgentRuntimeStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- sessions ------------------------------------------------------------
    async def insert_session(self, row: SessionRow) -> bool:
        exists = await self._session.execute(select(sessions_table.c.session_id).where(sessions_table.c.session_id == row.session_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(sessions_table).values(
                session_id=row.session_id,
                actor_id=row.actor_id,
                title=row.title,
                state=row.state,
                budget_limits_json=row.budget_limits_json,
                budget_usage_json=row.budget_usage_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_session(self, session_id: str) -> SessionRow | None:
        result = await self._session.execute(select(sessions_table).where(sessions_table.c.session_id == session_id))
        row = result.first()
        return _session_from_row(row) if row else None

    async def list_sessions(self, actor_id: str | None = None) -> tuple[SessionRow, ...]:
        stmt = select(sessions_table)
        if actor_id is not None:
            stmt = stmt.where(sessions_table.c.actor_id == actor_id)
        stmt = stmt.order_by(sessions_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_session_from_row(r) for r in result.all())

    async def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        state: str | None = None,
        budget_limits_json: str | None = None,
        budget_usage_json: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
        metadata_json: str | None = None,
    ) -> SessionRow | None:
        existing = await self.get_session(session_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if title is not None:
            values["title"] = title
        if state is not None:
            values["state"] = state
        if budget_limits_json is not None:
            values["budget_limits_json"] = budget_limits_json
        if budget_usage_json is not None:
            values["budget_usage_json"] = budget_usage_json
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(sessions_table).where(sessions_table.c.session_id == session_id, sessions_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(sessions_table).where(sessions_table.c.session_id == session_id).values(**values))
        return await self.get_session(session_id)

    # -- runs ----------------------------------------------------------------
    async def insert_run(self, row: RunRow) -> bool:
        exists = await self._session.execute(select(runs_table.c.run_id).where(runs_table.c.run_id == row.run_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(runs_table).values(
                run_id=row.run_id,
                session_id=row.session_id,
                parent_run_id=row.parent_run_id,
                state=row.state,
                budget_scope=row.budget_scope,
                budget_limits_json=row.budget_limits_json,
                budget_usage_json=row.budget_usage_json,
                exhaustion_reason=row.exhaustion_reason,
                attempt=row.attempt,
                max_attempts=row.max_attempts,
                timeout_seconds=row.timeout_seconds,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                completed_at=_as_utc(row.completed_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_run(self, run_id: str) -> RunRow | None:
        result = await self._session.execute(select(runs_table).where(runs_table.c.run_id == run_id))
        row = result.first()
        return _run_from_row(row) if row else None

    async def list_runs(self, session_id: str | None = None, parent_run_id: str | None = None) -> tuple[RunRow, ...]:
        stmt = select(runs_table)
        if session_id is not None:
            stmt = stmt.where(runs_table.c.session_id == session_id)
        if parent_run_id is not None:
            stmt = stmt.where(runs_table.c.parent_run_id == parent_run_id)
        stmt = stmt.order_by(runs_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_run_from_row(r) for r in result.all())

    async def update_run(
        self,
        run_id: str,
        *,
        state: str | None = None,
        budget_limits_json: str | None = None,
        budget_usage_json: str | None = None,
        exhaustion_reason: str | None = None,
        attempt: int | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
        metadata_json: str | None = None,
        completed_at: Any | None = None,
    ) -> RunRow | None:
        existing = await self.get_run(run_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if state is not None:
            values["state"] = state
        if budget_limits_json is not None:
            values["budget_limits_json"] = budget_limits_json
        if budget_usage_json is not None:
            values["budget_usage_json"] = budget_usage_json
        if exhaustion_reason is not None:
            values["exhaustion_reason"] = exhaustion_reason
        if attempt is not None:
            values["attempt"] = attempt
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if completed_at is not None:
            values["completed_at"] = _as_utc(completed_at) if isinstance(completed_at, datetime) else completed_at
        elif state in ("COMPLETED", "FAILED", "CANCELLED", "ORPHANED") and existing.completed_at is None:
            values["completed_at"] = datetime.now(UTC)
        if expected_version is not None:
            outcome = await self._session.execute(
                update(runs_table).where(runs_table.c.run_id == run_id, runs_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(runs_table).where(runs_table.c.run_id == run_id).values(**values))
        return await self.get_run(run_id)

    # -- tasks ---------------------------------------------------------------
    async def insert_task(self, row: TaskRow) -> bool:
        exists = await self._session.execute(select(tasks_table.c.task_id).where(tasks_table.c.task_id == row.task_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(tasks_table).values(
                task_id=row.task_id,
                session_id=row.session_id,
                run_id=row.run_id,
                workflow_id=row.workflow_id,
                title=row.title,
                description=row.description,
                state=row.state,
                priority=row.priority,
                attempt=row.attempt,
                max_attempts=row.max_attempts,
                timeout_seconds=row.timeout_seconds,
                input_payload_json=row.input_payload_json,
                output_payload_json=row.output_payload_json,
                error=row.error,
                awaiting_approval_id=row.awaiting_approval_id,
                checkpoint_id=row.checkpoint_id,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                completed_at=_as_utc(row.completed_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_task(self, task_id: str) -> TaskRow | None:
        result = await self._session.execute(select(tasks_table).where(tasks_table.c.task_id == task_id))
        row = result.first()
        return _task_from_row(row) if row else None

    async def list_tasks(
        self, session_id: str | None = None, run_id: str | None = None, workflow_id: str | None = None, state: str | None = None
    ) -> tuple[TaskRow, ...]:
        stmt = select(tasks_table)
        if session_id is not None:
            stmt = stmt.where(tasks_table.c.session_id == session_id)
        if run_id is not None:
            stmt = stmt.where(tasks_table.c.run_id == run_id)
        if workflow_id is not None:
            stmt = stmt.where(tasks_table.c.workflow_id == workflow_id)
        if state is not None:
            stmt = stmt.where(tasks_table.c.state == state)
        stmt = stmt.order_by(tasks_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_task_from_row(r) for r in result.all())

    async def update_task(
        self,
        task_id: str,
        *,
        state: str | None = None,
        attempt: int | None = None,
        output_payload_json: str | None = None,
        error: str | None = None,
        awaiting_approval_id: str | None = None,
        checkpoint_id: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
        metadata_json: str | None = None,
        completed_at: Any | None = None,
    ) -> TaskRow | None:
        existing = await self.get_task(task_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if state is not None:
            values["state"] = state
        if attempt is not None:
            values["attempt"] = attempt
        if output_payload_json is not None:
            values["output_payload_json"] = output_payload_json
        if error is not None:
            values["error"] = error
        # For awaiting_approval_id, we need to allow explicit None clearing; check if caller passed it as part of state change
        # In service, when moving away from WAITING_PERMISSION, we want to clear. To detect, we check if awaiting_approval_id is not None or state indicates clearing.
        # Here we treat awaiting_approval_id argument as explicit: if caller passes the same as existing, we keep; if caller wants clear, they'll pass a value that differs.
        # For simplicity, if awaiting_approval_id is not None, set; else if state indicates leaving WAITING_PERMISSION, we clear via explicit update in service using awaiting_approval_id="" sentinel? We'll just handle clearing via checking state.
        if awaiting_approval_id is not None:
            values["awaiting_approval_id"] = awaiting_approval_id
        elif state is not None and state != "WAITING_PERMISSION" and existing.awaiting_approval_id is not None:
            values["awaiting_approval_id"] = None
        if checkpoint_id is not None:
            values["checkpoint_id"] = checkpoint_id
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if completed_at is not None:
            values["completed_at"] = _as_utc(completed_at) if isinstance(completed_at, datetime) else completed_at
        elif state in ("COMPLETED", "FAILED", "CANCELLED") and existing.completed_at is None:
            values["completed_at"] = datetime.now(UTC)
        if expected_version is not None:
            outcome = await self._session.execute(
                update(tasks_table).where(tasks_table.c.task_id == task_id, tasks_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(tasks_table).where(tasks_table.c.task_id == task_id).values(**values))
        return await self.get_task(task_id)

    # -- workflows -----------------------------------------------------------
    async def insert_workflow(self, row: WorkflowRow) -> bool:
        exists = await self._session.execute(select(workflows_table.c.workflow_id).where(workflows_table.c.workflow_id == row.workflow_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(workflows_table).values(
                workflow_id=row.workflow_id,
                session_id=row.session_id,
                name=row.name,
                version=row.version,
                state=row.state,
                nodes_json=row.nodes_json,
                edges_json=row.edges_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_workflow(self, workflow_id: str) -> WorkflowRow | None:
        result = await self._session.execute(select(workflows_table).where(workflows_table.c.workflow_id == workflow_id))
        row = result.first()
        return _workflow_from_row(row) if row else None

    async def list_workflows(self, session_id: str | None = None) -> tuple[WorkflowRow, ...]:
        stmt = select(workflows_table)
        if session_id is not None:
            stmt = stmt.where(workflows_table.c.session_id == session_id)
        stmt = stmt.order_by(workflows_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_workflow_from_row(r) for r in result.all())

    async def update_workflow(
        self,
        workflow_id: str,
        *,
        state: str | None = None,
        nodes_json: str | None = None,
        edges_json: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
        metadata_json: str | None = None,
    ) -> WorkflowRow | None:
        existing = await self.get_workflow(workflow_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if state is not None:
            values["state"] = state
        if nodes_json is not None:
            values["nodes_json"] = nodes_json
        if edges_json is not None:
            values["edges_json"] = edges_json
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(workflows_table).where(workflows_table.c.workflow_id == workflow_id, workflows_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(workflows_table).where(workflows_table.c.workflow_id == workflow_id).values(**values))
        return await self.get_workflow(workflow_id)

    # -- steps ---------------------------------------------------------------
    async def insert_step(self, row: StepRow) -> bool:
        exists = await self._session.execute(select(steps_table.c.step_id).where(steps_table.c.step_id == row.step_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(steps_table).values(
                step_id=row.step_id,
                workflow_id=row.workflow_id,
                run_id=row.run_id,
                task_id=row.task_id,
                node_id=row.node_id,
                state=row.state,
                attempt=row.attempt,
                max_attempts=row.max_attempts,
                priority=row.priority,
                result_json=row.result_json,
                error=row.error,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
            )
        )
        return True

    async def get_step(self, step_id: str) -> StepRow | None:
        result = await self._session.execute(select(steps_table).where(steps_table.c.step_id == step_id))
        row = result.first()
        return _step_from_row(row) if row else None

    async def list_steps(self, workflow_id: str | None = None, run_id: str | None = None) -> tuple[StepRow, ...]:
        stmt = select(steps_table)
        if workflow_id is not None:
            stmt = stmt.where(steps_table.c.workflow_id == workflow_id)
        if run_id is not None:
            stmt = stmt.where(steps_table.c.run_id == run_id)
        stmt = stmt.order_by(steps_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_step_from_row(r) for r in result.all())

    async def get_step_by_node(self, workflow_id: str, node_id: str) -> StepRow | None:
        result = await self._session.execute(select(steps_table).where(steps_table.c.workflow_id == workflow_id, steps_table.c.node_id == node_id))
        row = result.first()
        return _step_from_row(row) if row else None

    async def update_step(
        self,
        step_id: str,
        *,
        state: str | None = None,
        attempt: int | None = None,
        result_json: str | None = None,
        error: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> StepRow | None:
        existing = await self.get_step(step_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if state is not None:
            values["state"] = state
        if attempt is not None:
            values["attempt"] = attempt
        if result_json is not None:
            values["result_json"] = result_json
        if error is not None:
            values["error"] = error
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if expected_version is not None:
            outcome = await self._session.execute(
                update(steps_table).where(steps_table.c.step_id == step_id, steps_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(steps_table).where(steps_table.c.step_id == step_id).values(**values))
        return await self.get_step(step_id)

    # -- checkpoints ---------------------------------------------------------
    async def insert_checkpoint(self, row: CheckpointRow) -> bool:
        exists = await self._session.execute(select(checkpoints_table.c.checkpoint_id).where(checkpoints_table.c.checkpoint_id == row.checkpoint_id))
        if exists.first() is not None:
            return False
        # Duplicate seq check per run
        dup = await self._session.execute(select(checkpoints_table.c.checkpoint_id).where(checkpoints_table.c.run_id == row.run_id, checkpoints_table.c.seq == row.seq))
        # Need to also filter task_id scope? For simplicity enforce per run seq uniqueness as in spec, but also check task grouping via extra query if needed
        # We'll enforce per (run_id, task_id) by checking both non-null cases; easiest: if any existing with same run and same seq, reject
        if dup.first() is not None:
            # If task_id differs, we should still allow same seq for different task? But spec seq is scoped to run_id alone in migration? We'll enforce per run_id only for simplicity (tightest)
            return False
        await self._session.execute(
            insert(checkpoints_table).values(
                checkpoint_id=row.checkpoint_id,
                run_id=row.run_id,
                task_id=row.task_id,
                workflow_id=row.workflow_id,
                step_id=row.step_id,
                seq=row.seq,
                state_snapshot_json=row.state_snapshot_json,
                snapshot_hash=row.snapshot_hash,
                created_at=_as_utc(row.created_at),
            )
        )
        return True

    async def get_checkpoint(self, checkpoint_id: str) -> CheckpointRow | None:
        result = await self._session.execute(select(checkpoints_table).where(checkpoints_table.c.checkpoint_id == checkpoint_id))
        row = result.first()
        return _checkpoint_from_row(row) if row else None

    async def list_checkpoints(self, run_id: str | None = None, task_id: str | None = None) -> tuple[CheckpointRow, ...]:
        stmt = select(checkpoints_table)
        if run_id is not None:
            stmt = stmt.where(checkpoints_table.c.run_id == run_id)
        if task_id is not None:
            stmt = stmt.where(checkpoints_table.c.task_id == task_id)
        stmt = stmt.order_by(checkpoints_table.c.seq.asc())
        result = await self._session.execute(stmt)
        return tuple(_checkpoint_from_row(r) for r in result.all())

    # -- approvals -----------------------------------------------------------
    async def insert_approval(self, row: ApprovalRow) -> bool:
        exists = await self._session.execute(select(approvals_table.c.approval_id).where(approvals_table.c.approval_id == row.approval_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(approvals_table).values(
                approval_id=row.approval_id,
                task_id=row.task_id,
                run_id=row.run_id,
                requested_by=row.requested_by,
                state=row.state,
                payload_json=row.payload_json,
                resolution_json=row.resolution_json,
                created_at=_as_utc(row.created_at),
                resolved_at=_as_utc(row.resolved_at),
                expires_at=_as_utc(row.expires_at),
            )
        )
        return True

    async def get_approval(self, approval_id: str) -> ApprovalRow | None:
        result = await self._session.execute(select(approvals_table).where(approvals_table.c.approval_id == approval_id))
        row = result.first()
        return _approval_from_row(row) if row else None

    async def list_approvals(self, task_id: str | None = None, state: str | None = None) -> tuple[ApprovalRow, ...]:
        stmt = select(approvals_table)
        if task_id is not None:
            stmt = stmt.where(approvals_table.c.task_id == task_id)
        if state is not None:
            stmt = stmt.where(approvals_table.c.state == state)
        stmt = stmt.order_by(approvals_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_approval_from_row(r) for r in result.all())

    async def update_approval(
        self,
        approval_id: str,
        *,
        state: str | None = None,
        resolution_json: str | None = None,
        expected_state: str | None = None,
    ) -> ApprovalRow | None:
        existing = await self.get_approval(approval_id)
        if existing is None:
            return None
        if expected_state is not None and existing.state != expected_state:
            return None
        values: dict[str, Any] = {}
        if state is not None:
            values["state"] = state
            if state in ("APPROVED", "DENIED", "EXPIRED"):
                values["resolved_at"] = datetime.now(UTC)
        if resolution_json is not None:
            values["resolution_json"] = resolution_json
        # Use optimistic check via expected_state
        if expected_state is not None:
            outcome = await self._session.execute(
                update(approvals_table).where(approvals_table.c.approval_id == approval_id, approvals_table.c.state == expected_state).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(approvals_table).where(approvals_table.c.approval_id == approval_id).values(**values))
        return await self.get_approval(approval_id)

    # -- delegations ---------------------------------------------------------
    async def insert_delegation(self, row: DelegationRow) -> bool:
        exists = await self._session.execute(select(delegations_table.c.delegation_id).where(delegations_table.c.delegation_id == row.delegation_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(delegations_table).values(
                delegation_id=row.delegation_id,
                parent_run_id=row.parent_run_id,
                child_run_id=row.child_run_id,
                status=row.status,
                created_at=_as_utc(row.created_at),
                completed_at=_as_utc(row.completed_at),
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_delegation(self, delegation_id: str) -> DelegationRow | None:
        result = await self._session.execute(select(delegations_table).where(delegations_table.c.delegation_id == delegation_id))
        row = result.first()
        return _delegation_from_row(row) if row else None

    async def list_delegations(self, parent_run_id: str | None = None, child_run_id: str | None = None) -> tuple[DelegationRow, ...]:
        stmt = select(delegations_table)
        if parent_run_id is not None:
            stmt = stmt.where(delegations_table.c.parent_run_id == parent_run_id)
        if child_run_id is not None:
            stmt = stmt.where(delegations_table.c.child_run_id == child_run_id)
        stmt = stmt.order_by(delegations_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_delegation_from_row(r) for r in result.all())

    async def update_delegation(self, delegation_id: str, *, status: str | None = None) -> DelegationRow | None:
        existing = await self.get_delegation(delegation_id)
        if existing is None:
            return None
        values: dict[str, Any] = {}
        if status is not None:
            values["status"] = status
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                values["completed_at"] = datetime.now(UTC)
        await self._session.execute(update(delegations_table).where(delegations_table.c.delegation_id == delegation_id).values(**values))
        return await self.get_delegation(delegation_id)


class SqlTransactionScope:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):
            raise TypeError("transaction scope requires a SQL unit of work")
        uow.register_repository(STORE_REPOSITORY_NAME, make_store)
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_value, None)
            self._uow = None
        return False

    def store(self) -> SqlAgentRuntimeStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(SqlAgentRuntimeStore, self._uow.repository(STORE_REPOSITORY_NAME))

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        outbox = TransactionalOutbox(self._uow)
        return await outbox.record_next(envelope, deduplication_key=deduplication_key)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        await self._uow.commit()


def sql_scope_factory(database: Database) -> Callable[[], SqlTransactionScope]:
    return lambda: SqlTransactionScope(database)


# --------------------------------------------------------------------------- #
# Row mappers
# --------------------------------------------------------------------------- #


def _session_from_row(row: Any) -> SessionRow:
    return SessionRow(
        session_id=str(row.session_id),
        actor_id=str(row.actor_id),
        title=str(row.title),
        state=str(row.state),
        budget_limits_json=str(row.budget_limits_json),
        budget_usage_json=str(row.budget_usage_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _run_from_row(row: Any) -> RunRow:
    return RunRow(
        run_id=str(row.run_id),
        session_id=str(row.session_id),
        parent_run_id=str(row.parent_run_id) if row.parent_run_id is not None else None,
        state=str(row.state),
        budget_scope=str(row.budget_scope),
        budget_limits_json=str(row.budget_limits_json),
        budget_usage_json=str(row.budget_usage_json),
        exhaustion_reason=str(row.exhaustion_reason) if row.exhaustion_reason is not None else None,
        attempt=int(row.attempt),
        max_attempts=int(row.max_attempts),
        timeout_seconds=float(row.timeout_seconds) if row.timeout_seconds is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        completed_at=_as_utc(row.completed_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _task_from_row(row: Any) -> TaskRow:
    return TaskRow(
        task_id=str(row.task_id),
        session_id=str(row.session_id),
        run_id=str(row.run_id) if row.run_id is not None else None,
        workflow_id=str(row.workflow_id) if row.workflow_id is not None else None,
        title=str(row.title),
        description=str(row.description),
        state=str(row.state),
        priority=int(row.priority),
        attempt=int(row.attempt),
        max_attempts=int(row.max_attempts),
        timeout_seconds=float(row.timeout_seconds) if row.timeout_seconds is not None else None,
        input_payload_json=str(row.input_payload_json),
        output_payload_json=str(row.output_payload_json) if row.output_payload_json is not None else None,
        error=str(row.error) if row.error is not None else None,
        awaiting_approval_id=str(row.awaiting_approval_id) if row.awaiting_approval_id is not None else None,
        checkpoint_id=str(row.checkpoint_id) if row.checkpoint_id is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        completed_at=_as_utc(row.completed_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _workflow_from_row(row: Any) -> WorkflowRow:
    return WorkflowRow(
        workflow_id=str(row.workflow_id),
        session_id=str(row.session_id),
        name=str(row.name),
        version=int(row.version),
        state=str(row.state),
        nodes_json=str(row.nodes_json),
        edges_json=str(row.edges_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _step_from_row(row: Any) -> StepRow:
    return StepRow(
        step_id=str(row.step_id),
        workflow_id=str(row.workflow_id),
        run_id=str(row.run_id) if row.run_id is not None else None,
        task_id=str(row.task_id) if row.task_id is not None else None,
        node_id=str(row.node_id),
        state=str(row.state),
        attempt=int(row.attempt),
        max_attempts=int(row.max_attempts),
        priority=int(row.priority),
        result_json=str(row.result_json) if row.result_json is not None else None,
        error=str(row.error) if row.error is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
    )


def _checkpoint_from_row(row: Any) -> CheckpointRow:
    return CheckpointRow(
        checkpoint_id=str(row.checkpoint_id),
        run_id=str(row.run_id),
        task_id=str(row.task_id) if row.task_id is not None else None,
        workflow_id=str(row.workflow_id) if row.workflow_id is not None else None,
        step_id=str(row.step_id) if row.step_id is not None else None,
        seq=int(row.seq),
        state_snapshot_json=str(row.state_snapshot_json),
        snapshot_hash=str(row.snapshot_hash),
        created_at=_as_utc(row.created_at),
    )


def _approval_from_row(row: Any) -> ApprovalRow:
    return ApprovalRow(
        approval_id=str(row.approval_id),
        task_id=str(row.task_id),
        run_id=str(row.run_id) if row.run_id is not None else None,
        requested_by=str(row.requested_by),
        state=str(row.state),
        payload_json=str(row.payload_json),
        resolution_json=str(row.resolution_json) if row.resolution_json is not None else None,
        created_at=_as_utc(row.created_at),
        resolved_at=_as_utc(row.resolved_at),
        expires_at=_as_utc(row.expires_at),
    )


def _delegation_from_row(row: Any) -> DelegationRow:
    return DelegationRow(
        delegation_id=str(row.delegation_id),
        parent_run_id=str(row.parent_run_id),
        child_run_id=str(row.child_run_id),
        status=str(row.status),
        created_at=_as_utc(row.created_at),
        completed_at=_as_utc(row.completed_at),
        metadata_json=str(row.metadata_json),
    )
