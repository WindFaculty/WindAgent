"""In-memory Agent Runtime store and transaction scope for unit tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.events import EventEnvelope

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


class InMemoryAgentRuntimeStore(AgentRuntimeStore):
    def __init__(self) -> None:
        self.sessions: dict[str, SessionRow] = {}
        self.runs: dict[str, RunRow] = {}
        self.tasks: dict[str, TaskRow] = {}
        self.workflows: dict[str, WorkflowRow] = {}
        self.steps: dict[str, StepRow] = {}
        self.checkpoints: dict[str, CheckpointRow] = {}
        self.approvals: dict[str, ApprovalRow] = {}
        self.delegations: dict[str, DelegationRow] = {}
        self.events: list[EventEnvelope] = []

    # -- sessions ------------------------------------------------------------
    async def insert_session(self, row: SessionRow) -> bool:
        if row.session_id in self.sessions:
            return False
        self.sessions[row.session_id] = row
        return True

    async def get_session(self, session_id: str) -> SessionRow | None:
        return self.sessions.get(session_id)

    async def list_sessions(self, actor_id: str | None = None) -> tuple[SessionRow, ...]:
        if actor_id is None:
            return tuple(self.sessions.values())
        return tuple(r for r in self.sessions.values() if r.actor_id == actor_id)

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
        existing = self.sessions.get(session_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = SessionRow(
            session_id=existing.session_id,
            actor_id=existing.actor_id,
            title=title if title is not None else existing.title,
            state=state if state is not None else existing.state,
            budget_limits_json=budget_limits_json if budget_limits_json is not None else existing.budget_limits_json,
            budget_usage_json=budget_usage_json if budget_usage_json is not None else existing.budget_usage_json,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.sessions[session_id] = updated
        return updated

    # -- runs ----------------------------------------------------------------
    async def insert_run(self, row: RunRow) -> bool:
        if row.run_id in self.runs:
            return False
        self.runs[row.run_id] = row
        return True

    async def get_run(self, run_id: str) -> RunRow | None:
        return self.runs.get(run_id)

    async def list_runs(self, session_id: str | None = None, parent_run_id: str | None = None) -> tuple[RunRow, ...]:
        rows = self.runs.values()
        if session_id is not None:
            rows = [r for r in rows if r.session_id == session_id]  # type: ignore[assignment]
        if parent_run_id is not None:
            rows = [r for r in rows if r.parent_run_id == parent_run_id]  # type: ignore[assignment]
        return tuple(rows)

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
        existing = self.runs.get(run_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = RunRow(
            run_id=existing.run_id,
            session_id=existing.session_id,
            parent_run_id=existing.parent_run_id,
            state=state if state is not None else existing.state,
            budget_scope=existing.budget_scope,
            budget_limits_json=budget_limits_json if budget_limits_json is not None else existing.budget_limits_json,
            budget_usage_json=budget_usage_json if budget_usage_json is not None else existing.budget_usage_json,
            exhaustion_reason=exhaustion_reason if exhaustion_reason is not None else existing.exhaustion_reason,
            attempt=attempt if attempt is not None else existing.attempt,
            max_attempts=existing.max_attempts,
            timeout_seconds=existing.timeout_seconds,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            completed_at=completed_at if completed_at is not None else existing.completed_at,
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        # Handle state-driven completed_at if transitioning to terminal and not explicitly set
        if state in ("COMPLETED", "FAILED", "CANCELLED", "ORPHANED") and updated.completed_at is None:
            updated = RunRow(
                run_id=updated.run_id,
                session_id=updated.session_id,
                parent_run_id=updated.parent_run_id,
                state=updated.state,
                budget_scope=updated.budget_scope,
                budget_limits_json=updated.budget_limits_json,
                budget_usage_json=updated.budget_usage_json,
                exhaustion_reason=updated.exhaustion_reason,
                attempt=updated.attempt,
                max_attempts=updated.max_attempts,
                timeout_seconds=updated.timeout_seconds,
                created_at=updated.created_at,
                updated_at=updated.updated_at,
                completed_at=datetime.now(UTC),
                optimistic_version=updated.optimistic_version,
                metadata_json=updated.metadata_json,
            )
        self.runs[run_id] = updated
        return updated

    # -- tasks ---------------------------------------------------------------
    async def insert_task(self, row: TaskRow) -> bool:
        if row.task_id in self.tasks:
            return False
        self.tasks[row.task_id] = row
        return True

    async def get_task(self, task_id: str) -> TaskRow | None:
        return self.tasks.get(task_id)

    async def list_tasks(
        self, session_id: str | None = None, run_id: str | None = None, workflow_id: str | None = None, state: str | None = None
    ) -> tuple[TaskRow, ...]:
        rows: Any = self.tasks.values()
        if session_id is not None:
            rows = [r for r in rows if r.session_id == session_id]
        if run_id is not None:
            rows = [r for r in rows if r.run_id == run_id]
        if workflow_id is not None:
            rows = [r for r in rows if r.workflow_id == workflow_id]
        if state is not None:
            rows = [r for r in rows if r.state == state]
        return tuple(rows)

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
        existing = self.tasks.get(task_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        # Handle explicit clearing vs keep: we treat None as "keep" for output/error unless needed.
        # For awaiting_approval_id and checkpoint_id, we need to allow clearing (None -> set to None) vs keep.
        # We use a sentinel: callers that want to keep pass the existing value implicitly by not changing?
        # Here we distinguish: if awaiting_approval_id is passed as existing value, we set; if None and caller intended keep, we keep existing.
        # For simplicity, we treat the passed awaiting_approval_id as explicit set only when it's not None OR caller wants to clear.
        # To support clearing, service will pass the existing awaiting_approval_id as well? We make explicit: if awaiting_approval_id is not None, set it, else keep existing unless checkpoint logic sets.
        # But for APPROVED resolve, service wants to clear: it passes awaiting_approval_id=None — we should clear.
        # We need a way to differentiate "don't change" vs "clear". We'll treat update_task's awaiting_approval_id as "set if not None or if we want to clear, we pass a marker".
        # Simpler: service passes awaiting_approval_id only when it wants to set/clear; we treat the argument as definitive if the task had an approval and now wants None, we clear.
        # Since Python default None means ambiguous, we check if caller explicitly passed awaiting_approval_id by inspecting whether the task is WAITING_PERMISSION and new state is RUNNING/FAILED -> then clear.
        # For now, implement: if awaiting_approval_id is not None, set; else if state indicates leaving WAITING_PERMISSION, clear.
        resolved_awaiting = existing.awaiting_approval_id
        if awaiting_approval_id is not None:
            resolved_awaiting = awaiting_approval_id
        else:
            # Clearing case: if we are moving away from WAITING_PERMISSION, clear
            if state is not None and state != "WAITING_PERMISSION" and existing.awaiting_approval_id is not None:
                resolved_awaiting = None
            # Also if explicit checkpoint update cleared? No.
        resolved_checkpoint = existing.checkpoint_id
        if checkpoint_id is not None:
            resolved_checkpoint = checkpoint_id
        updated = TaskRow(
            task_id=existing.task_id,
            session_id=existing.session_id,
            run_id=existing.run_id,
            workflow_id=existing.workflow_id,
            title=existing.title,
            description=existing.description,
            state=state if state is not None else existing.state,
            priority=existing.priority,
            attempt=attempt if attempt is not None else existing.attempt,
            max_attempts=existing.max_attempts,
            timeout_seconds=existing.timeout_seconds,
            input_payload_json=existing.input_payload_json,
            output_payload_json=output_payload_json if output_payload_json is not None else existing.output_payload_json,
            error=error if error is not None else existing.error,
            awaiting_approval_id=resolved_awaiting,
            checkpoint_id=resolved_checkpoint,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            completed_at=completed_at if completed_at is not None else (datetime.now(UTC) if state in ("COMPLETED", "FAILED", "CANCELLED") else existing.completed_at),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        # Handle explicit clearing of output/error when transitioning: keep logic above covers.
        # If output_payload_json wants to set, we already did; if we want to clear, not needed.
        self.tasks[task_id] = updated
        return updated

    # -- workflows -----------------------------------------------------------
    async def insert_workflow(self, row: WorkflowRow) -> bool:
        if row.workflow_id in self.workflows:
            return False
        self.workflows[row.workflow_id] = row
        return True

    async def get_workflow(self, workflow_id: str) -> WorkflowRow | None:
        return self.workflows.get(workflow_id)

    async def list_workflows(self, session_id: str | None = None) -> tuple[WorkflowRow, ...]:
        if session_id is None:
            return tuple(self.workflows.values())
        return tuple(r for r in self.workflows.values() if r.session_id == session_id)

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
        existing = self.workflows.get(workflow_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = WorkflowRow(
            workflow_id=existing.workflow_id,
            session_id=existing.session_id,
            name=existing.name,
            version=existing.version,
            state=state if state is not None else existing.state,
            nodes_json=nodes_json if nodes_json is not None else existing.nodes_json,
            edges_json=edges_json if edges_json is not None else existing.edges_json,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.workflows[workflow_id] = updated
        return updated

    # -- steps ---------------------------------------------------------------
    async def insert_step(self, row: StepRow) -> bool:
        if row.step_id in self.steps:
            return False
        self.steps[row.step_id] = row
        return True

    async def get_step(self, step_id: str) -> StepRow | None:
        return self.steps.get(step_id)

    async def list_steps(self, workflow_id: str | None = None, run_id: str | None = None) -> tuple[StepRow, ...]:
        rows: Any = self.steps.values()
        if workflow_id is not None:
            rows = [r for r in rows if r.workflow_id == workflow_id]
        if run_id is not None:
            rows = [r for r in rows if r.run_id == run_id]
        return tuple(rows)

    async def get_step_by_node(self, workflow_id: str, node_id: str) -> StepRow | None:
        for row in self.steps.values():
            if row.workflow_id == workflow_id and row.node_id == node_id:
                return row
        return None

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
        existing = self.steps.get(step_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = StepRow(
            step_id=existing.step_id,
            workflow_id=existing.workflow_id,
            run_id=existing.run_id,
            task_id=existing.task_id,
            node_id=existing.node_id,
            state=state if state is not None else existing.state,
            attempt=attempt if attempt is not None else existing.attempt,
            max_attempts=existing.max_attempts,
            priority=existing.priority,
            result_json=result_json if result_json is not None else existing.result_json,
            error=error if error is not None else existing.error,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
        )
        self.steps[step_id] = updated
        return updated

    # -- checkpoints ---------------------------------------------------------
    async def insert_checkpoint(self, row: CheckpointRow) -> bool:
        if row.checkpoint_id in self.checkpoints:
            return False
        # Check duplicate seq for same run_id+task_id
        for existing in self.checkpoints.values():
            if existing.run_id == row.run_id and existing.task_id == row.task_id and existing.seq == row.seq:
                return False
        self.checkpoints[row.checkpoint_id] = row
        return True

    async def get_checkpoint(self, checkpoint_id: str) -> CheckpointRow | None:
        return self.checkpoints.get(checkpoint_id)

    async def list_checkpoints(self, run_id: str | None = None, task_id: str | None = None) -> tuple[CheckpointRow, ...]:
        rows: Any = self.checkpoints.values()
        if run_id is not None:
            rows = [r for r in rows if r.run_id == run_id]
        if task_id is not None:
            rows = [r for r in rows if r.task_id == task_id]
        return tuple(sorted(rows, key=lambda c: c.seq))

    # -- approvals -----------------------------------------------------------
    async def insert_approval(self, row: ApprovalRow) -> bool:
        if row.approval_id in self.approvals:
            return False
        self.approvals[row.approval_id] = row
        return True

    async def get_approval(self, approval_id: str) -> ApprovalRow | None:
        return self.approvals.get(approval_id)

    async def list_approvals(self, task_id: str | None = None, state: str | None = None) -> tuple[ApprovalRow, ...]:
        rows: Any = self.approvals.values()
        if task_id is not None:
            rows = [r for r in rows if r.task_id == task_id]
        if state is not None:
            rows = [r for r in rows if r.state == state]
        return tuple(rows)

    async def update_approval(
        self,
        approval_id: str,
        *,
        state: str | None = None,
        resolution_json: str | None = None,
        expected_state: str | None = None,
    ) -> ApprovalRow | None:
        existing = self.approvals.get(approval_id)
        if existing is None:
            return None
        if expected_state is not None and existing.state != expected_state:
            return None
        updated = ApprovalRow(
            approval_id=existing.approval_id,
            task_id=existing.task_id,
            run_id=existing.run_id,
            requested_by=existing.requested_by,
            state=state if state is not None else existing.state,
            payload_json=existing.payload_json,
            resolution_json=resolution_json if resolution_json is not None else existing.resolution_json,
            created_at=existing.created_at,
            resolved_at=datetime.now(UTC) if state in ("APPROVED", "DENIED", "EXPIRED") else existing.resolved_at,
            expires_at=existing.expires_at,
        )
        self.approvals[approval_id] = updated
        return updated

    # -- delegations ---------------------------------------------------------
    async def insert_delegation(self, row: DelegationRow) -> bool:
        if row.delegation_id in self.delegations:
            return False
        self.delegations[row.delegation_id] = row
        return True

    async def get_delegation(self, delegation_id: str) -> DelegationRow | None:
        return self.delegations.get(delegation_id)

    async def list_delegations(self, parent_run_id: str | None = None, child_run_id: str | None = None) -> tuple[DelegationRow, ...]:
        rows: Any = self.delegations.values()
        if parent_run_id is not None:
            rows = [r for r in rows if r.parent_run_id == parent_run_id]
        if child_run_id is not None:
            rows = [r for r in rows if r.child_run_id == child_run_id]
        return tuple(rows)

    async def update_delegation(self, delegation_id: str, *, status: str | None = None) -> DelegationRow | None:
        existing = self.delegations.get(delegation_id)
        if existing is None:
            return None
        updated = DelegationRow(
            delegation_id=existing.delegation_id,
            parent_run_id=existing.parent_run_id,
            child_run_id=existing.child_run_id,
            status=status if status is not None else existing.status,
            created_at=existing.created_at,
            completed_at=datetime.now(UTC) if status in ("COMPLETED", "FAILED", "CANCELLED") else existing.completed_at,
            metadata_json=existing.metadata_json,
        )
        self.delegations[delegation_id] = updated
        return updated


class InMemoryTransactionScope:
    def __init__(self, store: InMemoryAgentRuntimeStore) -> None:
        self._store = store
        self._pending: list[tuple[EventEnvelope, str | None]] = []

    async def __aenter__(self) -> InMemoryTransactionScope:
        self._pending.clear()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool:
        if exc_type is not None:
            self._pending.clear()
        return False

    def store(self) -> InMemoryAgentRuntimeStore:
        return self._store

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        self._pending.append((envelope, deduplication_key))
        return True

    async def commit(self) -> None:
        for envelope, _ in self._pending:
            self._store.events.append(envelope)
        self._pending.clear()


def memory_scope_factory(store: InMemoryAgentRuntimeStore) -> Callable[[], InMemoryTransactionScope]:
    return lambda: InMemoryTransactionScope(store)
