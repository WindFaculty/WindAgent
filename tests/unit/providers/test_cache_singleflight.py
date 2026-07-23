"""
Tests for Phase 9 — Provider Caches and Singleflight.

Acceptance gates verified:
    [ ] Không cache chéo tenant/user
    [ ] DB vẫn là source of truth cho route lock
    [ ] Credential rotation invalidates discovery cache
    [ ] Model revision change causes miss
    [ ] Tool schema change causes miss
    [ ] Side-effect requests không response-cache
    [ ] Cache backend down không làm provider execution down
    [ ] Singleflight concurrency test pass
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List

import httpx
import pytest

from windagent_providers.base.contracts import (
    CacheDirective,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from windagent_providers.base.ports import CachePort
from windagent_providers.cache import (
    CacheNamespace,
    InMemoryCacheBackend,
    InMemorySingleFlight,
    ResponseCacheService,
    DiscoveryCacheService,
    HealthCacheService,
    RouteLockCacheService,
    response_cache_eligible,
    build_response_cache_key,
)
from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport
from windagent_providers.routing.circuit_breaker import InMemoryEndpointStateManager
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.memory_ports import (
    InMemoryEndpointRegistry,
    InMemoryQuotaStateManager,
    InMemoryRouteAttemptLog,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _binding(
    endpoint_id: str,
    canonical_model_id: str,
    provider_model_id: str,
    provider_name: str,
    base_url: str,
) -> Dict[str, Any]:
    return {
        "endpoint_id": endpoint_id,
        "binding_id": f"bnd-{endpoint_id}",
        "canonical_model_id": canonical_model_id,
        "provider_model_id": provider_model_id,
        "provider_name": provider_name,
        "base_url": base_url,
        "credential_ciphertext": "enc:v1:test",
        "equivalence_level": "exact_revision",
        "is_active": True,
    }


def _request(**overrides: Any) -> ProviderRequest:
    defaults: Dict[str, Any] = {
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.0,
        "seed": 42,
    }
    defaults.update(overrides)
    return ProviderRequest(**defaults)


def _coordinator_with_cache(cache: CachePort) -> EndpointExecutionCoordinator:
    registry = InMemoryEndpointRegistry([
        _binding("ep-1", "cm-gpt4o", "gpt-4o", "openai", "https://ep-1.test/v1"),
    ])
    state = InMemoryEndpointStateManager()
    quota = InMemoryQuotaStateManager()
    attempts = InMemoryRouteAttemptLog()
    response_cache = ResponseCacheService(cache)

    def resolver(candidate: Any) -> Any:
        return OpenAICompatibleTransport(
            provider_name="openai",
            base_url=candidate.base_url,
        )

    return EndpointExecutionCoordinator(
        adapter_resolver=resolver,
        endpoint_registry=registry,
        endpoint_state=state,
        quota_state=quota,
        attempt_log=attempts,
        response_cache=response_cache,
    )


# ──────────────────────────────────────────────
# Gate 1: Tenant/user isolation
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_cache_does_not_cross_tenant_or_user():
    cache = InMemoryCacheBackend()
    service = ResponseCacheService(cache)
    request = _request()

    ns_a = CacheNamespace(tenant_id="t1", user_id="u1")
    ns_b = CacheNamespace(tenant_id="t2", user_id="u2")

    response_a = ProviderResponse(
        canonical_model_id="cm-gpt4o",
        provider_model_id="gpt-4o",
        text="for A",
    )
    await service.set(request, ns_a, "cm-gpt4o", response_a)

    hit_b = await service.get(request, ns_b, "cm-gpt4o")
    assert hit_b.hit is False

    hit_a = await service.get(request, ns_a, "cm-gpt4o")
    assert hit_a.hit is True
    assert hit_a.response.text == "for A"


# ──────────────────────────────────────────────
# Gate 2: Route lock cache reads through persistent port
# ──────────────────────────────────────────────


class _FakePersistentRouteLockPort:
    def __init__(self):
        self._records: Dict[str, Dict[str, Any]] = {}
        self.create_calls: List[tuple] = []
        self.get_calls: List[tuple] = []

    async def get(self, scope_type: str, scope_id: str) -> Any:
        self.get_calls.append((scope_type, scope_id))
        return self._records.get(f"{scope_type}:{scope_id}")

    async def create(self, scope_type: str, scope_id: str, canonical_model_id: str) -> Dict[str, Any]:
        self.create_calls.append((scope_type, scope_id))
        record = {
            "lock_id": f"lk-{uuid.uuid4().hex[:8]}",
            "scope_type": scope_type,
            "scope_id": scope_id,
            "canonical_model_id": canonical_model_id,
        }
        self._records[f"{scope_type}:{scope_id}"] = record
        return record


@pytest.mark.asyncio
async def test_route_lock_cache_reads_through_persistent_port():
    cache = InMemoryCacheBackend()
    persistent = _FakePersistentRouteLockPort()
    service = RouteLockCacheService(cache, persistent)

    # Miss -> creates via persistent port.
    created = await service.create_lock("session", "s1", "cm-gpt4o")
    assert persistent.create_calls == [("session", "s1")]

    # Cached read returns record without hitting persistent port again.
    persistent.get_calls.clear()
    cached = await service.get_lock("session", "s1")
    assert cached is not None
    assert persistent.get_calls == []
    assert cached["lock_id"] == created["lock_id"]

    # After release cache is gone; next read falls through to DB.
    await service.release_lock("session", "s1")
    cache_value = await cache.get("route-lock:session:s1")
    assert cache_value is None


# ──────────────────────────────────────────────
# Gate 3: Credential rotation invalidates discovery cache
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_credential_rotation_invalidates_discovery_cache():
    cache = InMemoryCacheBackend()
    service = DiscoveryCacheService(cache)

    models = [{"id": "gpt-4o"}]
    await service.set("ep-1", "v1", "openai/v1", models)

    hit_before = await service.get("ep-1", "v1", "openai/v1")
    assert hit_before == models

    await service.invalidate_credential_rotation("ep-1", "v1", "openai/v1")

    hit_after = await service.get("ep-1", "v1", "openai/v1")
    assert hit_after is None


# ──────────────────────────────────────────────
# Gate 4: Model revision change causes miss
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_revision_change_causes_cache_miss():
    cache = InMemoryCacheBackend()
    service = ResponseCacheService(cache)
    request = _request()
    ns = CacheNamespace()

    response_v1 = ProviderResponse(
        canonical_model_id="cm-gpt4o",
        provider_model_id="gpt-4o",
        text="rev1",
    )
    await service.set(request, ns, "cm-gpt4o", response_v1, revision="2024-05-13")

    hit_rev1 = await service.get(request, ns, "cm-gpt4o", revision="2024-05-13")
    assert hit_rev1.hit is True

    hit_rev2 = await service.get(request, ns, "cm-gpt4o", revision="2024-08-06")
    assert hit_rev2.hit is False


# ──────────────────────────────────────────────
# Gate 5: Tool schema change causes miss
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_schema_change_causes_cache_miss():
    cache = InMemoryCacheBackend()
    service = ResponseCacheService(cache)
    ns = CacheNamespace()

    tools_a = [{"type": "function", "function": {"name": "get_weather"}}]
    tools_b = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]

    req_a = _request(tools=tools_a, temperature=0.0, seed=42)
    response_a = ProviderResponse(
        canonical_model_id="cm-gpt4o",
        provider_model_id="gpt-4o",
        text="toolA",
    )
    await service.set(req_a, ns, "cm-gpt4o", response_a)

    hit_a = await service.get(req_a, ns, "cm-gpt4o")
    assert hit_a.hit is True

    req_b = _request(tools=tools_b, temperature=0.0, seed=42)
    hit_b = await service.get(req_b, ns, "cm-gpt4o")
    assert hit_b.hit is False


# ──────────────────────────────────────────────
# Gate 6: Side-effect requests not cached
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_side_effect_tool_request_not_response_cached():
    cache = InMemoryCacheBackend()
    service = ResponseCacheService(cache)
    ns = CacheNamespace()

    side_effect_request = _request(
        tools=[{"type": "function", "function": {"name": "send_email"}}],
    )
    stored = await service.set(side_effect_request, ns, "cm-gpt4o", ProviderResponse(
        canonical_model_id="cm-gpt4o",
        provider_model_id="gpt-4o",
        text="sent",
    ))
    assert stored is False

    hit = await service.get(side_effect_request, ns, "cm-gpt4o")
    assert hit.hit is False


def test_high_temperature_without_seed_not_cacheable():
    req = _request(temperature=1.0, seed=None)
    assert response_cache_eligible(req) is False


# ──────────────────────────────────────────────
# Gate 7: Cache backend down doesn't break provider execution
# ──────────────────────────────────────────────


class _BrokenCache(CachePort):
    async def get(self, key: str) -> Any:
        raise RuntimeError("cache down")

    async def set(self, key: str, value: Any, ttl_seconds: Any = None) -> None:
        raise RuntimeError("cache down")

    async def delete(self, key: str) -> bool:
        raise RuntimeError("cache down")


@pytest.mark.asyncio
async def test_provider_execution_survives_broken_response_cache():
    call_count = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["count"] += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-OK",
                "model": "gpt-4o",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cache = _BrokenCache()
    coordinator = _coordinator_with_cache(cache)

    def resolver(candidate: Any) -> Any:
        return OpenAICompatibleTransport(
            provider_name="openai",
            base_url=candidate.base_url,
            http_client=mock_client,
        )

    coordinator._adapter_resolver = resolver

    response = await coordinator.execute(
        _request(),
        {"canonical_model_id": "cm-gpt4o", "lock_id": "lk-1"},
        namespace=CacheNamespace(tenant_id="t1", user_id="u1"),
    )
    assert response.text == "OK"


# ──────────────────────────────────────────────
# Gate 8: Singleflight collapses identical cacheable requests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_singleflight_collapses_concurrent_identical_requests():
    cache = InMemoryCacheBackend()
    response_cache = ResponseCacheService(cache)
    singleflight = InMemorySingleFlight()

    call_count = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["count"] += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-OK",
                "model": "gpt-4o",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = InMemoryEndpointRegistry([
        _binding("ep-1", "cm-gpt4o", "gpt-4o", "openai", "https://ep-1.test/v1"),
    ])
    state = InMemoryEndpointStateManager()
    quota = InMemoryQuotaStateManager()
    attempts = InMemoryRouteAttemptLog()

    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda c: OpenAICompatibleTransport(
            provider_name="openai", base_url=c.base_url, http_client=mock_client
        ),
        endpoint_registry=registry,
        endpoint_state=state,
        quota_state=quota,
        attempt_log=attempts,
        response_cache=response_cache,
        singleflight=singleflight,
    )

    lock = {"canonical_model_id": "cm-gpt4o", "lock_id": "lk-1"}
    ns = CacheNamespace(tenant_id="t1", user_id="u1")
    req = _request()

    async def call() -> ProviderResponse:
        return await coordinator.execute(req, lock, namespace=ns)

    responses = await asyncio.gather(*[call() for _ in range(5)])
    assert all(r.text == "OK" for r in responses)
    assert call_count["count"] == 1
