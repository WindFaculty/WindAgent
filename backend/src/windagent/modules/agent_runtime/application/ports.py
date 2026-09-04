"""Repository port for Agent Runtime persistence."""

from __future__ import annotations

from typing import Any, Protocol

from windagent.kernel.events import EventEnvelope

from .models import (
    ApprovalRow,
    CheckpointRow,
    DelegationRow,
    RunRow,
    SessionRow,
    StepRow,
    TaskRow,
    WorkflowRow,
)


class AgentRuntimeStore(Protocol):
    # -- sessions ------------------------------------------------------------
    async def insert_session(self, row: SessionRow) -> bool: ...
    async def get_session(self, session_id: str) -> SessionRow | None: ...
    async def list_sessions(self, actor_id: str | None = None) -> tuple[SessionRow, ...]: ...
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
    ) -> SessionRow | None: ...

    # -- runs ----------------------------------------------------------------
    async def insert_run(self, row: RunRow) -> bool: ...
    async def get_run(self, run_id: str) -> RunRow | None: ...
    async def list_runs(self, session_id: str | None = None, parent_run_id: str | None = None) -> tuple[RunRow, ...]: ...
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
    ) -> RunRow | None: ...

    # -- tasks ---------------------------------------------------------------
    async def insert_task(self, row: TaskRow) -> bool: ...
    async def get_task(self, task_id: str) -> TaskRow | None: ...
    async def list_tasks(
        self, session_id: str | None = None, run_id: str | None = None, workflow_id: str | None = None, state: str | None = None
    ) -> tuple[TaskRow, ...]: ...
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
    ) -> TaskRow | None: ...

    # -- workflows -----------------------------------------------------------
    async def insert_workflow(self, row: WorkflowRow) -> bool: ...
    async def get_workflow(self, workflow_id: str) -> WorkflowRow | None: ...
    async def list_workflows(self, session_id: str | None = None) -> tuple[WorkflowRow, ...]: ...
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
    ) -> WorkflowRow | None: ...

    # -- steps ---------------------------------------------------------------
    async def insert_step(self, row: StepRow) -> bool: ...
    async def get_step(self, step_id: str) -> StepRow | None: ...
    async def list_steps(self, workflow_id: str | None = None, run_id: str | None = None) -> tuple[StepRow, ...]: ...
    async def get_step_by_node(self, workflow_id: str, node_id: str) -> StepRow | None: ...
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
    ) -> StepRow | None: ...

    # -- checkpoints ---------------------------------------------------------
    async def insert_checkpoint(self, row: CheckpointRow) -> bool: ...
    async def get_checkpoint(self, checkpoint_id: str) -> CheckpointRow | None: ...
    async def list_checkpoints(self, run_id: str | None = None, task_id: str | None = None) -> tuple[CheckpointRow, ...]: ...

    # -- approvals -----------------------------------------------------------
    async def insert_approval(self, row: ApprovalRow) -> bool: ...
    async def get_approval(self, approval_id: str) -> ApprovalRow | None: ...
    async def list_approvals(self, task_id: str | None = None, state: str | None = None) -> tuple[ApprovalRow, ...]: ...
    async def update_approval(
        self,
        approval_id: str,
        *,
        state: str | None = None,
        resolution_json: str | None = None,
        expected_state: str | None = None,
    ) -> ApprovalRow | None: ...

    # -- delegations ---------------------------------------------------------
    async def insert_delegation(self, row: DelegationRow) -> bool: ...
    async def get_delegation(self, delegation_id: str) -> DelegationRow | None: ...
    async def list_delegations(self, parent_run_id: str | None = None, child_run_id: str | None = None) -> tuple[DelegationRow, ...]: ...
    async def update_delegation(self, delegation_id: str, *, status: str | None = None) -> DelegationRow | None: ...


class TransactionScope(Protocol):
    def store(self) -> AgentRuntimeStore: ...
    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool: ...
    async def commit(self) -> None: ...
    async def __aenter__(self) -> TransactionScope: ...
    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool: ...
