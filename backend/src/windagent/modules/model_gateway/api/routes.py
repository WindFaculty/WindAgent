"""HTTP surface of the model gateway (mounted under ``/api/v4``).

Routes stay thin per plan section 12: validate the DTO, dispatch through the
Command/Query buses, map to the response payload.  Every mutating route is
policy-gated, and every dispatch runs inside the module's ambient services
scope so handlers stay manifest-declarative.
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
)

from ..application import queries as app_queries
from ..application.commands import (
    AddProviderEndpoint,
    DeleteProvider,
    DeleteRoutingRule,
    InvokeModel,
    RegisterProvider,
    RemoveProviderCredential,
    RotateProviderCredential,
    UpdateProvider,
    UpsertRoutingRule,
)
from ..application.coordinator import ModelCompletionResult
from ..application.gateway import InvocationRequest, RouteDecision
from ..application.models import (
    CredentialView,
    EndpointView,
    ModelView,
    ProviderView,
    ReceiptView,
    RuleView,
    lock_view,
)
from ..application.queries import GetProvider
from ..application.runtime import ModelGatewayServices, bind_services
from ..domain.route_lock import RouteLockRecord
from ..domain.rules import RuleMatchContext
from ..infrastructure.repository import sql_scope_factory
from ..providers.contracts import ProviderMessage

MODULE_ID = "model_gateway"
MODULE_VERSION = "1.0.0"
MODEL_GATEWAY_PREFIX = "/model-gateway"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "model_gateway.read"
WRITE_ACTION = "model_gateway.write"
DELETE_ACTION = "model_gateway.delete"
INVOKE_ACTION = "model_gateway.invoke"
RESOURCE_TYPE = "model_gateway"


# --------------------------------------------------------------------------- #
# Request DTOs (pydantic validates; the bus dispatches)
# --------------------------------------------------------------------------- #


class CredentialIn(BaseModel):
    """Write-only credential payload: never echoed back."""

    secret: str = Field(min_length=1)
    label: str = ""


class RegisterProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1)
    protocol_mode: str = Field(default="openai", max_length=50)
    display_name: str | None = Field(default=None, max_length=200)
    vendor_type: str = Field(default="cloud", max_length=50)
    credential: CredentialIn | None = None
    supports_model_discovery: bool = True


class UpdateProviderIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, min_length=1)
    protocol_mode: str | None = Field(default=None, max_length=50)
    enabled: bool | None = None


class AddEndpointIn(BaseModel):
    base_url: str = Field(min_length=1)
    protocol_mode: str | None = Field(default=None, max_length=50)
    priority: int = Field(default=50, ge=0, le=1000)
    weight: int = Field(default=100, ge=0, le=1000)


class RoutingRuleIn(BaseModel):
    rule_id: str = Field(min_length=1, max_length=200)
    canonical_model_id: str = Field(min_length=1, max_length=300)
    fallback_model_id: str | None = Field(default=None, max_length=300)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    priority: int | None = Field(default=None, ge=0, le=100_000)
    expected_version: int | None = Field(default=None, ge=0)
    task_labels: list[str] = Field(default_factory=list)
    agent_types: list[str] = Field(default_factory=list)
    workflow_types: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    min_context_tokens: int = Field(default=0, ge=0)
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: list[str] = Field(default_factory=list)
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = Field(default=None, max_length=300)


class MessageIn(BaseModel):
    role: str = "user"
    content: str = ""


class InvokeIn(BaseModel):
    task_id: str = Field(min_length=1, max_length=200)
    scope_id: str = Field(min_length=1, max_length=200)
    scope_type: str = Field(default="task", max_length=30)
    role: str | None = Field(default=None, max_length=100)
    prompt: str = ""
    messages: list[MessageIn] = Field(default_factory=list)
    system_instruction: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    task_labels: list[str] = Field(default_factory=list)
    agent_type: str = ""
    workflow_type: str = ""
    available_capabilities: list[str] = Field(default_factory=list)
    estimated_context_tokens: int = Field(default=0, ge=0)
    has_tools: bool = False
    has_vision: bool = False
    cost_class: str = ""
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = None


class SimulateIn(BaseModel):
    scope_id: str = Field(default="simulation", max_length=200)
    scope_type: str = Field(default="session", max_length=30)
    task_labels: list[str] = Field(default_factory=list)
    agent_type: str = ""
    workflow_type: str = ""
    available_capabilities: list[str] = Field(default_factory=list)
    estimated_context_tokens: int = Field(default=0, ge=0)
    has_tools: bool = False
    has_vision: bool = False
    cost_class: str = ""
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = None


# --------------------------------------------------------------------------- #
# Dependencies: policy + ambient services scope
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


def require_model_gateway_policy(
    action: str, resource_type: str = RESOURCE_TYPE
) -> Callable[[Request], Awaitable[PolicyDecision]]:
    """Policy-gate one route through the composition-root policy engine.

    Mirrors the app-level dependency: ALLOW passes (audited), DENY and
    REQUIRE_APPROVAL fail closed with 403, and an unconfigured engine means
    explicitly unsecured development mode.
    """
    normalized_action = action

    async def dependency(request: Request) -> PolicyDecision:
        engine = getattr(request.app.state, "policy_engine", None)
        if engine is None:
            return PolicyDecision(
                effect=PolicyEffect.ALLOW,
                reason="no policy engine is configured",
                policy_id=POLICY_UNCONFIGURED_POLICY_ID,
            )
        decision = await cast(PolicyEngine, engine).decide(
            PolicyRequest(
                action=normalized_action,
                resource_type=resource_type,
                actor_id=_principal_actor_id(request),  # type: ignore[arg-type]
            )
        )
        await _audit_decision(request, decision, normalized_action, resource_type)
        if decision.effect is not PolicyEffect.ALLOW:
            from windagent.kernel.errors import DomainError

            raise DomainError(
                decision.reason or "denied by policy",
                code="forbidden",
                context={"policy_id": decision.policy_id},
            )
        return decision

    return dependency


async def _audit_decision(
    request: Request, decision: PolicyDecision, action: str, resource_type: str
) -> None:
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


def services_from_state(request: Request) -> ModelGatewayServices:
    """Compose the module services from the composition root's app.state."""
    database = getattr(request.app.state, "database", None)
    if database is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="model gateway requires a configured database",
        )
    from windagent.platform.security import EnvironmentSecretStore

    from ..infrastructure.secret_store import (
        ChainedSecretStore,
        EncryptedSecretStore,
    )

    secrets = ChainedSecretStore(
        primary=EncryptedSecretStore(database.session_factory),
        fallbacks=(EnvironmentSecretStore(),),
    )
    return ModelGatewayServices(
        scope_factory=sql_scope_factory(database),
        secrets=secrets,
        telemetry=getattr(request.app.state, "telemetry", None),
    )


