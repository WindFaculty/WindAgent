"""Offline unit tests for model-gateway application services (in-memory)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from windagent.modules.model_gateway.application.gateway import InvocationRequest
from windagent.modules.model_gateway.application.models import (
    BindingRow,
    CanonicalModelRow,
    CredentialRow,
    EndpointRow,
    ProviderRow,
    RuleRow,
)
from windagent.modules.model_gateway.application.runtime import (
    ModelGatewayContainer,
    ModelGatewayServices,
    bind_services,
)
from windagent.modules.model_gateway.domain.errors import (
    NetworkFailure,
    NoMatchingRuleError,
    RateLimitFailure,
    SameModelEndpointExhausted,
)
from windagent.modules.model_gateway.domain.route_lock import LockStatus
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
    ProviderStreamEvent,
    ProviderUsage,
    StreamEventType,
)
from windagent.platform.security import InMemorySecretStore


class FakeAdapter:
    """Scriptable adapter: pops behaviors per model, then answers OK."""

    provider_name = "fake"

    def __init__(self, script: dict[str, list[Any]]) -> None:
        self.script = script
        self.calls: list[tuple[str, str]] = []

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        self.calls.append(("generate", model_id))
        behaviors = self.script.setdefault(model_id, [])
        if behaviors:
            behavior = behaviors.pop(0)
            if isinstance(behavior, Exception):
                raise behavior
            return ProviderResponse(
                provider_model_id=model_id,
                text=str(behavior),
                usage=ProviderUsage(prompt_tokens=3, completion_tokens=2),
            )
        return ProviderResponse(
            provider_model_id=model_id,
            text="ok",
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1),
        )

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append(("stream", model_id))
        yield ProviderStreamEvent(event_type=StreamEventType.DONE)
        return

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        return (DiscoveredModel(id="fake-model"),)

    async def health(self) -> HealthReport:
        return HealthReport(provider_name=self.provider_name, healthy=True)


class FakeAdapterFactory:
    def __init__(self, adapter: FakeAdapter) -> None:
        self.adapter = adapter
        self.resolved: list[tuple[str, str | None]] = []

    def resolve(
        self,
        protocol_mode: str,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float | None = None,
    ) -> ProviderAdapter:
        self.resolved.append((protocol_mode, api_key))
        return cast("ProviderAdapter", self.adapter)


def _services(adapter: FakeAdapter) -> tuple[ModelGatewayServices, InMemoryModelGatewayStore]:
    store = InMemoryModelGatewayStore()
    services = ModelGatewayServices(
        scope_factory=memory_scope_factory(store),
        secrets=InMemorySecretStore(),
        adapter_factory=FakeAdapterFactory(adapter),
    )
    return services, store


def _seed(store: InMemoryModelGatewayStore, *, provider_name: str = "fake") -> None:
    store.providers["pv-fake"] = ProviderRow(
        id="pv-fake",
        name=provider_name,
        display_name=provider_name,
        vendor_type="cloud",
        base_url="https://fake.example/v1",
        protocol_mode="openai",
    )
    store.provider_by_name[provider_name] = "pv-fake"
    store.endpoints["ep-fake"] = EndpointRow(
        id="ep-fake",
        provider_id="pv-fake",
        base_url="https://fake.example/v1",
        protocol_mode="openai",
    )
    store.credentials["cred-1"] = CredentialRow(
        id="cred-1",
        provider_id="pv-fake",
        secret_name="model_gateway/credentials/cred-1",
    )
    store.models["windagent/story-default"] = CanonicalModelRow(
        canonical_name="windagent/story-default",
        vendor="fake",
        family="story-default",
    )
    store.bindings[("ep-fake", "windagent/story-default")] = BindingRow(
        id="bnd-1",
        endpoint_id="ep-fake",
        canonical_model_id="windagent/story-default",
        provider_model_id="fake-model",
    )
    store.rules["story-default"] = RuleRow(
        rule_id="story-default",
        rule_version=1,
        canonical_model_id="windagent/story-default",
        description="default story model",
    )


def _request(**overrides: object) -> InvocationRequest:
    defaults: dict[str, object] = {
        "task_id": "task-1",
        "scope_id": "session-1",
        "scope_type": "task",
        "prompt": "hello",
    }
    defaults.update(overrides)
    return InvocationRequest(**defaults)  # type: ignore[arg-type]


class TestProviderRegistry:
    @pytest.mark.asyncio
    async def test_register_provider_writes_secret_and_metadata(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            view = await container.registry.register_provider(
                name="openai",
                base_url="https://api.openai.com/v1",
                credential_secret="sk-abc",
            )
        assert view.has_credential is True
        assert view.endpoint_count == 1
        payload = view.to_payload()
        assert "sk-abc" not in str(payload)
        assert "sk-abc" not in str(store.credentials)
        credential = await store.active_credential_for_provider(view.id)
        assert credential is not None
        secret = await services.secrets.read(credential.secret_name)
        assert secret is not None and secret.reveal() == "sk-abc"

    @pytest.mark.asyncio
    async def test_duplicate_provider_is_rejected(self) -> None:
        adapter = FakeAdapter(script={})
        services, _ = _services(adapter)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            await container.registry.register_provider(
                name="openai", base_url="https://x/v1"
            )
            from windagent.modules.model_gateway.domain.errors import (
                DuplicateProviderError,
            )

            with pytest.raises(DuplicateProviderError):
                await container.registry.register_provider(
                    name="openai", base_url="https://y/v1"
                )

    @pytest.mark.asyncio
    async def test_credential_rotation_bumps_version_and_revokes(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            provider = await container.registry.register_provider(
                name="openai", base_url="https://x/v1", credential_secret="v1"
            )
            rotated = await container.registry.rotate_credential(
                provider.id, secret="v2"
            )
        assert rotated.secret_version == 2
        secret = await services.secrets.read(
            [c for c in store.credentials.values() if c.revoked_at is None][0].secret_name
        )
        assert secret is not None and secret.reveal() == "v2"

    @pytest.mark.asyncio
    async def test_provider_delete_is_blocked_by_enabled_rules(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            provider = await container.registry.register_provider(
                name="openai", base_url="https://x/v1"
            )
            await container.registry.record_discovery(
                store.endpoints[list(store.endpoints)[0]].id
                if store.endpoints
                else "",
                (DiscoveredModel(id="gpt-4o"),),
            )
            store.rules["r1"] = RuleRow(
                rule_id="r1",
                rule_version=1,
                canonical_model_id="gpt-4o",
            )
            from windagent.modules.model_gateway.domain.errors import ProviderInUseError

            with pytest.raises(ProviderInUseError):
                await container.registry.delete_provider(provider.id)
            outcome = await container.registry.delete_provider(
                provider.id, allow_disabling_rules=True
            )
            assert outcome["disabled_rules"] == ["r1"]
            assert store.rules["r1"].enabled is False

    @pytest.mark.asyncio
    async def test_discovery_reconciliation_marks_stale_bindings(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            await container.registry.register_provider(
                name="openai", base_url="https://x/v1"
            )
            endpoint_id = next(iter(store.endpoints))
            first = await container.registry.record_discovery(
                endpoint_id, (DiscoveredModel(id="gpt-4o"),)
            )
            assert first.added == ("gpt-4o",)
            second = await container.registry.record_discovery(
                endpoint_id, (DiscoveredModel(id="gpt-4o"),)
            )
            assert second.unchanged == ("gpt-4o",)
            third = await container.registry.record_discovery(
                endpoint_id, (DiscoveredModel(id="gpt-4o-2024-11-20"),)
            )
            assert third.added == ("gpt-4o-2024-11-20",)
            assert third.unavailable == ("gpt-4o",)
            bindings = await store.list_bindings()
            by_model = {b.provider_model_id: b for b in bindings}
            assert by_model["gpt-4o"].availability == "unavailable"
            assert by_model["gpt-4o"].is_active is False


class TestRouteLockService:
    @pytest.mark.asyncio
    async def test_resolve_creates_then_reuses_the_lock(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        _seed(store)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            context = RuleMatchContext(scope_id="s1", scope_type="task")
            first = await container.locks.resolve_or_create_lock(context)
            second = await container.locks.resolve_or_create_lock(context)
            assert first.lock_id == second.lock_id
            event_types = [e.event_type for e in store.events]
            assert "model_gateway.route.locked" in event_types
            assert "model_gateway.route.reused" in event_types

    @pytest.mark.asyncio
    async def test_no_matching_rule_fails_closed(self) -> None:
        adapter = FakeAdapter(script={})
        services, _ = _services(adapter)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            with pytest.raises(NoMatchingRuleError):
                await container.locks.resolve_or_create_lock(
                    RuleMatchContext(scope_id="s1", scope_type="task")
                )

    @pytest.mark.asyncio
    async def test_reselect_replaces_the_active_lock(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        _seed(store)
        store.rules["alt"] = RuleRow(
            rule_id="alt",
            rule_version=1,
            canonical_model_id="windagent/story-default",
            user_preference_model="windagent/story-default",
        )
        with bind_services(services):
            container = ModelGatewayContainer(services)
            original = await container.locks.resolve_or_create_lock(
                RuleMatchContext(scope_id="s1", scope_type="task")
            )
            replacement = await container.locks.reselect_model(
                scope_type="task",
                scope_id="s1",
                new_context=RuleMatchContext(
                    scope_id="s1",
                    scope_type="task",
                    user_preference_model="windagent/story-default",
                ),
                reason="user_override",
            )
            assert replacement.lock_id != original.lock_id
            fetched = await container.locks.get_lock(original.lock_id)
            assert fetched is not None
            assert fetched.status == LockStatus.RELEASED.value
            assert replacement.is_active
            event_types = [e.event_type for e in store.events]
            assert "model_gateway.model.reselected" in event_types

    @pytest.mark.asyncio
    async def test_fallback_lock_keeps_primary_active(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        _seed(store)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            primary = await container.locks.resolve_or_create_lock(
                RuleMatchContext(scope_id="s1", scope_type="task")
            )
            fallback = await container.locks.create_fallback_lock(
                scope_type="task",
                scope_id="s1",
                canonical_model_id="windagent/story-default",
                reason="failover",
                source_lock_id=primary.lock_id,
            )
            active = await container.locks.get_active_lock("task", "s1")
            assert active is not None
            assert active.lock_id == primary.lock_id
            assert fallback.is_fallback is True
            assert fallback.source_lock_id == primary.lock_id


class TestModelGatewayInvocation:
    @pytest.mark.asyncio
    async def test_invoke_returns_routed_completion_and_receipt(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        _seed(store)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            result = await container.gateway.invoke(_request())
        assert result.response.text == "ok"
        assert result.canonical_model_id == "windagent/story-default"
        assert result.route_lock_id
        assert result.fallback_used is False
        receipts = store.receipts
        assert len(receipts) == 1
        assert receipts[0].status == "success"
        assert store.attempts[0].status == "success"

    @pytest.mark.asyncio
    async def test_rate_limit_exhausts_a_single_endpoint(self) -> None:
        adapter = FakeAdapter(
            script={
                "fake-model": [RateLimitFailure(endpoint_id="ep-fake")] * 10,
            }
        )
        services, store = _services(adapter)
        _seed(store)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            with pytest.raises(SameModelEndpointExhausted):
                await container.gateway.invoke(_request())
        # One endpoint: the 429 cools it down, the next selection is empty,
        # and the loop stops with the exhausted error (old coordinator flow).
        failed = [a for a in store.attempts if a.status == "failed"]
        assert len(failed) == 1
        state = await store.get_endpoint_state("ep-fake")
        assert state.cooldown_until is not None

    @pytest.mark.asyncio
    async def test_rate_limit_fails_over_to_a_sibling_endpoint(self) -> None:
        adapter = FakeAdapter(
            script={
                "fake-model": [RateLimitFailure(endpoint_id="ep-fake")],
            }
        )
        services, store = _services(adapter)
        _seed(store)
        store.endpoints["ep-fake-2"] = EndpointRow(
            id="ep-fake-2",
            provider_id="pv-fake",
            base_url="https://fake2.example/v1",
            protocol_mode="openai",
        )
        store.bindings[("ep-fake-2", "windagent/story-default")] = BindingRow(
            id="bnd-3",
            endpoint_id="ep-fake-2",
            canonical_model_id="windagent/story-default",
            provider_model_id="fake-model",
        )
        with bind_services(services):
            container = ModelGatewayContainer(services)
            result = await container.gateway.invoke(_request())
        statuses = [a.status for a in store.attempts]
        assert statuses == ["failed", "success"]
        assert result.endpoint_id == "ep-fake-2"

    @pytest.mark.asyncio
    async def test_model_level_fallback_on_eligible_failure(self) -> None:
        adapter = FakeAdapter(
            script={
                "fake-model": [NetworkFailure(endpoint_id="ep-fake")] * 10,
                "windagent/story-fallback": [],
            }
        )
        services, store = _services(adapter)
        _seed(store)
        store.models["windagent/story-fallback"] = CanonicalModelRow(
            canonical_name="windagent/story-fallback",
            vendor="fake",
            family="story-fallback",
        )
        store.endpoints["ep-fallback"] = EndpointRow(
            id="ep-fallback",
            provider_id="pv-fake",
            base_url="https://fallback.example/v1",
            protocol_mode="openai",
        )
        store.bindings[("ep-fallback", "windagent/story-fallback")] = BindingRow(
            id="bnd-2",
            endpoint_id="ep-fallback",
            canonical_model_id="windagent/story-fallback",
            provider_model_id="windagent/story-fallback",
        )
        store.rules["story-default"] = RuleRow(
            rule_id="story-default",
            rule_version=1,
            canonical_model_id="windagent/story-default",
            fallback_model_id="windagent/story-fallback",
        )
        with bind_services(services):
            container = ModelGatewayContainer(services)
            result = await container.gateway.invoke(_request())
        assert result.fallback_used is True
        assert result.canonical_model_id == "windagent/story-fallback"
        # With one primary endpoint the network failure exhausts the model's
        # candidates, and that exhaustion is what triggers the fallback.
        assert result.fallback_reason == "same_model_endpoint_exhausted"
        receipts = store.receipts
        assert receipts[0].fallback_used is True

    @pytest.mark.asyncio
    async def test_non_eligible_failure_stops_without_fallback(self) -> None:
        from windagent.modules.model_gateway.domain.errors import ContextOverflowFailure

        adapter = FakeAdapter(
            script={"fake-model": [ContextOverflowFailure(endpoint_id="ep-fake")]}
        )
        services, store = _services(adapter)
        _seed(store)
        store.rules["story-default"] = RuleRow(
            rule_id="story-default",
            rule_version=1,
            canonical_model_id="windagent/story-default",
            fallback_model_id="windagent/story-fallback",
        )
        with bind_services(services):
            container = ModelGatewayContainer(services)
            with pytest.raises(ContextOverflowFailure):
                await container.gateway.invoke(_request())
        receipts = store.receipts
        assert receipts[0].status == "failed"

    @pytest.mark.asyncio
    async def test_simulate_reports_candidates_without_locking(self) -> None:
        adapter = FakeAdapter(script={})
        services, store = _services(adapter)
        _seed(store)
        with bind_services(services):
            container = ModelGatewayContainer(services)
            decision = await container.gateway.simulate(
                RuleMatchContext(scope_id="sim", scope_type="session")
            )
            assert decision.canonical_model_id == "windagent/story-default"
            assert decision.candidates[0]["endpoint_id"] == "ep-fake"
            assert not store.locks
            assert not store.receipts


