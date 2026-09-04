"""HTTP surface of Automation (mounted under ``/api/v4``).

Routes stay thin per plan section 12: validate DTO, dispatch through
Command/Query buses, map to response payload.  Mutating routes are
policy-gated; tool execution additionally passes the domain Policy Engine
via ``ToolExecutor`` (plan section 18: shell/filesystem/browser must be
gated even when the HTTP layer already authorized).
"""

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
    SecretStore,
)

from ..application import queries as app_queries
from ..application.commands import (
    DeregisterTool,
    ExecuteTool,
    RegisterBuiltinTools,
    RegisterTool,
    UpdateTool,
)
from ..application.runtime import AutomationServices, bind_services
from ..infrastructure.repository import sql_scope_factory

MODULE_ID = "automation"
MODULE_VERSION = "1.0.0"
AUTOMATION_PREFIX = "/automation"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "automation.read"
WRITE_ACTION = "automation.write"
EXECUTE_ACTION = "automation.execute"
RESOURCE_TYPE = "automation"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class RegisterToolIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\.\-]+$")
    description: str = Field(min_length=1, max_length=2000)
    version: str = Field(default="1.0.0", max_length=50)
    risk_level: str = Field(default="read_only", max_length=50)
    capability: str = Field(default="general", max_length=100)
    runtime_type: str = Field(default="in_process", max_length=50)
    side_effect_class: str = Field(default="none", max_length=50)
    is_idempotent: bool = True
    is_destructive: bool = False
    is_reversible: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    required_permissions: list[str] = Field(default_factory=list)
    sandbox_requirement: str = Field(default="none", max_length=50)
    artifact_outputs: list[str] = Field(default_factory=list)
    retry_eligible: bool = True
    redaction_policy: str = Field(default="secrets_only", max_length=50)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class UpdateToolIn(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    version: str | None = Field(default=None, max_length=50)
    risk_level: str | None = Field(default=None, max_length=50)
    capability: str | None = Field(default=None, max_length=100)
    runtime_type: str | None = Field(default=None, max_length=50)
    enabled: bool | None = None
    expected_version: int | None = Field(default=None, ge=0)


class ExecuteToolIn(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    workspace_root: str = Field(default="/tmp", max_length=500)
    actor_id: str | None = Field(default=None, max_length=100)
    correlation_id: str | None = Field(default=None, max_length=36)
    causation_id: str | None = Field(default=None, max_length=36)
    trace_id: str | None = Field(default=None, max_length=64)
    user_approved: bool = False
    invocation_id: str | None = Field(default=None, max_length=80)


# --------------------------------------------------------------------------- #
# Policy + ambient services scope
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


def require_automation_policy(
    action: str, resource_type: str = RESOURCE_TYPE
) -> Callable[[Request], Awaitable[PolicyDecision]]:
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


def services_from_state(request: Request) -> AutomationServices:
    database = getattr(request.app.state, "database", None)
    if database is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="automation requires a configured database")
    from windagent.platform.security import EnvironmentSecretStore

    # Reuse policy_engine from app state for executor wiring (fail-closed semantics)
    policy_engine = getattr(request.app.state, "policy_engine", None)
    return AutomationServices(
        scope_factory=sql_scope_factory(database),
        secrets=cast(SecretStore, EnvironmentSecretStore()),
        policy_engine=policy_engine,
        telemetry=getattr(request.app.state, "telemetry", None),
    )


async def services_scope(request: Request) -> AsyncIterator[None]:
    with bind_services(services_from_state(request)):
        yield


SERVICES_DEP = Depends(services_scope)
READ_POLICY_DEP = Depends(require_automation_policy(READ_ACTION))
WRITE_POLICY_DEP = Depends(require_automation_policy(WRITE_ACTION))
EXECUTE_POLICY_DEP = Depends(require_automation_policy(EXECUTE_ACTION))


def _buses(request: Request) -> tuple[Any, Any]:
    return request.app.state.command_bus, request.app.state.query_bus


def create_automation_router() -> APIRouter:
    router = APIRouter(prefix=AUTOMATION_PREFIX, tags=["automation"])

    @router.post("/tools", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def register_tool(payload: RegisterToolIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            RegisterTool(
                name=payload.name,
                description=payload.description,
                version=payload.version,
                risk_level=payload.risk_level,
                capability=payload.capability,
                runtime_type=payload.runtime_type,
                side_effect_class=payload.side_effect_class,
                is_idempotent=payload.is_idempotent,
                is_destructive=payload.is_destructive,
                is_reversible=payload.is_reversible,
                timeout_seconds=payload.timeout_seconds,
                required_permissions=tuple(payload.required_permissions),
                sandbox_requirement=payload.sandbox_requirement,
                artifact_outputs=tuple(payload.artifact_outputs),
                retry_eligible=payload.retry_eligible,
                redaction_policy=payload.redaction_policy,
                parameters_schema=payload.parameters_schema,
                output_schema=payload.output_schema,
                enabled=payload.enabled,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.post("/tools/builtins/register", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def register_builtins(request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        views = await command_bus.dispatch(RegisterBuiltinTools())
        return {"tools": [v.to_payload() for v in views], "count": len(views)}

    @router.get("/tools", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_tools(
        request: Request,
        capability: str | None = QueryParam(default=None),
        runtime_type: str | None = QueryParam(default=None),
        enabled_only: bool = QueryParam(default=False),
    ) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(
            app_queries.ListTools(capability=capability, runtime_type=runtime_type, enabled_only=enabled_only)
        )
        return {"tools": [v.to_payload() for v in views], "count": len(views)}

    @router.get("/tools/{tool_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_tool(tool_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetTool(tool_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/tools/by-name/{name}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_tool_by_name(name: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetToolByName(name))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.patch("/tools/{tool_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_tool(tool_id: str, payload: UpdateToolIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            UpdateTool(
                tool_id=tool_id,
                description=payload.description,
                version=payload.version,
                risk_level=payload.risk_level,
                capability=payload.capability,
                runtime_type=payload.runtime_type,
                enabled=payload.enabled,
                expected_version=payload.expected_version,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.delete("/tools/{tool_id}", status_code=204, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def deregister_tool(tool_id: str, request: Request) -> None:
        command_bus, _ = _buses(request)
        await command_bus.dispatch(DeregisterTool(tool_id=tool_id))

    @router.post("/tools/{tool_name}/execute", dependencies=[SERVICES_DEP, EXECUTE_POLICY_DEP])
    async def execute_tool(tool_name: str, payload: ExecuteToolIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        view = await command_bus.dispatch(
            ExecuteTool(
                tool_name=tool_name,
                params=payload.params,
                workspace_root=payload.workspace_root,
                actor_id=payload.actor_id,
                correlation_id=payload.correlation_id,
                causation_id=payload.causation_id,
                trace_id=payload.trace_id,
                user_approved=payload.user_approved,
                invocation_id=payload.invocation_id,
            )
        )
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/runs", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_runs(
        request: Request,
        tool_name: str | None = QueryParam(default=None),
        status: str | None = QueryParam(default=None),
        limit: int = QueryParam(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        _, query_bus = _buses(request)
        views = await query_bus.ask(app_queries.ListToolRuns(tool_name=tool_name, status=status, limit=limit))
        return {"runs": [v.to_payload() for v in views], "count": len(views)}

    @router.get("/runs/{run_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetToolRun(run_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/runs/by-invocation/{invocation_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_run_by_invocation(invocation_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        view = await query_bus.ask(app_queries.GetToolRunByInvocation(invocation_id))
        return view.to_payload()  # type: ignore[no-any-return]

    @router.get("/runtimes", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_runtimes(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        runtimes = await query_bus.ask(app_queries.ListRuntimeTypes())
        return {"runtimes": list(runtimes), "count": len(runtimes)}

    @router.get("/capabilities", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_capabilities(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        caps = await query_bus.ask(app_queries.GetCapabilities())
        return {"capabilities": list(caps), "count": len(caps)}

    return router
