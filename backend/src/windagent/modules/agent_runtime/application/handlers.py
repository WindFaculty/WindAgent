"""Application handlers connecting commands/queries/jobs to services."""

from __future__ import annotations

from typing import Any

from .commands import (
    CompleteTask,
    CreateCheckpoint,
    CreateRun,
    CreateSession,
    CreateTask,
    CreateWorkflow,
    DelegateRun,
    FailTask,
    RecordRunBudgetUsage,
    RequestApproval,
    ResolveApproval,
    RetryTask,
    ScheduleWorkflow,
    TransitionDelegation,
    TransitionRun,
    TransitionSession,
    TransitionStep,
    TransitionTask,
    TransitionWorkflow,
)
from .queries import (
    GetApproval,
    GetCheckpoint,
    GetDelegation,
    GetRun,
    GetSession,
    GetStep,
    GetTask,
    GetWorkflow,
    ListApprovals,
    ListCheckpoints,
    ListDelegations,
    ListRuns,
    ListSessions,
    ListSteps,
    ListTasks,
    ListWorkflows,
)
from .runtime import AgentRuntimeServices, container_for


class _Handler:
    def __init__(self, services: AgentRuntimeServices | None = None) -> None:
        self._services = services


# -- sessions ------------------------------------------------------------


class CreateSessionHandler(_Handler):
    async def handle(self, cmd: CreateSession) -> Any:
        return await container_for(self._services).agent_runtime.create_session(
            actor_id=cmd.actor_id, title=cmd.title, budget_limits=cmd.budget_limits, metadata=cmd.metadata
        )


class TransitionSessionHandler(_Handler):
    async def handle(self, cmd: TransitionSession) -> Any:
        return await container_for(self._services).agent_runtime.transition_session(
            session_id=cmd.session_id, target_state=cmd.target_state, expected_version=cmd.expected_version
        )


class GetSessionHandler(_Handler):
    async def handle(self, q: GetSession) -> Any:
        return await container_for(self._services).agent_runtime.get_session(q.session_id)


class ListSessionsHandler(_Handler):
    async def handle(self, q: ListSessions) -> Any:
        return await container_for(self._services).agent_runtime.list_sessions(q.actor_id)


# -- runs ----------------------------------------------------------------


class CreateRunHandler(_Handler):
    async def handle(self, cmd: CreateRun) -> Any:
        return await container_for(self._services).agent_runtime.create_run(
            session_id=cmd.session_id,
            parent_run_id=cmd.parent_run_id,
            budget_scope=cmd.budget_scope,
            budget_limits=cmd.budget_limits,
            max_attempts=cmd.max_attempts,
            timeout_seconds=cmd.timeout_seconds,
            metadata=cmd.metadata,
        )


class TransitionRunHandler(_Handler):
    async def handle(self, cmd: TransitionRun) -> Any:
        return await container_for(self._services).agent_runtime.transition_run(
            run_id=cmd.run_id, target_state=cmd.target_state, expected_version=cmd.expected_version, exhaustion_reason=cmd.exhaustion_reason
        )


class RecordRunBudgetUsageHandler(_Handler):
    async def handle(self, cmd: RecordRunBudgetUsage) -> Any:
        return await container_for(self._services).agent_runtime.record_run_budget_usage(
            run_id=cmd.run_id, usage_patch=cmd.usage_patch, expected_version=cmd.expected_version
        )


class GetRunHandler(_Handler):
    async def handle(self, q: GetRun) -> Any:
        return await container_for(self._services).agent_runtime.get_run(q.run_id)


class ListRunsHandler(_Handler):
    async def handle(self, q: ListRuns) -> Any:
        return await container_for(self._services).agent_runtime.list_runs(q.session_id, q.parent_run_id)


# -- tasks ----------------------------------------------------------------


class CreateTaskHandler(_Handler):
    async def handle(self, cmd: CreateTask) -> Any:
        return await container_for(self._services).agent_runtime.create_task(
            session_id=cmd.session_id,
            title=cmd.title,
            description=cmd.description,
            run_id=cmd.run_id,
            workflow_id=cmd.workflow_id,
            priority=cmd.priority,
            max_attempts=cmd.max_attempts,
            timeout_seconds=cmd.timeout_seconds,
            input_payload=cmd.input_payload,
            metadata=cmd.metadata,
        )


