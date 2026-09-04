"""HTTP surface of Agent Runtime (mounted under ``/api/v4``)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field

from windagent.kernel.time import utc_now
from windagent.platform.observability import current_operation_context
from windagent.platform.security import (
    AuditEvent,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
)

from ..application import queries as app_queries
from ..application.commands import (
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
from ..application.runtime import AgentRuntimeServices, bind_services
from ..infrastructure.repository import sql_scope_factory

MODULE_ID = "agent_runtime"
MODULE_VERSION = "1.0.0"
PREFIX = "/agent-runtime"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "agent_runtime.read"
WRITE_ACTION = "agent_runtime.write"
DELETE_ACTION = "agent_runtime.delete"
RESOURCE_TYPE = "agent_runtime"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class CreateSessionIn(BaseModel):
    actor_id: str = Field(default="system", min_length=1, max_length=100)
    title: str = Field(default="Untitled session", min_length=1, max_length=300)
    budget_limits: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionSessionIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=32)
    expected_version: int | None = Field(default=None, ge=0)


class CreateRunIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    parent_run_id: str | None = Field(default=None, max_length=36)
    budget_scope: str = Field(default="conversation", max_length=32)
    budget_limits: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionRunIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=32)
    expected_version: int | None = Field(default=None, ge=0)
    exhaustion_reason: str | None = Field(default=None, max_length=200)


class RecordBudgetUsageIn(BaseModel):
    usage_patch: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=0)


class CreateTaskIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=400)
    description: str = Field(default="", max_length=5000)
    run_id: str | None = Field(default=None, max_length=36)
    workflow_id: str | None = Field(default=None, max_length=36)
    priority: int = Field(default=0)
    max_attempts: int = Field(default=3, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionTaskIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=32)
    expected_version: int | None = Field(default=None, ge=0)


class CompleteTaskIn(BaseModel):
    output_payload: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=0)


class FailTaskIn(BaseModel):
    error: str = Field(default="", max_length=5000)
    expected_version: int | None = Field(default=None, ge=0)


class RetryTaskIn(BaseModel):
    expected_version: int | None = Field(default=None, ge=0)


class CreateWorkflowIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=300)
    nodes: dict[str, Any] = Field(default_factory=dict)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionWorkflowIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=32)
    expected_version: int | None = Field(default=None, ge=0)


class ScheduleWorkflowIn(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    expected_version: int | None = Field(default=None, ge=0)


class TransitionStepIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=32)
    expected_version: int | None = Field(default=None, ge=0)


class CreateCheckpointIn(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = Field(default=None, max_length=36)
    workflow_id: str | None = Field(default=None, max_length=36)
    step_id: str | None = Field(default=None, max_length=36)
    seq: int | None = Field(default=None, ge=0)


class RequestApprovalIn(BaseModel):
    task_id: str = Field(min_length=1, max_length=36)
    requested_by: str = Field(default="system", min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = Field(default=None, max_length=36)
    expires_in_seconds: float | None = Field(default=None, gt=0)


class ResolveApprovalIn(BaseModel):
    target_state: str = Field(min_length=1, max_length=32)
    resolution: dict[str, Any] = Field(default_factory=dict)


class DelegateRunIn(BaseModel):
    parent_run_id: str = Field(min_length=1, max_length=36)
    child_run_id: str = Field(min_length=1, max_length=36)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionDelegationIn(BaseModel):
    target_status: str = Field(min_length=1, max_length=32)


# --------------------------------------------------------------------------- #
# Policy + ambient scope
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


def require_policy(action: str, resource_type: str = RESOURCE_TYPE) -> Callable[[Request], Awaitable[PolicyDecision]]:
    normalized_action = action

    async def dependency(request: Request) -> PolicyDecision:
        engine = getattr(request.app.state, "policy_engine", None)
        if engine is None:
            return PolicyDecision(effect=PolicyEffect.ALLOW, reason="no policy engine is configured", policy_id=POLICY_UNCONFIGURED_POLICY_ID)
        decision = await cast(PolicyEngine, engine).decide(
            PolicyRequest(action=normalized_action, resource_type=resource_type, actor_id=_principal_actor_id(request))  # type: ignore[arg-type]
        )
        await _audit_decision(request, decision, normalized_action, resource_type)
        if decision.effect is not PolicyEffect.ALLOW:
            from windagent.kernel.errors import DomainError

            raise DomainError(decision.reason or "denied by policy", code="forbidden", context={"policy_id": decision.policy_id})
        return decision

    return dependency


async def _audit_decision(request: Request, decision: PolicyDecision, action: str, resource_type: str) -> None:
    sink = getattr(request.app.state, "audit_sink", None)
    if sink is None:
        return
    operation = current_operation_context()
    await sink.record(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            outcome=decision.effect.value,
            actor_id=_principal_actor_id(request),  # type: ignore[arg-type]
            correlation_id=operation.correlation_id if operation else None,
            causation_id=operation.causation_id if operation else None,
            trace_id=operation.trace_id if operation else None,
            reason=decision.reason,
            details={"policy_id": decision.policy_id} if decision.policy_id else {},
            occurred_at=utc_now(),
        )
    )


def services_from_state(request: Request) -> AgentRuntimeServices:
    database = getattr(request.app.state, "database", None)
    if database is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="agent runtime requires a configured database")

    return AgentRuntimeServices(scope_factory=sql_scope_factory(database), telemetry=getattr(request.app.state, "telemetry", None))


async def services_scope(request: Request) -> AsyncIterator[None]:
    with bind_services(services_from_state(request)):
        yield


SERVICES_DEP = Depends(services_scope)
READ_POLICY_DEP = Depends(require_policy(READ_ACTION))
WRITE_POLICY_DEP = Depends(require_policy(WRITE_ACTION))


def _buses(request: Request) -> tuple[Any, Any]:
    return request.app.state.command_bus, request.app.state.query_bus


def create_agent_runtime_router() -> APIRouter:
    router = APIRouter(prefix=PREFIX, tags=["agent-runtime"])

    # -- sessions ----------------------------------------------------------
    @router.post("/sessions", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_session(payload: CreateSessionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateSession(actor_id=payload.actor_id, title=payload.title, budget_limits=payload.budget_limits, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/sessions/{session_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_session(session_id: str, payload: TransitionSessionIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionSession(session_id=session_id, target_state=payload.target_state, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/sessions/{session_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_session(session_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetSession(session_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/sessions", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_sessions(request: Request, actor_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListSessions(actor_id=actor_id))
        return {"sessions": [v.to_payload() for v in views]}

    # -- runs --------------------------------------------------------------
    @router.post("/runs", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_run(payload: CreateRunIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateRun(
                session_id=payload.session_id,
                parent_run_id=payload.parent_run_id,
                budget_scope=payload.budget_scope,
                budget_limits=payload.budget_limits,
                max_attempts=payload.max_attempts,
                timeout_seconds=payload.timeout_seconds,
                metadata=payload.metadata,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/runs/{run_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_run(run_id: str, payload: TransitionRunIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionRun(run_id=run_id, target_state=payload.target_state, expected_version=payload.expected_version, exhaustion_reason=payload.exhaustion_reason))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/runs/{run_id}/budget-usage", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def record_budget(run_id: str, payload: RecordBudgetUsageIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(RecordRunBudgetUsage(run_id=run_id, usage_patch=payload.usage_patch, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/runs/{run_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetRun(run_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/runs", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_runs(request: Request, session_id: str | None = QueryParam(default=None), parent_run_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListRuns(session_id=session_id, parent_run_id=parent_run_id))
        return {"runs": [v.to_payload() for v in views]}

    # -- tasks -------------------------------------------------------------
    @router.post("/tasks", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_task(payload: CreateTaskIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateTask(
                session_id=payload.session_id,
                title=payload.title,
                description=payload.description,
                run_id=payload.run_id,
                workflow_id=payload.workflow_id,
                priority=payload.priority,
                max_attempts=payload.max_attempts,
                timeout_seconds=payload.timeout_seconds,
                input_payload=payload.input_payload,
                metadata=payload.metadata,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/tasks/{task_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_task(task_id: str, payload: TransitionTaskIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionTask(task_id=task_id, target_state=payload.target_state, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/tasks/{task_id}/complete", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def complete_task(task_id: str, payload: CompleteTaskIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CompleteTask(task_id=task_id, output_payload=payload.output_payload, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/tasks/{task_id}/fail", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def fail_task(task_id: str, payload: FailTaskIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(FailTask(task_id=task_id, error=payload.error, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/tasks/{task_id}/retry", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def retry_task(task_id: str, payload: RetryTaskIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(RetryTask(task_id=task_id, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/tasks/{task_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_task(task_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetTask(task_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/tasks", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_tasks(
        request: Request,
        session_id: str | None = QueryParam(default=None),
        run_id: str | None = QueryParam(default=None),
        workflow_id: str | None = QueryParam(default=None),
        state: str | None = QueryParam(default=None),
    ) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListTasks(session_id=session_id, run_id=run_id, workflow_id=workflow_id, state=state))
        return {"tasks": [v.to_payload() for v in views]}

    # -- workflows ---------------------------------------------------------
    @router.post("/workflows", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_workflow(payload: CreateWorkflowIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(CreateWorkflow(session_id=payload.session_id, name=payload.name, nodes=payload.nodes, edges=payload.edges, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/workflows/{workflow_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_workflow(workflow_id: str, payload: TransitionWorkflowIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionWorkflow(workflow_id=workflow_id, target_state=payload.target_state, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/workflows/{workflow_id}/schedule", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def schedule_workflow(workflow_id: str, payload: ScheduleWorkflowIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(ScheduleWorkflow(workflow_id=workflow_id, run_id=payload.run_id, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/workflows/{workflow_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_workflow(workflow_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetWorkflow(workflow_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/workflows", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_workflows(request: Request, session_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListWorkflows(session_id=session_id))
        return {"workflows": [v.to_payload() for v in views]}

    # -- steps -------------------------------------------------------------
    @router.post("/steps/{step_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_step(step_id: str, payload: TransitionStepIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionStep(step_id=step_id, target_state=payload.target_state, expected_version=payload.expected_version))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/steps/{step_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_step(step_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetStep(step_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/steps", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_steps(request: Request, workflow_id: str | None = QueryParam(default=None), run_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListSteps(workflow_id=workflow_id, run_id=run_id))
        return {"steps": [v.to_payload() for v in views]}

    # -- checkpoints -------------------------------------------------------
    @router.post("/checkpoints", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def create_checkpoint(payload: CreateCheckpointIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            CreateCheckpoint(run_id=payload.run_id, state_snapshot=payload.state_snapshot, task_id=payload.task_id, workflow_id=payload.workflow_id, step_id=payload.step_id, seq=payload.seq)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/checkpoints/{checkpoint_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_checkpoint(checkpoint_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetCheckpoint(checkpoint_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/checkpoints", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_checkpoints(request: Request, run_id: str | None = QueryParam(default=None), task_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListCheckpoints(run_id=run_id, task_id=task_id))
        return {"checkpoints": [v.to_payload() for v in views]}

    # -- approvals ---------------------------------------------------------
    @router.post("/approvals", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def request_approval(payload: RequestApprovalIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            RequestApproval(task_id=payload.task_id, requested_by=payload.requested_by, payload=payload.payload, run_id=payload.run_id, expires_in_seconds=payload.expires_in_seconds)
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/approvals/{approval_id}/resolve", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def resolve_approval(approval_id: str, payload: ResolveApprovalIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(ResolveApproval(approval_id=approval_id, target_state=payload.target_state, resolution=payload.resolution))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/approvals/{approval_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_approval(approval_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetApproval(approval_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/approvals", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_approvals(request: Request, task_id: str | None = QueryParam(default=None), state: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListApprovals(task_id=task_id, state=state))
        return {"approvals": [v.to_payload() for v in views]}

    # -- delegations -------------------------------------------------------
    @router.post("/delegations", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def delegate_run(payload: DelegateRunIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(DelegateRun(parent_run_id=payload.parent_run_id, child_run_id=payload.child_run_id, metadata=payload.metadata))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/delegations/{delegation_id}/transitions", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def transition_delegation(delegation_id: str, payload: TransitionDelegationIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(TransitionDelegation(delegation_id=delegation_id, target_status=payload.target_status))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/delegations/{delegation_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_delegation(delegation_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetDelegation(delegation_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/delegations", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_delegations(request: Request, parent_run_id: str | None = QueryParam(default=None), child_run_id: str | None = QueryParam(default=None)) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListDelegations(parent_run_id=parent_run_id, child_run_id=child_run_id))
        return {"delegations": [v.to_payload() for v in views]}

    return router
