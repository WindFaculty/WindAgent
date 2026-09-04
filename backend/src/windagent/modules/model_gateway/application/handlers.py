"""Application handlers connecting commands/queries/jobs to the services.

Handlers resolve their collaborators lazily (module manifests are discovered
without constructor arguments) or use explicitly injected services in tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from windagent.kernel.types import JSONValue
from windagent.platform.observability import bind_operation_context, current_operation_context

from ..domain.errors import ModelGatewayValidationError, RouteLockNotFoundError
from ..domain.route_lock import VALID_SCOPE_TYPES
from ..domain.rules import RuleMatchContext
from .commands import (
    AddProviderEndpoint,
    DeleteProvider,
    DeleteRoutingRule,
    InvokeModel,
    RegisterProvider,
    RemoveProviderCredential,
    ReselectModel,
    RotateProviderCredential,
    UpdateProvider,
    UpsertRoutingRule,
)
from .coordinator import ModelCompletionResult
from .gateway import InvocationRequest
from .models import (
    CredentialView,
    EndpointView,
    ModelView,
    ProviderView,
    ReceiptRow,
    ReceiptView,
    RuleView,
)
from .queries import (
    GetActiveRouteLock,
    GetProvider,
    GetRouteLock,
    ListCanonicalModels,
    ListEndpoints,
    ListProviders,
    ListReceipts,
    ListRoutingRules,
    SimulateRoute,
)
from .runtime import ModelGatewayServices, container_for, resolve_services


class _Handler:
    """Base with the lazy services resolution."""

    def __init__(self, services: ModelGatewayServices | None = None) -> None:
        self._services = services


class RegisterProviderHandler(_Handler):
    """Registers a provider atomically."""

    async def handle(self, command: RegisterProvider) -> ProviderView:
        return await container_for(self._services).registry.register_provider(
            name=command.name,
            display_name=command.display_name,
            vendor_type=command.vendor_type,
            base_url=command.base_url,
            protocol_mode=command.protocol_mode,
            credential_secret=command.credential_secret,
            credential_label=command.credential_label,
            supports_model_discovery=command.supports_model_discovery,
        )


class UpdateProviderHandler(_Handler):
    """Updates provider fields."""

    async def handle(self, command: UpdateProvider) -> ProviderView:
        return await container_for(self._services).registry.update_provider(
            command.provider_id,
            display_name=command.display_name,
            base_url=command.base_url,
            protocol_mode=command.protocol_mode,
            enabled=command.enabled,
        )


class DeleteProviderHandler(_Handler):
    """Deletes a provider after the in-use check."""

    async def handle(self, command: DeleteProvider) -> dict[str, object]:
        return await container_for(self._services).registry.delete_provider(
            command.provider_id,
            allow_disabling_rules=command.allow_disabling_rules,
        )


class RotateProviderCredentialHandler(_Handler):
    """Rotates the write-only credential."""

    async def handle(self, command: RotateProviderCredential) -> CredentialView:
        return await container_for(self._services).registry.rotate_credential(
            command.provider_id, secret=command.secret, label=command.label
        )


class RemoveProviderCredentialHandler(_Handler):
    """Removes the stored credential."""

    async def handle(self, command: RemoveProviderCredential) -> bool:
        return await container_for(self._services).registry.remove_credential(
            command.provider_id
        )


class AddProviderEndpointHandler(_Handler):
    """Adds an endpoint to a provider."""

    async def handle(self, command: AddProviderEndpoint) -> EndpointView:
        return await container_for(self._services).registry.add_endpoint(
            command.provider_id,
            base_url=command.base_url,
            protocol_mode=command.protocol_mode,
            priority=command.priority,
            weight=command.weight,
        )


class UpsertRoutingRuleHandler(_Handler):
    """Creates or updates a routing rule."""

    async def handle(self, command: UpsertRoutingRule) -> RuleView:
        return await container_for(self._services).registry.upsert_rule(
            rule_id=command.rule_id,
            canonical_model_id=command.canonical_model_id,
            fallback_model_id=command.fallback_model_id,
            description=command.description,
            enabled=command.enabled,
            priority=command.priority,
            expected_version=command.expected_version,
            task_labels=command.task_labels,
            agent_types=command.agent_types,
            workflow_types=command.workflow_types,
            required_capabilities=command.required_capabilities,
            min_context_tokens=command.min_context_tokens,
            requires_tools=command.requires_tools,
            requires_vision=command.requires_vision,
            cost_classes=command.cost_classes,
            requires_local=command.requires_local,
            requires_private=command.requires_private,
            user_preference_model=command.user_preference_model,
        )


class DeleteRoutingRuleHandler(_Handler):
    """Deletes a routing rule."""

    async def handle(self, command: DeleteRoutingRule) -> bool:
        return await container_for(self._services).registry.delete_rule(command.rule_id)


class InvokeModelHandler(_Handler):
    """Routes and executes one invocation through the single authority."""

    async def handle(self, command: InvokeModel) -> ModelCompletionResult:
        return await container_for(self._services).gateway.invoke(command.request)


class ReselectModelHandler(_Handler):
    """Releases and re-pins a scope's route lock."""

    async def handle(self, command: ReselectModel) -> object:
        context = cast(RuleMatchContext, command.new_context)
        return await container_for(self._services).locks.reselect_model(
            scope_type=command.scope_type,
            scope_id=command.scope_id,
            new_context=context,
            reason=command.reason,
        )


