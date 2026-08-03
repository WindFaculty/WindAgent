"""
Execution Coordinator for WindAgent Provider Routing Phase 8.

Executes a ProviderRequest against exact-equivalent endpoint bindings of a locked
canonical model, applying same-model failover when an endpoint returns 429, 5xx,
network/timeout errors, auth failures, or model-not-found.  Preserves the route
lock's canonical model across all attempts and records every attempt.

Usage::

    coordinator = EndpointExecutionCoordinator(adapter_resolver, registry, state, quota, attempts)
    response = await coordinator.execute(request, route_lock, turn_id="turn-1")
"""

from __future__ import annotations

import time
import uuid
from typing import Any, AsyncIterator, Callable, Optional

from windagent_providers.base.contracts import (
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
)
from windagent_providers.base.errors import (
    NetworkFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
    TimeoutFailure,
)
from windagent_core.contracts.providers.ports import (
    EndpointRegistryPort,
    EndpointStatePort,
    QuotaStatePort,
    RouteAttemptPort,
)
from windagent_providers.cache.contracts import CacheNamespace
from windagent_providers.cache.response_cache import ResponseCacheService
from windagent_providers.cache.singleflight import InMemorySingleFlight
from windagent_providers.routing.cooldown import (
    apply_rate_limit_cooldown,
    apply_transient_failure_cooldown,
)
from windagent_providers.routing.endpoint_selector import EndpointSelector
from windagent_providers.routing.failover_policy import (
    FailoverDecision,
    SameModelFailoverPolicy,
)


AdapterResolver = Callable[[str], Any]