class TransitionTaskHandler(_Handler):
    async def handle(self, cmd: TransitionTask) -> Any:
        return await container_for(self._services).agent_runtime.transition_task(
            task_id=cmd.task_id, target_state=cmd.target_state, expected_version=cmd.expected_version
        )


class CompleteTaskHandler(_Handler):
    async def handle(self, cmd: CompleteTask) -> Any:
        return await container_for(self._services).agent_runtime.complete_task(
            task_id=cmd.task_id, output_payload=cmd.output_payload, expected_version=cmd.expected_version
        )


class FailTaskHandler(_Handler):
    async def handle(self, cmd: FailTask) -> Any:
        return await container_for(self._services).agent_runtime.fail_task(
            task_id=cmd.task_id, error=cmd.error, expected_version=cmd.expected_version
        )


class RetryTaskHandler(_Handler):
    async def handle(self, cmd: RetryTask) -> Any:
        return await container_for(self._services).agent_runtime.retry_task(task_id=cmd.task_id, expected_version=cmd.expected_version)


class GetTaskHandler(_Handler):
    async def handle(self, q: GetTask) -> Any:
        return await container_for(self._services).agent_runtime.get_task(q.task_id)


class ListTasksHandler(_Handler):
    async def handle(self, q: ListTasks) -> Any:
        return await container_for(self._services).agent_runtime.list_tasks(q.session_id, q.run_id, q.workflow_id, q.state)


# -- workflows -------------------------------------------------------------


class CreateWorkflowHandler(_Handler):
    async def handle(self, cmd: CreateWorkflow) -> Any:
        return await container_for(self._services).agent_runtime.create_workflow(
            session_id=cmd.session_id, name=cmd.name, nodes=cmd.nodes, edges=cmd.edges, metadata=cmd.metadata
        )


class TransitionWorkflowHandler(_Handler):
    async def handle(self, cmd: TransitionWorkflow) -> Any:
        return await container_for(self._services).agent_runtime.transition_workflow(
            workflow_id=cmd.workflow_id, target_state=cmd.target_state, expected_version=cmd.expected_version
        )


class ScheduleWorkflowHandler(_Handler):
    async def handle(self, cmd: ScheduleWorkflow) -> Any:
        return await container_for(self._services).agent_runtime.schedule_workflow(
            workflow_id=cmd.workflow_id, run_id=cmd.run_id, expected_version=cmd.expected_version
        )


class GetWorkflowHandler(_Handler):
    async def handle(self, q: GetWorkflow) -> Any:
        return await container_for(self._services).agent_runtime.get_workflow(q.workflow_id)


class ListWorkflowsHandler(_Handler):
    async def handle(self, q: ListWorkflows) -> Any:
        return await container_for(self._services).agent_runtime.list_workflows(q.session_id)


# -- steps -----------------------------------------------------------------


class TransitionStepHandler(_Handler):
    async def handle(self, cmd: TransitionStep) -> Any:
        return await container_for(self._services).agent_runtime.transition_step(
            step_id=cmd.step_id, target_state=cmd.target_state, expected_version=cmd.expected_version
        )


class GetStepHandler(_Handler):
    async def handle(self, q: GetStep) -> Any:
        return await container_for(self._services).agent_runtime.get_step(q.step_id)


class ListStepsHandler(_Handler):
    async def handle(self, q: ListSteps) -> Any:
        return await container_for(self._services).agent_runtime.list_steps(q.workflow_id, q.run_id)


# -- checkpoints -----------------------------------------------------------


class CreateCheckpointHandler(_Handler):
    async def handle(self, cmd: CreateCheckpoint) -> Any:
        return await container_for(self._services).agent_runtime.create_checkpoint(
            run_id=cmd.run_id, state_snapshot=cmd.state_snapshot, task_id=cmd.task_id, workflow_id=cmd.workflow_id, step_id=cmd.step_id, seq=cmd.seq
        )


class GetCheckpointHandler(_Handler):
    async def handle(self, q: GetCheckpoint) -> Any:
        return await container_for(self._services).agent_runtime.get_checkpoint(q.checkpoint_id)


