"""A6 — real provider-neutral Studio model port tests (REAL_MODEL_RUNTIME_GATE surface).

Covers route-lock determinism (same scope reuses the lock, no silent model
flip), the ModelCompletionRequest -> ProviderRequest mapping, provenance
completeness (provider/model/usage + route lock id), typed retryability of
the full provider failure taxonomy, same-model failover, and fixture-guard
compatibility (the real port carries no ``fixture`` marker).
"""

from __future__ import annotations

import pytest

from windagent_core.contracts.providers import ProviderRequest, ProviderResponse
from windagent_core.contracts.providers.usage import ProviderUsage
from windagent_intelligence.story.prompts.fixture import assert_not_fixture, is_fixture_provider
from windagent_intelligence.video.ports import ModelCompletionRequest, ModelCompletionResult
from windagent_providers.base.errors import (
    AuthenticationFailure,
    CancellationFailure,
    ContentPolicyFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    MalformedResponseFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    PermissionFailure,
    ProviderUnavailableFailure,
    QuotaExhaustedFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
    TimeoutFailure,
)
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_worker.studio_model_port import (
    AUTH,
    QUOTA,
    SAFETY,
    SCHEMA,
    TERMINAL,
    TRANSIENT,
    UNKNOWN,
    RouteLockedModelPort,
    build_studio_ruleset,
    classify_provider_error,
)
from tests.fakes.routing_fakes import InMemoryLockStore

BINDING = {
    "endpoint_id": "ep-stub-1",
    "binding_id": "bind-stub-1",
    "provider_model_id": "stub-model-1",
    "provider_name": "stub-provider",
    "base_url": "https://stub.invalid/v1",
    "equivalence_level": "exact_revision",
    "is_active": True,
    "protocol_mode": "openai",
    "credential_ciphertext": "cipher:stub",
}


class StubEndpointState:
    async def is_available(self, endpoint_id: str) -> bool:
        return True

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        return None

    async def record_failure(self, endpoint_id: str, error_class: str, status_code) -> None:
        return None

    async def set_cooldown(self, endpoint_id: str, cooldown_until) -> None:
        return None


class StubQuotaState:
    async def get_quota_state(self, provider_id: str):
        return None

    async def update_quota_state(self, provider_id: str, snapshot) -> None:
        return None


class StubAttemptLog:
    def __init__(self) -> None:
        self.attempts: list[dict] = []

    async def record_attempt(self, **kwargs) -> str:
        self.attempts.append(kwargs)
        return f"attempt_{len(self.attempts)}"


class StubEndpointRegistry:
    def __init__(self, bindings: list[dict]) -> None:
        self.bindings = bindings

    async def list_endpoints_for_canonical_model(self, canonical_model_id: str) -> list[dict]:
        return self.bindings

    async def get_endpoint(self, endpoint_id: str):
        return next((b for b in self.bindings if b["endpoint_id"] == endpoint_id), None)


class StubProviderAdapter:
    """Controlled provider stub — non-certification tests only (A5 rule)."""

    def __init__(self, *, content: str = '{"ok": true}', error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls: list[tuple[ProviderRequest, str]] = []

    async def generate(self, request: ProviderRequest, model_id: str | None = None) -> ProviderResponse:
        self.calls.append((request, model_id or ""))
        if self.error is not None:
            raise self.error
        return ProviderResponse(
            provider_id="stub-provider",
            provider_model_id=model_id,
            content=self.content,
            finish_reason="stop",
            usage=ProviderUsage(prompt_tokens=11, completion_tokens=7),
        )


def _request(
    *,
    capability: str = "ideation",
    user: str = "hello",
    structured_output_schema: dict | None = None,
    **meta,
) -> ModelCompletionRequest:
    return ModelCompletionRequest(
        capability=capability,
        system="system",
        user=user,
        canonical_model="canonical/story",
        temperature=0.5,
        max_tokens=512,
        structured_output_schema=structured_output_schema,
        metadata={"prompt_id": "story.ideation.generate", **meta},
    )


def _build_port(*, stub: StubProviderAdapter | None = None, bindings: list[dict] | None = None) -> tuple[RouteLockedModelPort, RouteLockService, StubProviderAdapter, StubAttemptLog]:
    stub = stub or StubProviderAdapter()
    attempts = StubAttemptLog()
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: stub,
        endpoint_registry=StubEndpointRegistry(bindings or [BINDING]),
        endpoint_state=StubEndpointState(),
        quota_state=StubQuotaState(),
        attempt_log=attempts,
    )
    lock_service = RouteLockService(
        ruleset=build_studio_ruleset("canonical/story"),
        lock_repository=InMemoryLockStore(),
    )
    port = RouteLockedModelPort(lock_service, coordinator)
    return port, lock_service, stub, attempts


# ---------------------------------------------------------------------------
# Route-lock determinism + no silent model flip
# ---------------------------------------------------------------------------


async def test_same_scope_reuses_same_route_lock():
    port, lock_service, _, _ = _build_port()
    req = _request()
    receipt1 = await port.lock_route(req)
    receipt2 = await port.lock_route(req)
    assert receipt1.route_lock_id == receipt2.route_lock_id
    assert receipt1.canonical_model_id == "canonical/story"
    # Only one active lock exists for the scope.
    assert len(lock_service.snapshot()) == 1


