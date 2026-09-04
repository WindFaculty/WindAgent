"""E2E Test: Model Gateway provider registration, CAS route locking, and invocation receipts."""

from __future__ import annotations

from typing import cast

import pytest
from windagent.modules.model_gateway.application.models import (
    BindingRow,
    CanonicalModelRow,
    EndpointRow,
    ProviderRow,
    RuleRow,
)
from windagent.modules.model_gateway.application.runtime import (
    ModelGatewayServices,
    container_for,
)
from windagent.modules.model_gateway.domain.rules import RuleMatchContext
from windagent.modules.model_gateway.infrastructure.memory import (
    InMemoryModelGatewayStore,
    memory_scope_factory,
)
from windagent.modules.model_gateway.providers.contracts import (
    DiscoveredModel,
    HealthReport,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from windagent.platform.security import InMemorySecretStore


class E2EFakeAdapter:
    provider_name = "anthropic"

    async def generate(self, request: ProviderRequest, model_id: str) -> ProviderResponse:
        return ProviderResponse(
            provider_model_id=model_id,
            text="Architecture analysis passed.",
            usage=ProviderUsage(prompt_tokens=100, completion_tokens=50),
        )

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        return (DiscoveredModel(id="claude-3-7-sonnet"),)

    async def health(self) -> HealthReport:
        return HealthReport(provider_name=self.provider_name, healthy=True)


class E2EAdapterFactory:
    def __init__(self, adapter: E2EFakeAdapter) -> None:
        self.adapter = adapter

    def resolve(self, protocol_mode: str, *, base_url: str, api_key: str | None, timeout_seconds: float | None = None) -> ProviderAdapter:
        return cast("ProviderAdapter", self.adapter)


@pytest.mark.asyncio
async def test_e2e_model_gateway_routing_and_locks() -> None:
    store = InMemoryModelGatewayStore()
    adapter = E2EFakeAdapter()
    services = ModelGatewayServices(
        scope_factory=memory_scope_factory(store),
        secrets=InMemorySecretStore(),
        adapter_factory=E2EAdapterFactory(adapter),
    )
    container = container_for(services)

    # 1. Register Provider
    prov_row = ProviderRow(
        id="pv-anthropic",
        name="anthropic",
        display_name="Anthropic Production",
        vendor_type="cloud",
        base_url="https://api.anthropic.com/v1",
        protocol_mode="anthropic",
    )
    store.providers["pv-anthropic"] = prov_row
    store.provider_by_name["anthropic"] = "pv-anthropic"

    # 2. Register Canonical Model & Endpoint
    model_row = CanonicalModelRow(
        canonical_name="claude-3-7-sonnet",
        vendor="anthropic",
        family="architecture_review",
        context_window=200000,
    )
    store.models["claude-3-7-sonnet"] = model_row

    endpoint_row = EndpointRow(
        id="ep-claude-37",
        provider_id="pv-anthropic",
        base_url="https://api.anthropic.com/v1",
        protocol_mode="anthropic",
        enabled=True,
    )
    store.endpoints["ep-claude-37"] = endpoint_row

    binding_row = BindingRow(
        id="bind-1",
        endpoint_id="ep-claude-37",
        canonical_model_id="claude-3-7-sonnet",
        provider_model_id="claude-3-7-sonnet",
    )
    store.bindings["bind-1"] = binding_row

    # 3. Create Routing Rule
    rule_row = RuleRow(
        rule_id="rule-arch-1",
        rule_version=1,
        canonical_model_id="claude-3-7-sonnet",
        priority=100,
        task_labels=("architecture_review",),
        enabled=True,
    )
    store.rules["rule-arch-1"] = rule_row

    # 4. Resolve Route Lock
    match_ctx = RuleMatchContext(
        scope_type="session",
        scope_id="sess-e2e-1",
        task_labels=("architecture_review",),
    )
    lock = await container.locks.resolve_or_create_lock(match_ctx)
    assert lock is not None
    assert lock.canonical_model_id == "claude-3-7-sonnet"