class ListProvidersHandler(_Handler):
    """Lists providers (never secret material)."""

    async def handle(self, query: ListProviders) -> tuple[ProviderView, ...]:
        return await container_for(self._services).registry.list_providers()


class GetProviderHandler(_Handler):
    """Fetches one provider; raises ProviderNotFoundError when missing."""

    async def handle(self, query: GetProvider) -> ProviderView:
        return await container_for(self._services).registry.get_provider(
            query.provider_id
        )


class ListEndpointsHandler(_Handler):
    """Lists one provider's endpoints."""

    async def handle(self, query: ListEndpoints) -> tuple[EndpointView, ...]:
        return await container_for(self._services).registry.list_endpoints(
            query.provider_id
        )


class ListCanonicalModelsHandler(_Handler):
    """Lists the canonical catalog with bindings."""

    async def handle(self, query: ListCanonicalModels) -> tuple[ModelView, ...]:
        grouped = await container_for(self._services).registry.list_models()
        return tuple(
            ModelView(
                canonical_name=model.canonical_name,
                vendor=model.vendor,
                family=model.family,
                revision=model.revision,
                context_window=model.context_window,
                capabilities=model.capabilities,
                enabled=model.enabled,
                bindings=tuple(
                    {
                        "id": binding.id,
                        "endpoint_id": binding.endpoint_id,
                        "provider_model_id": binding.provider_model_id,
                        "equivalence_level": binding.equivalence_level,
                        "availability": binding.availability,
                        "is_active": binding.is_active,
                    }
                    for binding in bindings
                ),
            )
            for model, bindings in grouped
        )


class ListRoutingRulesHandler(_Handler):
    """Lists routing rules."""

    async def handle(self, query: ListRoutingRules) -> tuple[RuleView, ...]:
        return await container_for(self._services).registry.list_rules()


class GetRouteLockHandler(_Handler):
    """Fetches one route lock; 404-mapped when missing."""

    async def handle(self, query: GetRouteLock) -> object:
        lock = await container_for(self._services).locks.get_lock(query.lock_id)
        if lock is None:
            raise RouteLockNotFoundError(
                f"route lock {query.lock_id!r} not found",
                context={"lock_id": query.lock_id},
            )
        return lock