class EndpointExecutionCoordinator:
    """Phase 8 execution coordinator: same-model endpoint failover with audit."""

    def __init__(
        self,
        adapter_resolver: AdapterResolver,
        endpoint_registry: EndpointRegistryPort,
        endpoint_state: EndpointStatePort,
        quota_state: QuotaStatePort,
        attempt_log: RouteAttemptPort,
        failover_policy: Optional[SameModelFailoverPolicy] = None,
        response_cache: Optional[ResponseCacheService] = None,
        singleflight: Optional[InMemorySingleFlight] = None,
        release_telemetry: Any | None = None,
    ):
        self._adapter_resolver = adapter_resolver
        self._registry = endpoint_registry
        self._state = endpoint_state
        self._quota = quota_state
        self._attempts = attempt_log
        self._selector = EndpointSelector(endpoint_state, quota_state)
        self._policy = failover_policy or SameModelFailoverPolicy()
        self._response_cache = response_cache
        self._singleflight = singleflight
        self._release_telemetry = release_telemetry

    async def execute(
        self,
        request: ProviderRequest,
        route_lock: Any,
        turn_id: Optional[str] = None,
        *,
        namespace: Optional[CacheNamespace] = None,
        max_attempts: int = 5,
    ) -> ProviderResponse:
        """
        Execute request on the canonical model of route_lock, failing over only
        to exact-equivalent endpoints.

        If a response_cache is configured and the request is cacheable, a cache
        hit short-circuits execution.  Otherwise a singleflight keyed by the
        cache key collapses concurrent identical requests.
        """
        canonical_model_id = _canonical_model_id(route_lock)
        route_lock_id = _route_lock_id(route_lock)
        cache_key: Optional[str] = None
        if self._release_telemetry is not None:
            self._release_telemetry.record_route_request()

        # Phase 9: response cache short-circuit.
        if self._response_cache is not None and namespace is not None:
            cache_result = await self._response_cache.get(
                request,
                namespace,
                canonical_model_id,
                explicit_opt_in=False,
            )
            cache_key = cache_result.cache_key
            if cache_result.hit and cache_result.response is not None:
                return cache_result.response

        if self._singleflight is not None and cache_key is not None:
            return await self._singleflight.do(
                cache_key,
                lambda: self._execute_once(
                    request,
                    canonical_model_id,
                    route_lock_id,
                    turn_id,
                    namespace,
                    cache_key,
                    max_attempts,
                ),
            )

        return await self._execute_once(
            request,
            canonical_model_id,
            route_lock_id,
            turn_id,
            namespace,
            cache_key,
            max_attempts,
        )

    async def _execute_once(
        self,
        request: ProviderRequest,
        canonical_model_id: str,
        route_lock_id: str,
        turn_id: Optional[str],
        namespace: Optional[CacheNamespace],
        cache_key: Optional[str],
        max_attempts: int,
    ) -> ProviderResponse:
        for attempt_index in range(max_attempts):
            try:
                candidates = await self._selector.select_candidates(
                    await self._registry.list_endpoints_for_canonical_model(
                        canonical_model_id
                    )
                )
            except SameModelEndpointExhausted:
                raise

            candidate = candidates[0]
            start = time.perf_counter()
            try:
                adapter = self._adapter_resolver(candidate)
                response = await adapter.generate(
                    request, model_id=candidate.provider_model_id
                )
                # Normalize canonical_model_id to the locked model.
                response.canonical_model_id = canonical_model_id
                response.endpoint_id = candidate.endpoint_id
                response.raw_metadata = {
                    **response.raw_metadata,
                    "route_lock_id": route_lock_id,
                    "provider_binding_id": candidate.binding_id,
                }
                latency_ms = (time.perf_counter() - start) * 1000.0

                await self._state.record_success(candidate.endpoint_id, latency_ms)
                await self._record_attempt(
                    route_lock_id=route_lock_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    binding_id=candidate.binding_id,
                    status="success",
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    endpoint_id=candidate.endpoint_id,
                )
                # Phase 9: write through to response cache.
                if (
                    self._response_cache is not None
                    and namespace is not None
                    and cache_key is not None
                ):
                    await self._response_cache.set(
                        request,
                        namespace,
                        canonical_model_id,
                        response,
                    )
                return response

            except ProviderFailure as exc:
                latency_ms = (time.perf_counter() - start) * 1000.0
                decision = self._policy.classify(exc, attempt_index=0)

                await self._state.record_failure(
                    candidate.endpoint_id,
                    exc.__class__.__name__,
                    getattr(exc, "status_code", None),
                )

                if isinstance(exc, RateLimitFailure):
                    await apply_rate_limit_cooldown(
                        self._state, candidate.endpoint_id, exc
                    )
                elif isinstance(
                    exc,
                    (ProviderUnavailableFailure, NetworkFailure, TimeoutFailure),
                ):
                    await apply_transient_failure_cooldown(
                        self._state,
                        candidate.endpoint_id,
                        exc,
                        attempt_index=attempt_index,
                    )

                await self._record_attempt(
                    route_lock_id=route_lock_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    binding_id=candidate.binding_id,
                    status="rate_limited"
                    if isinstance(exc, RateLimitFailure)
                    else "failed",
                    http_status=getattr(exc, "status_code", None),
                    error_class=exc.__class__.__name__,
                    endpoint_id=candidate.endpoint_id,
                )

                if decision.decision == FailoverDecision.STOP:
                    raise

                # Otherwise continue loop and pick next candidate.
                if self._release_telemetry is not None:
                    self._release_telemetry.record_route_failover()

        raise SameModelEndpointExhausted(
            "All exact-equivalent endpoints for the locked canonical model are exhausted"
        )

    async def execute_stream(
        self,
        request: ProviderRequest,
        route_lock: Any,
        turn_id: Optional[str] = None,
        *,
        max_attempts: int = 5,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """
        Streaming execution with same-model failover.

        If the initial endpoint succeeds at transport level, the stream proceeds.
        If the initial endpoint fails before emitting tokens, failover to another
        exact-equivalent endpoint is attempted.  Already-emitted tokens are never
        silently stitched to a new endpoint; a failure mid-stream emits an error
        event and stops.
        """
        canonical_model_id = _canonical_model_id(route_lock)
        route_lock_id = _route_lock_id(route_lock)
        if self._release_telemetry is not None:
            self._release_telemetry.record_route_request()

        for attempt_index in range(max_attempts):
            try:
                candidates = await self._selector.select_candidates(
                    await self._registry.list_endpoints_for_canonical_model(
                        canonical_model_id
                    )
                )
            except SameModelEndpointExhausted:
                yield _error_event("SameModelEndpointExhausted")
                return

            candidate = candidates[0]
            adapter = self._adapter_resolver(candidate)

            emitted = False
            start = time.perf_counter()
            try:
                async for event in adapter.stream(
                    request, model_id=candidate.provider_model_id
                ):
                    emitted = True
                    yield event

                latency_ms = (time.perf_counter() - start) * 1000.0
                await self._state.record_success(candidate.endpoint_id, latency_ms)
                await self._record_attempt(
                    route_lock_id=route_lock_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    binding_id=candidate.binding_id,
                    status="success",
                    endpoint_id=candidate.endpoint_id,
                )
                return

            except ProviderFailure as exc:
                latency_ms = (time.perf_counter() - start) * 1000.0
                decision = self._policy.classify(exc, attempt_index=0)

                await self._state.record_failure(
                    candidate.endpoint_id,
                    exc.__class__.__name__,
                    getattr(exc, "status_code", None),
                )

                if isinstance(exc, RateLimitFailure):
                    await apply_rate_limit_cooldown(
                        self._state, candidate.endpoint_id, exc
                    )
                elif isinstance(
                    exc,
                    (ProviderUnavailableFailure, NetworkFailure, TimeoutFailure),
                ):
                    await apply_transient_failure_cooldown(
                        self._state,
                        candidate.endpoint_id,
                        exc,
                        attempt_index=attempt_index,
                    )

                await self._record_attempt(
                    route_lock_id=route_lock_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    binding_id=candidate.binding_id,
                    status="rate_limited"
                    if isinstance(exc, RateLimitFailure)
                    else "failed",
                    http_status=getattr(exc, "status_code", None),
                    error_class=exc.__class__.__name__,
                    endpoint_id=candidate.endpoint_id,
                )

                if emitted:
                    # Partial stream failure: emit error event; do not silently re-stream.
                    yield _error_event(exc.__class__.__name__)
                    return

                if decision.decision == FailoverDecision.STOP:
                    yield _error_event(exc.__class__.__name__)
                    return
                if self._release_telemetry is not None:
                    self._release_telemetry.record_route_failover()

                # Otherwise failover.

        yield _error_event("SameModelEndpointExhausted")

    async def _record_attempt(
        self,
        *,
        route_lock_id: str,
        turn_id: Optional[str],
        attempt_index: int,
        binding_id: Optional[str],
        endpoint_id: str,
        status: str,
        http_status: Optional[int] = None,
        error_class: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        await self._attempts.record_attempt(
            route_lock_id=route_lock_id,
            turn_id=turn_id,
            attempt_index=attempt_index,
            provider_binding_id=binding_id,
            status=status,
            http_status=http_status,
            error_class=error_class,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            endpoint_id=endpoint_id,
        )


def _canonical_model_id(route_lock: Any) -> str:
    if isinstance(route_lock, dict):
        return route_lock["canonical_model_id"]
    return route_lock.canonical_model_id


def _route_lock_id(route_lock: Any) -> str:
    if isinstance(route_lock, dict):
        return route_lock.get("lock_id", str(uuid.uuid4()))
    return getattr(route_lock, "lock_id", str(uuid.uuid4()))


def _error_event(error_class_name: str) -> ProviderStreamEvent:
    return ProviderStreamEvent(
        event_type="error",
        sequence_number=0,
        error=error_class_name,
    )
