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
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from windagent_providers.base.contracts import ProviderRequest, ProviderResponse, ProviderStreamEvent
from windagent_providers.base.errors import (
    AuthenticationFailure,
    ProviderFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
)
from windagent_providers.base.ports import EndpointRegistryPort, EndpointStatePort, QuotaStatePort, RouteAttemptPort
from windagent_providers.routing.cooldown import apply_rate_limit_cooldown
from windagent_providers.routing.endpoint_selector import EndpointCandidate, EndpointSelector
from windagent_providers.routing.failover_policy import FailoverDecision, SameModelFailoverPolicy


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
    ):
        self._adapter_resolver = adapter_resolver
        self._registry = endpoint_registry
        self._state = endpoint_state
        self._quota = quota_state
        self._attempts = attempt_log
        self._selector = EndpointSelector(endpoint_state, quota_state)
        self._policy = failover_policy or SameModelFailoverPolicy()

    async def execute(
        self,
        request: ProviderRequest,
        route_lock: Any,
        turn_id: Optional[str] = None,
        *,
        max_attempts: int = 5,
    ) -> ProviderResponse:
        """
        Execute request on the canonical model of route_lock, failing over only
        to exact-equivalent endpoints.
        """
        canonical_model_id = _canonical_model_id(route_lock)
        route_lock_id = _route_lock_id(route_lock)

        for attempt_index in range(max_attempts):
            try:
                candidates = await self._selector.select_candidates(
                    await self._registry.list_endpoints_for_canonical_model(canonical_model_id)
                )
            except SameModelEndpointExhausted:
                raise

            candidate = candidates[0]
            adapter = self._adapter_resolver(candidate)

            start = time.perf_counter()
            try:
                response = await adapter.generate(request, model_id=candidate.provider_model_id)
                # Normalize canonical_model_id to the locked model.
                response.canonical_model_id = canonical_model_id
                response.endpoint_id = candidate.endpoint_id
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
                    await apply_rate_limit_cooldown(self._state, candidate.endpoint_id, exc)

                await self._record_attempt(
                    route_lock_id=route_lock_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    binding_id=candidate.binding_id,
                    status="rate_limited" if isinstance(exc, RateLimitFailure) else "failed",
                    http_status=getattr(exc, "status_code", None),
                    error_class=exc.__class__.__name__,
                    endpoint_id=candidate.endpoint_id,
                )

                if decision.decision == FailoverDecision.STOP:
                    raise

                # Otherwise continue loop and pick next candidate.

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

        for attempt_index in range(max_attempts):
            try:
                candidates = await self._selector.select_candidates(
                    await self._registry.list_endpoints_for_canonical_model(canonical_model_id)
                )
            except SameModelEndpointExhausted:
                yield _error_event("SameModelEndpointExhausted")
                return

            candidate = candidates[0]
            adapter = self._adapter_resolver(candidate)

            emitted = False
            start = time.perf_counter()
            try:
                async for event in adapter.stream(request, model_id=candidate.provider_model_id):
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
                    await apply_rate_limit_cooldown(self._state, candidate.endpoint_id, exc)

                await self._record_attempt(
                    route_lock_id=route_lock_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    binding_id=candidate.binding_id,
                    status="rate_limited" if isinstance(exc, RateLimitFailure) else "failed",
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