class GetActiveRouteLockHandler(_Handler):
    """Fetches a scope's active lock."""

    async def handle(self, query: GetActiveRouteLock) -> object:
        if query.scope_type not in VALID_SCOPE_TYPES:
            raise ModelGatewayValidationError(
                f"invalid lock scope type: {query.scope_type!r}",
                context={"scope_type": query.scope_type},
            )
        return await container_for(self._services).locks.get_active_lock(
            query.scope_type, query.scope_id
        )


class SimulateRouteHandler(_Handler):
    """Dry-runs a routing decision."""

    async def handle(self, query: SimulateRoute) -> object:
        return await container_for(self._services).gateway.simulate(query.context)


class ListReceiptsHandler(_Handler):
    """Lists routing receipts."""

    async def handle(self, query: ListReceipts) -> tuple[ReceiptView, ...]:
        services = resolve_services(self._services)
        async with services.scope_factory() as scope:
            rows: tuple[ReceiptRow, ...] = await scope.store().list_receipts(
                task_id=query.task_id, limit=query.limit
            )
        return tuple(ReceiptView.from_row(row) for row in rows)


class InvokeModelJobHandler(_Handler):
    """Worker job handler: executes one model invocation from a payload.

    Job type: ``model_gateway.invoke``.  The payload is an
    :class:`InvocationRequest` in JSON form; the result is the completion's
    transport payload.  The agent runtime reaches the gateway through this
    job seam — cross-module imports stay forbidden.
    """

    job_type = "model_gateway.invoke"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        request = invocation_request_from_payload(payload)
        container = container_for(self._services)
        operation = current_operation_context()
        if operation is not None:
            with bind_operation_context(operation):
                result = await container.gateway.invoke(request)
        else:
            result = await container.gateway.invoke(request)
        return result.to_payload()


def invocation_request_from_payload(
    payload: Mapping[str, JSONValue],
) -> InvocationRequest:
    """Build an invocation request from a JSON job/HTTP payload."""
    from ..providers.contracts import ProviderMessage

    def _as_list(key: str) -> list[JSONValue]:
        raw = payload.get(key)
        return list(raw) if isinstance(raw, list) else []

    def _as_text(key: str, default: str = "") -> str:
        raw = payload.get(key)
        return str(raw) if raw is not None else default

    def _as_opt_text(key: str) -> str | None:
        raw = payload.get(key)
        return str(raw) if raw is not None else None

    def _as_float(key: str) -> float | None:
        raw = payload.get(key)
        return float(raw) if isinstance(raw, (int, float)) else None

    def _as_int(key: str, default: int | None = None) -> int | None:
        raw = payload.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return default
        return int(raw)

    messages = tuple(
        ProviderMessage(
            role=_as_text("role", "user"),
            content=_as_text("content", ""),
        )
        for message in _as_list("messages")
        if isinstance(message, Mapping)
    )
    tools = tuple(
        dict(tool) for tool in _as_list("tools") if isinstance(tool, Mapping)
    )

    return InvocationRequest(
        task_id=_as_text("task_id").strip(),
        scope_id=_as_text("scope_id").strip(),
        scope_type=_as_text("scope_type", "task"),
        role=_as_opt_text("role"),
        prompt=_as_text("prompt"),
        messages=messages,
        system_instruction=_as_opt_text("system_instruction"),
        temperature=_as_float("temperature"),
        max_output_tokens=_as_int("max_output_tokens"),
        tools=tools,
        task_labels=tuple(str(item) for item in _as_list("task_labels")),
        agent_type=_as_text("agent_type"),
        workflow_type=_as_text("workflow_type"),
        available_capabilities=tuple(
            str(item) for item in _as_list("available_capabilities")
        ),
        estimated_context_tokens=_as_int("estimated_context_tokens", 0) or 0,
        has_tools=bool(payload.get("has_tools", False)),
        has_vision=bool(payload.get("has_vision", False)),
        cost_class=_as_text("cost_class"),
        requires_local=bool(payload.get("requires_local", False)),
        requires_private=bool(payload.get("requires_private", False)),
        user_preference_model=_as_opt_text("user_preference_model"),
    )