async def services_scope(request: Request) -> AsyncIterator[None]:
    """Bind the ambient services for the duration of one dispatch."""
    with bind_services(services_from_state(request)):
        yield


SERVICES_DEP = Depends(services_scope)
READ_POLICY_DEP = Depends(require_model_gateway_policy(READ_ACTION))
WRITE_POLICY_DEP = Depends(require_model_gateway_policy(WRITE_ACTION))
DELETE_POLICY_DEP = Depends(require_model_gateway_policy(DELETE_ACTION))
INVOKE_POLICY_DEP = Depends(require_model_gateway_policy(INVOKE_ACTION))


def _buses(request: Request) -> tuple[Any, Any]:
    """The composition root's command and query buses."""
    return request.app.state.command_bus, request.app.state.query_bus


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #


def create_model_gateway_router() -> APIRouter:
    """The module-owned router; relative paths mount under ``/api/v4``."""
    router = APIRouter(prefix=MODEL_GATEWAY_PREFIX, tags=["model-gateway"])

    # -- providers ---------------------------------------------------------
    @router.get("/providers", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_providers(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        providers: tuple[ProviderView, ...] = await query_bus.ask(app_queries.ListProviders())
        return {"providers": [provider.to_payload() for provider in providers]}

    @router.post("/providers", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def register_provider(payload: RegisterProviderIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        provider_view: ProviderView = await command_bus.dispatch(
            RegisterProvider(
                name=payload.name,
                base_url=payload.base_url,
                protocol_mode=payload.protocol_mode,
                display_name=payload.display_name,
                vendor_type=payload.vendor_type,
                credential_secret=payload.credential.secret if payload.credential else None,
                credential_label=payload.credential.label if payload.credential else "",
                supports_model_discovery=payload.supports_model_discovery,
            )
        )
        return provider_view.to_payload()

    @router.get("/providers/{provider_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_provider(provider_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        provider: ProviderView = await query_bus.ask(GetProvider(provider_id))
        return provider.to_payload()

    @router.patch("/providers/{provider_id}", dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def update_provider(
        provider_id: str, payload: UpdateProviderIn, request: Request
    ) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        provider: ProviderView = await command_bus.dispatch(
            UpdateProvider(
                provider_id=provider_id,
                display_name=payload.display_name,
                base_url=payload.base_url,
                protocol_mode=payload.protocol_mode,
                enabled=payload.enabled,
            )
        )
        return provider.to_payload()

    @router.delete("/providers/{provider_id}", dependencies=[SERVICES_DEP, DELETE_POLICY_DEP])
    async def delete_provider(
        provider_id: str,
        request: Request,
        allow_disabling_rules: bool = QueryParam(default=False),
    ) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        result: dict[str, object] = await command_bus.dispatch(
            DeleteProvider(provider_id=provider_id, allow_disabling_rules=allow_disabling_rules)
        )
        return result

    @router.put(
        "/providers/{provider_id}/credential",
        status_code=201,
        dependencies=[SERVICES_DEP, WRITE_POLICY_DEP],
    )
    async def rotate_credential(
        provider_id: str, payload: CredentialIn, request: Request
    ) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        credential: CredentialView = await command_bus.dispatch(
            RotateProviderCredential(provider_id=provider_id, secret=payload.secret, label=payload.label)
        )
        return credential.to_payload()

    @router.delete(
        "/providers/{provider_id}/credential", dependencies=[SERVICES_DEP, DELETE_POLICY_DEP]
    )
    async def remove_credential(provider_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        removed: bool = await command_bus.dispatch(RemoveProviderCredential(provider_id=provider_id))
        return {"provider_id": provider_id, "removed": removed}

    @router.get(
        "/providers/{provider_id}/endpoints", dependencies=[SERVICES_DEP, READ_POLICY_DEP]
    )
    async def list_endpoints(provider_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        endpoints: tuple[EndpointView, ...] = await query_bus.ask(app_queries.ListEndpoints(provider_id))
        return {"endpoints": [endpoint.to_payload() for endpoint in endpoints]}

    @router.post(
        "/providers/{provider_id}/endpoints",
        status_code=201,
        dependencies=[SERVICES_DEP, WRITE_POLICY_DEP],
    )
    async def add_endpoint(
        provider_id: str, payload: AddEndpointIn, request: Request
    ) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        endpoint_view: EndpointView = await command_bus.dispatch(
            AddProviderEndpoint(
                provider_id=provider_id,
                base_url=payload.base_url,
                protocol_mode=payload.protocol_mode,
                priority=payload.priority,
                weight=payload.weight,
            )
        )
        return endpoint_view.to_payload()

    # -- canonical models ----------------------------------------------------
    @router.get("/models", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_models(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        models: tuple[ModelView, ...] = await query_bus.ask(app_queries.ListCanonicalModels())
        return {"models": [model.to_payload() for model in models]}

    # -- routing rules ---------------------------------------------------------
    @router.get("/rules", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_rules(request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        rules: tuple[RuleView, ...] = await query_bus.ask(app_queries.ListRoutingRules())
        return {"rules": [rule.to_payload() for rule in rules]}

    @router.post("/rules", status_code=201, dependencies=[SERVICES_DEP, WRITE_POLICY_DEP])
    async def upsert_rule(payload: RoutingRuleIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        rule: RuleView = await command_bus.dispatch(
            UpsertRoutingRule(
                rule_id=payload.rule_id,
                canonical_model_id=payload.canonical_model_id,
                fallback_model_id=payload.fallback_model_id,
                description=payload.description,
                enabled=payload.enabled,
                priority=payload.priority,
                expected_version=payload.expected_version,
                task_labels=tuple(payload.task_labels),
                agent_types=tuple(payload.agent_types),
                workflow_types=tuple(payload.workflow_types),
                required_capabilities=tuple(payload.required_capabilities),
                min_context_tokens=payload.min_context_tokens,
                requires_tools=payload.requires_tools,
                requires_vision=payload.requires_vision,
                cost_classes=tuple(payload.cost_classes),
                requires_local=payload.requires_local,
                requires_private=payload.requires_private,
                user_preference_model=payload.user_preference_model,
            )
        )
        return rule.to_payload()

    @router.delete("/rules/{rule_id}", dependencies=[SERVICES_DEP, DELETE_POLICY_DEP])
    async def delete_rule(rule_id: str, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        deleted: bool = await command_bus.dispatch(DeleteRoutingRule(rule_id=rule_id))
        return {"rule_id": rule_id, "deleted": deleted}

    # -- routing ---------------------------------------------------------------
    @router.post("/route/simulate", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def simulate(payload: SimulateIn, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        context = RuleMatchContext(
            scope_id=payload.scope_id,
            scope_type=payload.scope_type,
            task_labels=tuple(payload.task_labels),
            agent_type=payload.agent_type,
            workflow_type=payload.workflow_type,
            available_capabilities=tuple(payload.available_capabilities),
            estimated_context_tokens=payload.estimated_context_tokens,
            has_tools=payload.has_tools,
            has_vision=payload.has_vision,
            cost_class=payload.cost_class,
            requires_local=payload.requires_local,
            requires_private=payload.requires_private,
            user_preference_model=payload.user_preference_model,
        )
        decision: RouteDecision = await query_bus.ask(app_queries.SimulateRoute(context))
        return decision.to_payload()

    @router.get("/route/locks/{lock_id}", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_lock(lock_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _buses(request)
        lock: RouteLockRecord = await query_bus.ask(app_queries.GetRouteLock(lock_id))
        return lock_view(lock)

    @router.get("/route/locks", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def get_active_lock(
        request: Request,
        scope_type: str = QueryParam(default="task", max_length=30),
        scope_id: str = QueryParam(default="", max_length=200),
    ) -> dict[str, Any]:
        _, query_bus = _buses(request)
        lock: RouteLockRecord | None = await query_bus.ask(
            app_queries.GetActiveRouteLock(scope_type, scope_id)
        )
        if lock is None:
            from windagent.kernel.errors import DomainError

            raise DomainError(
                "no active route lock for scope",
                code="not_found",
                context={"scope_type": scope_type, "scope_id": scope_id},
            )
        return lock_view(lock)

    # -- invocation --------------------------------------------------------------
    @router.post("/invocations", dependencies=[SERVICES_DEP, INVOKE_POLICY_DEP])
    async def invoke(payload: InvokeIn, request: Request) -> dict[str, Any]:
        command_bus, _ = _buses(request)
        messages = tuple(
            ProviderMessage(role=message.role, content=message.content)
            for message in payload.messages
        )
        invocation = InvocationRequest(
            task_id=payload.task_id,
            scope_id=payload.scope_id,
            scope_type=payload.scope_type,
            role=payload.role,
            prompt=payload.prompt,
            messages=messages,
            system_instruction=payload.system_instruction,
            temperature=payload.temperature,
            max_output_tokens=payload.max_output_tokens,
            task_labels=tuple(payload.task_labels),
            agent_type=payload.agent_type,
            workflow_type=payload.workflow_type,
            available_capabilities=tuple(payload.available_capabilities),
            estimated_context_tokens=payload.estimated_context_tokens,
            has_tools=payload.has_tools,
            has_vision=payload.has_vision,
            cost_class=payload.cost_class,
            requires_local=payload.requires_local,
            requires_private=payload.requires_private,
            user_preference_model=payload.user_preference_model,
        )
        result: ModelCompletionResult = await command_bus.dispatch(InvokeModel(request=invocation))
        return result.to_payload()

    # -- receipts ------------------------------------------------------------------
    @router.get("/receipts", dependencies=[SERVICES_DEP, READ_POLICY_DEP])
    async def list_receipts(
        request: Request,
        task_id: str | None = QueryParam(default=None, max_length=200),
        limit: int = QueryParam(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        _, query_bus = _buses(request)
        receipts: tuple[ReceiptView, ...] = await query_bus.ask(
            app_queries.ListReceipts(task_id=task_id, limit=limit)
        )
        return {"receipts": [receipt.to_payload() for receipt in receipts]}

    return router
