"""
Tests for Phase 8 — Endpoint Failover, Quota, Circuit Breaker, and Cooldown.

Acceptance gates verified:
    [ ] 429 failover cùng model pass
    [ ] Canonical model không đổi
    [ ] Route lock không đổi
    [ ] Attempt audit đầy đủ
    [ ] Không duplicate billing ngoài retry contract
    [ ] Circuit breaker pass
    [ ] Distributed cooldown pass
    [ ] 400 không bị retry mù
    [ ] Partial streaming policy pass
    [ ] All exhausted trả SameModelEndpointExhausted
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List

import httpx
import pytest

from windagent_providers.base.contracts import (
    ProviderRequest,
    ProviderStreamEvent,
)
from windagent_providers.base.errors import (
    InvalidRequestFailure,
    ProviderUnavailableFailure,
    SameModelEndpointExhausted,
)
from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport
from windagent_providers.routing.circuit_breaker import InMemoryEndpointStateManager
from windagent_providers.routing.endpoint_selector import EndpointSelector
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.memory_ports import (
    InMemoryEndpointRegistry,
    InMemoryQuotaStateManager,
    InMemoryRouteAttemptLog,
)


def _binding(
    endpoint_id: str,
    canonical_model_id: str,
    provider_model_id: str,
    provider_name: str,
    base_url: str,
    credential_ciphertext: str = "enc:v1:test",
    equivalence_level: str = "exact_revision",
    is_active: bool = True,
) -> Dict[str, Any]:
    return {
        "endpoint_id": endpoint_id,
        "binding_id": f"bnd-{endpoint_id}",
        "canonical_model_id": canonical_model_id,
        "provider_model_id": provider_model_id,
        "provider_name": provider_name,
        "base_url": base_url,
        "credential_ciphertext": credential_ciphertext,
        "equivalence_level": equivalence_level,
        "is_active": is_active,
    }


def _make_coordinator(bindings: List[Dict[str, Any]]) -> tuple[EndpointExecutionCoordinator, InMemoryRouteAttemptLog]:
    registry = InMemoryEndpointRegistry(bindings)
    state = InMemoryEndpointStateManager()
    quota = InMemoryQuotaStateManager()
    attempts = InMemoryRouteAttemptLog()

    def adapter_resolver(provider_name: str) -> Any:
        # Return a fresh transport for each provider; tests inject http_client per call.
        return OpenAICompatibleTransport(provider_name=provider_name, base_url=f"https://{provider_name}.test/v1")

    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=adapter_resolver,
        endpoint_registry=registry,
        endpoint_state=state,
        quota_state=quota,
        attempt_log=attempts,
    )
    return coordinator, attempts


def _lock(canonical_model_id: str = "cm-gpt4o") -> Dict[str, Any]:
    return {
        "lock_id": f"lk-{uuid.uuid4().hex[:8]}",
        "canonical_model_id": canonical_model_id,
        "scope": "session",
        "scope_id": "sess-test",
    }


def _request() -> ProviderRequest:
    return ProviderRequest(messages=[{"role": "user", "content": "Hello"}])


# ──────────────────────────────────────────────
# Gate 1: 429 failover cùng model
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_429_failover_to_same_model_succeeds():
    """Endpoint A returns 429; endpoint B with exact revision succeeds."""
    call_count = {"A": 0, "B": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        # Adapter base_url for openai is https://openai.test/v1
        host = request.url.host
        if "ep-a" in host:
            call_count["A"] += 1
            return httpx.Response(429, json={"error": {"message": "Rate limit"}}, headers={"retry-after": "2"})
        call_count["B"] += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-B",
                "model": "gpt-4o-2024-05-13",
                "choices": [{"message": {"role": "assistant", "content": "OK from B"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    bindings = [
        _binding("ep-a", "cm-gpt4o", "gpt-4o", "openai", "https://ep-a.test/v1"),
        _binding("ep-b", "cm-gpt4o", "gpt-4o", "openai", "https://ep-b.test/v1"),
    ]
    coordinator, attempts = _make_coordinator(bindings)

    # Override adapter resolver to build per-candidate mock transports so the
    # coordinator calls ep-a first, then ep-b on failover.
    def resolver(candidate: Any) -> Any:
        if candidate.endpoint_id == "ep-a":
            return OpenAICompatibleTransport(
                provider_name="openai", base_url="https://ep-a.test/v1", http_client=mock_client
            )
        return OpenAICompatibleTransport(
            provider_name="openai", base_url="https://ep-b.test/v1", http_client=mock_client
        )

    coordinator._adapter_resolver = resolver  # type: ignore[assignment]

    lock = _lock("cm-gpt4o")
    response = await coordinator.execute(_request(), lock, turn_id="t1")

    assert response.text == "OK from B"
    assert response.canonical_model_id == "cm-gpt4o"
    assert call_count["A"] == 1
    assert call_count["B"] == 1

    records = attempts.all_records()
    assert len(records) == 2
    assert records[0]["status"] == "rate_limited"
    assert records[0]["endpoint_id"] == "ep-a"
    assert records[1]["status"] == "success"
    assert records[1]["endpoint_id"] == "ep-b"


# ──────────────────────────────────────────────
# Gate 2: timeout then success
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_then_success_failover():
    def handler(request: httpx.Request) -> httpx.Response:
        if "ep-a" in request.url.host:
            raise httpx.ConnectTimeout("connection timed out")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-OK",
                "model": "gpt-4o",
                "choices": [{"message": {"role": "assistant", "content": "Timeout recovery"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    coordinator, attempts = _make_coordinator([
        _binding("ep-a", "cm-gpt4o", "gpt-4o", "openai", "https://ep-a.test/v1"),
        _binding("ep-b", "cm-gpt4o", "gpt-4o", "openai", "https://ep-b.test/v1"),
    ])

    # Override adapter resolver: ep-a always fails with timeout, ep-b succeeds.
    def resolver(candidate: Any) -> Any:
        base = "https://ep-a.test/v1" if candidate.endpoint_id == "ep-a" else "https://ep-b.test/v1"
        return OpenAICompatibleTransport(provider_name="openai", base_url=base, http_client=mock_client)

    coordinator._adapter_resolver = resolver  # type: ignore[assignment]

    response = await coordinator.execute(_request(), _lock("cm-gpt4o"))
    assert response.text == "Timeout recovery"
    assert response.canonical_model_id == "cm-gpt4o"
    assert attempts.all_records()[-1]["status"] == "success"


# ──────────────────────────────────────────────
# Gate 3: all endpoints exhausted
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_endpoints_exhausted_raises_same_model_exhausted():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    coordinator, attempts = _make_coordinator([
        _binding("ep-a", "cm-gpt4o", "gpt-4o", "openai", "https://ep-a.test/v1"),
        _binding("ep-b", "cm-gpt4o", "gpt-4o", "openai", "https://ep-b.test/v1"),
    ])

    # Override adapter resolver: ep-a uses the shared handler, ep-b same handler.
    def resolver(candidate: Any) -> Any:
        base = "https://ep-a.test/v1" if candidate.endpoint_id == "ep-a" else "https://ep-b.test/v1"
        return OpenAICompatibleTransport(provider_name="openai", base_url=base, http_client=mock_client)

    coordinator._adapter_resolver = resolver  # type: ignore[assignment]

    with pytest.raises(SameModelEndpointExhausted):
        await coordinator.execute(_request(), _lock("cm-gpt4o"))

    for rec in attempts.all_records():
        assert rec["error_class"] == "ProviderUnavailableFailure"


# ──────────────────────────────────────────────
# Gate 4: 400 does not failover blindly
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_400_invalid_request_stops_no_blind_failover():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Bad request"}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    coordinator, attempts = _make_coordinator([
        _binding("ep-a", "cm-gpt4o", "gpt-4o", "openai", "https://ep-a.test/v1"),
        _binding("ep-b", "cm-gpt4o", "gpt-4o", "openai", "https://ep-b.test/v1"),
    ])

    # Override adapter resolver: ep-a uses the shared handler, ep-b same handler.
    def resolver(candidate: Any) -> Any:
        base = "https://ep-a.test/v1" if candidate.endpoint_id == "ep-a" else "https://ep-b.test/v1"
        return OpenAICompatibleTransport(provider_name="openai", base_url=base, http_client=mock_client)

    coordinator._adapter_resolver = resolver  # type: ignore[assignment]

    with pytest.raises(InvalidRequestFailure):
        await coordinator.execute(_request(), _lock("cm-gpt4o"))

    # Only one attempt recorded because policy stops on 400.
    assert len(attempts.all_records()) == 1


# ──────────────────────────────────────────────
# Gate 5: circuit breaker opens after threshold
# ────────────────────────────────────────��─────

@pytest.mark.asyncio
async def test_circuit_opens_after_consecutive_failures():
    state = InMemoryEndpointStateManager(failure_threshold=2, half_open_timeout_seconds=300.0)

    # Manually record 2 failures.
    await state.record_failure("ep-fail", "ProviderUnavailableFailure", 503)
    await state.record_failure("ep-fail", "ProviderUnavailableFailure", 503)

    assert (await state.is_available("ep-fail")) is False

    # Quota manager always says yes.
    quota = InMemoryQuotaStateManager()
    selector = EndpointSelector(state, quota)

    bindings = [_binding("ep-fail", "cm-gpt4o", "gpt-4o", "openai", "https://ep-fail.test/v1")]
    with pytest.raises(SameModelEndpointExhausted):
        await selector.select_candidates(bindings)


# ──────────────────────────────────────────────
# Gate 6: cooldown excludes endpoint
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cooldown_excludes_endpoint_from_selection():
    state = InMemoryEndpointStateManager()
    await state.set_cooldown("ep-cold", datetime.now(timezone.utc) + timedelta(seconds=60))

    quota = InMemoryQuotaStateManager()
    selector = EndpointSelector(state, quota)

    bindings = [
        _binding("ep-cold", "cm-gpt4o", "gpt-4o", "openai", "https://ep-cold.test/v1"),
        _binding("ep-warm", "cm-gpt4o", "gpt-4o", "openai", "https://ep-warm.test/v1"),
    ]
    candidates = await selector.select_candidates(bindings)
    assert len(candidates) == 1
    assert candidates[0].endpoint_id == "ep-warm"


# ──────────────────────────────────────────────
# Gate 7: exact revision filter
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_exact_revision_bindings_not_failover_eligible():
    state = InMemoryEndpointStateManager()
    quota = InMemoryQuotaStateManager()
    selector = EndpointSelector(state, quota)

    bindings = [
        _binding("ep-exact", "cm-gpt4o", "gpt-4o", "openai", "https://ep-exact.test/v1", equivalence_level="exact_revision"),
        _binding("ep-approx", "cm-gpt4o", "gpt-4o", "openai", "https://ep-approx.test/v1", equivalence_level="approximate"),
    ]
    candidates = await selector.select_candidates(bindings)
    assert [c.endpoint_id for c in candidates] == ["ep-exact"]


# ──────────────────────────────────────────────
# Gate 8: auth failure tries binding with other credential
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_failure_failover_to_other_credential():
    def handler(request: httpx.Request) -> httpx.Response:
        if "ep-a" in request.url.host:
            return httpx.Response(401, json={"error": {"message": "Invalid key"}})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-auth-ok",
                "model": "gpt-4o",
                "choices": [{"message": {"role": "assistant", "content": "OK with other key"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    coordinator, attempts = _make_coordinator([
        _binding("ep-a", "cm-gpt4o", "gpt-4o", "openai", "https://ep-a.test/v1", credential_ciphertext="enc:v1:key1"),
        _binding("ep-b", "cm-gpt4o", "gpt-4o", "openai", "https://ep-b.test/v1", credential_ciphertext="enc:v1:key2"),
    ])

    # Override adapter resolver: ep-a uses auth failure handler, ep-b succeeds.
    def resolver(candidate: Any) -> Any:
        base = "https://ep-a.test/v1" if candidate.endpoint_id == "ep-a" else "https://ep-b.test/v1"
        return OpenAICompatibleTransport(provider_name="openai", base_url=base, http_client=mock_client)

    coordinator._adapter_resolver = resolver  # type: ignore[assignment]

    response = await coordinator.execute(_request(), _lock("cm-gpt4o"))
    assert response.text == "OK with other key"


# ──────────────────────────────────────────────
# Gate 9: partial stream failure emits error event
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_partial_stream_failure_emits_error_and_stops():
    stream_count = {"A": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "ep-a" in request.url.host:
            stream_count["A"] += 1
            sse = 'data: {"choices": [{"delta": {"content": "tok"}}]}\n\n'
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, text='data: [DONE]\n\n', headers={"content-type": "text/event-stream"})

    class ControlledTransport(OpenAICompatibleTransport):
        def __init__(self, fail_after_n: int = 1):
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            super().__init__(provider_name="openai", base_url="https://ep-a.test/v1", http_client=client)
            self.fail_after_n = fail_after_n

        async def stream(self, request: ProviderRequest, model_id: str) -> AsyncIterator[ProviderStreamEvent]:
            count = 0
            async for event in super().stream(request, model_id):
                yield event
                count += 1
                if count >= self.fail_after_n:
                    raise ProviderUnavailableFailure("simulated mid-stream failure")

    coordinator, attempts = _make_coordinator([
        _binding("ep-a", "cm-gpt4o", "gpt-4o", "openai", "https://ep-a.test/v1"),
        _binding("ep-b", "cm-gpt4o", "gpt-4o", "openai", "https://ep-b.test/v1"),
    ])
    coordinator._adapter_resolver = lambda candidate: ControlledTransport(fail_after_n=1)

    events = []
    async for event in coordinator.execute_stream(_request(), _lock("cm-gpt4o")):
        events.append(event)

    assert any(e.event_type == "token" for e in events)
    assert any(e.event_type == "error" for e in events)
    # Should NOT have harvested endpoint B after emitting tokens.
    assert not any(e.event_type == "done" for e in events)
