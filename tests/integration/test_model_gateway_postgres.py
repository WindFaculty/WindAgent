"""PostgreSQL integration tests for the model gateway (Phase 11).

Runs against the canonical database (plan section 8).  The conftest applies
the full Alembic chain — including ``0005_model_gateway`` — before these
tests, which is itself part of the phase's integration gate.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from windagent.modules.model_gateway.application.gateway import InvocationRequest
from windagent.modules.model_gateway.application.runtime import (
    ModelGatewayContainer,
    ModelGatewayServices,
)
from windagent.modules.model_gateway.domain.errors import (
    CanonicalModelDisabledError,
    NoMatchingRuleError,
    RateLimitFailure,
)
from windagent.modules.model_gateway.domain.route_lock import LockStatus
from windagent.modules.model_gateway.domain.rules import RuleMatchContext
from windagent.modules.model_gateway.infrastructure.repository import sql_scope_factory
from windagent.modules.model_gateway.infrastructure.secret_store import (
    CANONICAL_KEY_ENV,
    EncryptedSecretStore,
)
from windagent.modules.model_gateway.infrastructure.tables import (
    attempts_table,
    route_locks_table,
)
from windagent.modules.model_gateway.providers.contracts import (
    DiscoveredModel,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from windagent.platform.events.outbox import outbox_table
from windagent.platform.persistence import Database
from windagent.platform.security import InMemorySecretStore, SecretValue

pytestmark = [pytest.mark.postgres]


class ScriptedAdapter:
    provider_name = "fake"

    def __init__(self, script: dict[str, list[object]]) -> None:
        self.script = script

    async def generate(
        self, request: ProviderRequest, model_id: str
    ) -> ProviderResponse:
        behaviors = self.script.setdefault(model_id, [])
        if behaviors:
            behavior = behaviors.pop(0)
            if isinstance(behavior, Exception):
                raise behavior
            return ProviderResponse(provider_model_id=model_id, text=str(behavior))
        return ProviderResponse(
            provider_model_id=model_id,
            text="ok",
            usage=ProviderUsage(prompt_tokens=1, completion_tokens=1),
        )

    async def stream(
        self, request: ProviderRequest, model_id: str
    ) -> AsyncIterator[ProviderResponse]:
        yield ProviderResponse(provider_model_id=model_id)

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        return ()

    async def health(self) -> None:
        return None


class ScriptedAdapterFactory:
    def __init__(self, adapter: ScriptedAdapter) -> None:
        self.adapter = adapter

    def resolve(
        self,
        protocol_mode: str,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float | None = None,
    ) -> ProviderAdapter:
        return self.adapter  # type: ignore[return-value]


@pytest.fixture
def services(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> ModelGatewayServices:
    monkeypatch.setenv(CANONICAL_KEY_ENV, base64.b64encode(b"i" * 32).decode())
    return ModelGatewayServices(
        scope_factory=sql_scope_factory(database),
        secrets=InMemorySecretStore(),
        adapter_factory=ScriptedAdapterFactory(ScriptedAdapter(script={})),
    )


@pytest.fixture(autouse=True)
async def _clean_model_gateway_tables(database: Database) -> AsyncIterator[None]:
    """The integration database persists across runs; start each test clean."""
    from windagent.modules.model_gateway.infrastructure.tables import (
        attempts_table,
        bindings_table,
        canonical_models_table,
        credentials_table,
        endpoint_state_table,
        endpoints_table,
        providers_table,
        quota_state_table,
        receipts_table,
        routing_rules_table,
        secrets_table,
    )

    factory = database.session_factory
    async with factory() as session:
        for table in (
            attempts_table,
            receipts_table,
            route_locks_table,
            secrets_table,
            credentials_table,
            bindings_table,
            canonical_models_table,
            routing_rules_table,
            endpoint_state_table,
            quota_state_table,
            endpoints_table,
            providers_table,
        ):
            await session.execute(sa_delete(table))
        await session.execute(sa_delete(outbox_table))
        await session.commit()
    yield


async def _seed_model(
    container: ModelGatewayContainer, provider_id: str, model_id: str
) -> None:
    endpoint_id = (await container.registry.list_endpoints(provider_id))[0].id
    reconciliation = await container.registry.record_discovery(
        endpoint_id, (DiscoveredModel(id=model_id),)
    )
    assert reconciliation.added == (model_id,)


async def test_registry_to_lock_to_invocation_round_trip(
    services: ModelGatewayServices,
) -> None:
    container = ModelGatewayContainer(services)
    provider = await container.registry.register_provider(
        name="integration-openai",
        base_url="https://api.integration.example/v1",
        credential_secret="sk-integration",
    )
    endpoints = await container.registry.list_endpoints(provider.id)
    assert len(endpoints) == 1
    await _seed_model(container, provider.id, "gpt-4o-integration")
    await container.registry.upsert_rule(
        rule_id="integration-default", canonical_model_id="gpt-4o-integration"
    )

    lock = await container.locks.resolve_or_create_lock(
        RuleMatchContext(scope_id="scope-1", scope_type="task")
    )
    assert lock.canonical_model_id == "gpt-4o-integration"
    assert lock.routing_snapshot.rule_id == "integration-default"


async def test_concurrent_lock_resolution_yields_one_active_lock(
    services: ModelGatewayServices,
) -> None:
    container = ModelGatewayContainer(services)
    provider = await container.registry.register_provider(
        name="integration-lock",
        base_url="https://api.lock.example/v1",
    )
    await _seed_model(container, provider.id, "lock-model")
    await container.registry.upsert_rule(
        rule_id="lock-rule", canonical_model_id="lock-model"
    )

    context = RuleMatchContext(scope_id="scope-race", scope_type="task")
    first, second = await asyncio.gather(
        container.locks.resolve_or_create_lock(context),
        container.locks.resolve_or_create_lock(context),
    )
    assert first.lock_id == second.lock_id


async def test_single_active_lock_per_scope_in_database(
    database: Database, services: ModelGatewayServices
) -> None:
    container = ModelGatewayContainer(services)
    provider = await container.registry.register_provider(
        name="integration-unique",
        base_url="https://api.unique.example/v1",
    )
    await _seed_model(container, provider.id, "unique-model")
    await container.registry.upsert_rule(
        rule_id="unique-rule", canonical_model_id="unique-model"
    )
    await container.locks.resolve_or_create_lock(
        RuleMatchContext(scope_id="scope-unique", scope_type="task")
    )
    factory = database.session_factory
    async with factory() as session:
        active_count = (
            await session.execute(
                select(func.count())
                .select_from(route_locks_table)
                .where(
                    route_locks_table.c.scope_type == "task",
                    route_locks_table.c.scope_id == "scope-unique",
                    route_locks_table.c.status == LockStatus.ACTIVE.value,
                )
            )
        ).scalar()
    assert active_count == 1


async def test_invocation_persists_receipt_attempts_state_and_events(
    database: Database, services: ModelGatewayServices
) -> None:
    services.adapter_factory.adapter.script["rate-model"] = [  # type: ignore[attr-defined]
        RateLimitFailure(endpoint_id="ep-rate")
    ]
    container = ModelGatewayContainer(services)
    provider = await container.registry.register_provider(
        name="integration-rate",
        base_url="https://api.rate.example/v1",
        credential_secret="sk-rate",
    )
    await _seed_model(container, provider.id, "rate-model")
    # A second, healthy endpoint serves the failover attempt; seed discovery
    # for every endpoint so both hold bindings.
    await container.registry.add_endpoint(
        provider.id, base_url="https://api.rate2.example/v1"
    )
    for endpoint in await container.registry.list_endpoints(provider.id):
        await container.registry.record_discovery(
            endpoint.id, (DiscoveredModel(id="rate-model"),)
        )
    await container.registry.upsert_rule(
        rule_id="rate-rule", canonical_model_id="rate-model"
    )

    result = await container.gateway.invoke(
        InvocationRequest(
            task_id="task-integration-1",
            scope_id="scope-integration-1",
            scope_type="task",
            prompt="hello",
        )
    )
    assert result.response.text == "ok"
    assert result.attempts == 2

    async with sql_scope_factory(database)() as scope:
        receipts = await scope.store().list_receipts(
            task_id="task-integration-1", limit=10
        )
        assert receipts and receipts[0].status == "success"
        # Exactly one endpoint absorbed the 429 cooldown; the other served.
        for endpoint in await container.registry.list_endpoints(provider.id):
            state = await scope.store().get_endpoint_state(endpoint.id)
            if endpoint.id == result.endpoint_id:
                assert state.cooldown_until is None
                assert state.success_count == 1
            else:
                assert state.cooldown_until is not None
                assert state.failure_count == 1

    factory = database.session_factory
    async with factory() as session:
        attempt_rows = (await session.execute(select(attempts_table))).all()
        assert len(attempt_rows) == 2
        event_types = list(
            (
                await session.execute(
                    select(outbox_table.c.event_type).where(
                        outbox_table.c.event_type.like("model_gateway.%")
                    )
                )
            ).scalars()
        )
    assert "model_gateway.route.locked" in event_types


async def test_disabled_model_is_rejected_fail_closed(
    database: Database, services: ModelGatewayServices
) -> None:
    container = ModelGatewayContainer(services)
    provider = await container.registry.register_provider(
        name="integration-disabled",
        base_url="https://api.disabled.example/v1",
    )
    await _seed_model(container, provider.id, "off-model")
    await container.registry.upsert_rule(
        rule_id="off-rule", canonical_model_id="off-model"
    )
    from windagent.modules.model_gateway.infrastructure.tables import (
        canonical_models_table,
    )

    factory = database.session_factory
    async with factory() as session:
        await session.execute(
            canonical_models_table.update()
            .where(canonical_models_table.c.canonical_name == "off-model")
            .values(enabled=False)
        )
        await session.commit()

    with pytest.raises(CanonicalModelDisabledError):
        await container.locks.resolve_or_create_lock(
            RuleMatchContext(scope_id="scope-off", scope_type="task")
        )


async def test_no_matching_rule_fails_closed(
    services: ModelGatewayServices,
) -> None:
    container = ModelGatewayContainer(services)
    with pytest.raises(NoMatchingRuleError):
        await container.locks.resolve_or_create_lock(
            RuleMatchContext(scope_id="scope-empty", scope_type="task")
        )


async def test_encrypted_secret_store_round_trip_on_postgres(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CANONICAL_KEY_ENV, base64.b64encode(b"s" * 32).decode())
    store = EncryptedSecretStore(database.session_factory)
    await store.write(
        "model_gateway/credentials/test-cred", SecretValue("sk-round-trip")
    )
    value = await store.read("model_gateway/credentials/test-cred")
    assert value is not None and value.reveal() == "sk-round-trip"
    assert await store.delete("model_gateway/credentials/test-cred") is True
    assert await store.read("model_gateway/credentials/test-cred") is None