async def test_different_capability_or_prompt_gets_distinct_lock():
    port, lock_service, _, _ = _build_port()
    a = await port.lock_route(_request(capability="ideation", user="one"))
    b = await port.lock_route(_request(capability="bibles", user="one"))
    c = await port.lock_route(_request(capability="ideation", user="two"))
    assert len({a.route_lock_id, b.route_lock_id, c.route_lock_id}) == 3
    assert len(lock_service.snapshot()) == 3


async def test_explicit_route_lock_id_wins_as_scope():
    port, lock_service, _, _ = _build_port()
    receipt = await port.lock_route(_request(route_lock_id="lock_task_42"))
    # The lock RECORD id is generated; the lock SCOPE must be the explicit id.
    snapshot = lock_service.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["scope_id"] == "lock_task_42"
    assert receipt.route_lock_id == snapshot[0]["lock_id"]


# ---------------------------------------------------------------------------
# Completion mapping + provenance
# ---------------------------------------------------------------------------


async def test_complete_maps_request_and_returns_provenance():
    port, _, stub, attempts = _build_port()
    output_schema = {"type": "object", "required": ["ok"]}
    result = await port.complete(
        _request(user="hello model", structured_output_schema=output_schema)
    )
    assert isinstance(result, ModelCompletionResult)
    assert result.provider == "stub-provider"
    assert result.content == '{"ok": true}'
    assert result.usage["prompt_tokens"] == 11
    assert result.usage["completion_tokens"] == 7
    assert result.usage["route_lock_id"]
    # ProviderRequest carried the story completion through the coordinator.
    (provider_request, model_id), = stub.calls
    assert isinstance(provider_request, ProviderRequest)
    assert provider_request.prompt == "hello model"
    assert provider_request.system_instruction == "system"
    assert provider_request.temperature == 0.5
    assert provider_request.max_tokens == 512
    assert provider_request.structured_output_schema == output_schema
    assert model_id == "stub-model-1"
    assert attempts.attempts and attempts.attempts[-1]["status"] == "success"


async def test_failover_stays_on_locked_canonical_model():
    stub = StubProviderAdapter(error=RateLimitFailure())
    port, _, _, attempts = _build_port(stub=stub, bindings=[BINDING])
    with pytest.raises((RateLimitFailure, SameModelEndpointExhausted)):
        await port.complete(_request())
    # The coordinator recorded the failed attempts under the route lock;
    # the locked canonical model never changed.
    assert attempts.attempts
    assert attempts.attempts[-1]["error_class"] == "RateLimitFailure"
    assert attempts.attempts[-1]["status"] == "rate_limited"


async def test_no_silent_fallback_when_endpoints_exhausted():
    stub = StubProviderAdapter(error=NetworkFailure())
    port, _, _, _ = _build_port(stub=stub, bindings=[BINDING])
    with pytest.raises((NetworkFailure, SameModelEndpointExhausted)):
        await port.complete(_request())


# ---------------------------------------------------------------------------
# Typed retryability taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "category", "retryable"),
    [
        (RateLimitFailure(), QUOTA, True),
        (QuotaExhaustedFailure(), QUOTA, False),
        (AuthenticationFailure(), AUTH, False),
        (PermissionFailure(), AUTH, False),
        (ContentPolicyFailure(), SAFETY, False),
        (InvalidRequestFailure(), SCHEMA, False),
        (ContextOverflowFailure(), SCHEMA, False),
        (ModelNotFoundFailure(), TERMINAL, False),
        (MalformedResponseFailure(), TERMINAL, False),
        (CancellationFailure(), TERMINAL, False),
        (SameModelEndpointExhausted(), TRANSIENT, True),
        (NetworkFailure(), TRANSIENT, True),
        (TimeoutFailure(), TRANSIENT, True),
        (ProviderUnavailableFailure(), TRANSIENT, True),
        (RuntimeError("boom"), UNKNOWN, False),
    ],
)
def test_failure_taxonomy_maps_to_typed_retryability(exc, category, retryable):
    cls = classify_provider_error(exc)
    assert cls.category == category
    assert cls.retryable is retryable


async def test_port_classify_passthrough():
    port, _, _, _ = _build_port()
    assert port.classify(AuthenticationFailure()).category == AUTH
    assert port.classify(NetworkFailure()).retryable is True


# ---------------------------------------------------------------------------
# Certification fixture guard
# ---------------------------------------------------------------------------


def test_real_port_is_not_a_fixture_provider():
    port, _, _, _ = _build_port()
    assert not is_fixture_provider(port)
    assert_not_fixture(port)  # must not raise


async def test_lock_route_rejects_disabled_model_fail_closed():
    from windagent_core.contracts.studio.story_roles import RoutingUnavailableError
    from windagent_providers.routing.route_lock_service import (
        RouteLockService as RLS,
    )

    port = RouteLockedModelPort(
        RLS(
            ruleset=build_studio_ruleset("canonical/story"),
            disabled_models={"canonical/story"},
        ),
        object(),  # never reached: lock fails first
    )
    # P0.3.4: a disabled canonical model is not a valid route -> typed
    # ROUTING_UNAVAILABLE instead of a raw matcher error.
    with pytest.raises(RoutingUnavailableError):
        await port.lock_route(_request())