class ListCheckpointsHandler(_Handler):
    async def handle(self, q: ListCheckpoints) -> Any:
        return await container_for(self._services).agent_runtime.list_checkpoints(q.run_id, q.task_id)


# -- approvals -------------------------------------------------------------


class RequestApprovalHandler(_Handler):
    async def handle(self, cmd: RequestApproval) -> Any:
        return await container_for(self._services).agent_runtime.request_approval(
            task_id=cmd.task_id, requested_by=cmd.requested_by, payload=cmd.payload, run_id=cmd.run_id, expires_in_seconds=cmd.expires_in_seconds
        )


class ResolveApprovalHandler(_Handler):
    async def handle(self, cmd: ResolveApproval) -> Any:
        return await container_for(self._services).agent_runtime.resolve_approval(
            approval_id=cmd.approval_id, target_state=cmd.target_state, resolution=cmd.resolution
        )


class GetApprovalHandler(_Handler):
    async def handle(self, q: GetApproval) -> Any:
        return await container_for(self._services).agent_runtime.get_approval(q.approval_id)


class ListApprovalsHandler(_Handler):
    async def handle(self, q: ListApprovals) -> Any:
        return await container_for(self._services).agent_runtime.list_approvals(q.task_id, q.state)


# -- delegations -----------------------------------------------------------


class DelegateRunHandler(_Handler):
    async def handle(self, cmd: DelegateRun) -> Any:
        return await container_for(self._services).agent_runtime.delegate_run(
            parent_run_id=cmd.parent_run_id, child_run_id=cmd.child_run_id, metadata=cmd.metadata
        )


class TransitionDelegationHandler(_Handler):
    async def handle(self, cmd: TransitionDelegation) -> Any:
        return await container_for(self._services).agent_runtime.transition_delegation(
            delegation_id=cmd.delegation_id, target_status=cmd.target_status
        )


class GetDelegationHandler(_Handler):
    async def handle(self, q: GetDelegation) -> Any:
        return await container_for(self._services).agent_runtime.get_delegation(q.delegation_id)


class ListDelegationsHandler(_Handler):
    async def handle(self, q: ListDelegations) -> Any:
        return await container_for(self._services).agent_runtime.list_delegations(q.parent_run_id, q.child_run_id)


# -- job adapters ----------------------------------------------------------


class AgentRunExecuteJobHandler(_Handler):
    job_type = "agent_runtime.run.execute"

    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        run_id = str(payload.get("run_id", ""))
        target_state = str(payload.get("target_state", "RUNNING"))
        # Simple pass-through: transition run
        view = await container_for(self._services).agent_runtime.transition_run(run_id=run_id, target_state=target_state)
        return {"run_id": view.run_id, "state": view.state, "status": "SUCCEEDED"}


class AgentTaskExecuteJobHandler(_Handler):
    job_type = "agent_runtime.task.execute"

    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        task_id = str(payload.get("task_id", ""))
        action = str(payload.get("action", "complete"))
        if action == "complete":
            output = payload.get("output_payload") or {}
            if not isinstance(output, dict):
                output = {"result": output}
            view = await container_for(self._services).agent_runtime.complete_task(task_id=task_id, output_payload=output)
            return {"task_id": view.task_id, "state": view.state, "status": "SUCCEEDED"}
        elif action == "fail":
            error = str(payload.get("error", "task failed via job"))
            view = await container_for(self._services).agent_runtime.fail_task(task_id=task_id, error=error)
            return {"task_id": view.task_id, "state": view.state, "status": "FAILED", "error": error}
        else:
            # generic transition
            target = str(payload.get("target_state", "RUNNING"))
            view = await container_for(self._services).agent_runtime.transition_task(task_id=task_id, target_state=target)
            return {"task_id": view.task_id, "state": view.state, "status": "SUCCEEDED"}


class AgentWorkflowStepExecuteJobHandler(_Handler):
    job_type = "agent_runtime.workflow.step.execute"

    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        step_id = str(payload.get("step_id", ""))
        target_state = str(payload.get("target_state", "COMPLETED"))
        view = await container_for(self._services).agent_runtime.transition_step(step_id=step_id, target_state=target_state)
        return {"step_id": view.step_id, "state": view.state, "status": "SUCCEEDED"}
