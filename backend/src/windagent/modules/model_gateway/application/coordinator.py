"""Endpoint execution coordinator: the failover loop.

REWRITE of the frozen ``routing/execution_coordinator.py``.  Preserved
semantics: candidates are re-selected every attempt, the default budget is
five attempts, rate-limit failures cool an endpoint down by its parsed
``Retry-After`` (ceiling 300s), transient failures cool it by the bounded
exponential backoff, STOP decisions re-raise, and an exhausted budget raises
``SameModelEndpointExhausted``.  Streaming fails over only before the first
token — mid-stream failures emit an error event instead of stitching streams.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from windagent.kernel.time import Clock, SystemClock, utc_now
from windagent.platform.observability import Telemetry
from windagent.platform.security import SecretStore

from ..domain.circuit import CircuitBreakerPolicy
from ..domain.cooldown import calculate_backoff_cooldown_seconds, rate_limit_cooldown_seconds
from ..domain.errors import (
    NetworkFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
    TimeoutFailure,
)
from ..domain.failover import AttemptPolicy, FailoverDecision, SameModelFailoverPolicy
from ..domain.route_lock import RouteLockRecord
from ..domain.selection import EndpointCandidate
from ..providers.contracts import (
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderUsage,
    StreamEventType,
)
from .models import AttemptRow
from .ports import AdapterFactory, TransactionScope
from .selector import EndpointSelector

DEFAULT_MAX_ATTEMPTS = 5

TRANSIENT_KINDS = frozenset(
    {
        ProviderUnavailableFailure.kind,
        NetworkFailure.kind,
        TimeoutFailure.kind,
    }
)


@dataclass(frozen=True, slots=True)
class ModelCompletionResult:
    """One successful invocation with its complete routing provenance."""

    response: ProviderResponse
    canonical_model_id: str
    route_lock_id: str
    rule_id: str
    rule_version: int
    provider_name: str
    provider_model_id: str
    endpoint_id: str
    binding_id: str
    attempts: int
    fallback_used: bool = False
    fallback_reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport and job results."""
        return {
            "canonical_model_id": self.canonical_model_id,
            "route_lock_id": self.route_lock_id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "provider_name": self.provider_name,
            "provider_model_id": self.provider_model_id,
            "endpoint_id": self.endpoint_id,
            "binding_id": self.binding_id,
            "attempts": self.attempts,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "finish_reason": self.response.finish_reason,
            "text": self.response.text,
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in self.response.tool_calls
            ],
            "usage": {
                "prompt_tokens": self.response.usage.prompt_tokens,
                "completion_tokens": self.response.usage.completion_tokens,
                "cached_tokens": self.response.usage.cached_tokens,
                "reasoning_tokens": self.response.usage.reasoning_tokens,
                "total_tokens": self.response.usage.total_tokens,
            },
            "total_latency_ms": self.response.total_latency_ms,
        }


class EndpointExecutionCoordinator:
    """Executes one locked request across exact-equivalent endpoints."""

    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        secrets: SecretStore,
        adapter_factory: AdapterFactory,
        selector: EndpointSelector,
        clock: Clock | None = None,
        failover_policy: SameModelFailoverPolicy | None = None,
        circuit_policy: CircuitBreakerPolicy | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._secrets = secrets
        self._adapter_factory = adapter_factory
        self._selector = selector
        self._clock: Clock = clock or SystemClock()
        self._failover = failover_policy or SameModelFailoverPolicy()
        self._circuit_policy = circuit_policy or CircuitBreakerPolicy()
        self._telemetry = telemetry

    async def execute(
        self,
        request: ProviderRequest,
        *,
        lock: RouteLockRecord,
        task_id: str,
        role: str | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> ModelCompletionResult:
        """Run the failover loop until a response or a terminal failure."""
        attempt_index = 0
        last_failure: ProviderFailure | None = None
        while attempt_index < max_attempts:
            candidate = await self._top_candidate(lock.canonical_model_id)
            adapter = await self._adapter_for(candidate)
            attempt_started = self._clock.now()
            try:
                response = await adapter.generate(request, candidate.provider_model_id)
            except ProviderFailure as failure:
                await self._record_failure(
                    lock, candidate, attempt_index, failure, attempt_started
                )
                policy: AttemptPolicy = self._failover.classify(failure, attempt_index)
                if policy.decision is FailoverDecision.STOP:
                    raise
                last_failure = failure
                attempt_index += 1
                continue

            await self._record_success(
                lock, candidate, response.usage, attempt_index, attempt_started
            )
            return ModelCompletionResult(
                response=response,
                canonical_model_id=lock.canonical_model_id,
                route_lock_id=lock.lock_id,
                rule_id=lock.routing_snapshot.rule_id,
                rule_version=lock.routing_snapshot.rule_version,
                provider_name=candidate.provider_name,
                provider_model_id=candidate.provider_model_id,
                endpoint_id=candidate.endpoint_id,
                binding_id=candidate.binding_id,
                attempts=attempt_index + 1,
            )

        raise SameModelEndpointExhausted(
            "All exact-equivalent endpoints for the locked canonical model are exhausted",
            context={
                "canonical_model_id": lock.canonical_model_id,
                "attempts": attempt_index,
                "last_error_kind": last_failure.kind if last_failure else None,
            },
        )

    async def execute_stream(
        self,
        request: ProviderRequest,
        *,
        lock: RouteLockRecord,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Stream with same-model failover before the first token only."""
        attempt_index = 0
        while attempt_index < max_attempts:
            candidate = await self._top_candidate(lock.canonical_model_id)
            adapter = await self._adapter_for(candidate)
            attempt_started = self._clock.now()
            emitted = False
            final_usage: ProviderUsage | None = None
            try:
                async for event in adapter.stream(request, candidate.provider_model_id):
                    if event.event_type is StreamEventType.DONE:
                        final_usage = event.usage
                    emitted = True
                    yield event
            except ProviderFailure as failure:
                await self._record_failure(
                    lock, candidate, attempt_index, failure, attempt_started
                )
                policy = self._failover.classify(failure, attempt_index)
                if emitted or policy.decision is FailoverDecision.STOP:
                    # Mid-stream failures never stitch a second stream.
                    yield ProviderStreamEvent(
                        event_type=StreamEventType.ERROR,
                        error=failure.message,
                    )
                    return
                attempt_index += 1
                continue

            await self._record_success(
                lock,
                candidate,
                final_usage or ProviderUsage(),
                attempt_index,
                attempt_started,
            )
            return
        raise SameModelEndpointExhausted(
            "All exact-equivalent endpoints for the locked canonical model are exhausted",
            context={
                "canonical_model_id": lock.canonical_model_id,
                "attempts": attempt_index,
            },
        )

    # ------------------------------------------------------------------ #

    async def _top_candidate(self, canonical_model_id: str) -> EndpointCandidate:
        """Re-select candidates each attempt and take the best survivor."""
        async with self._scope_factory() as scope:
            candidates = await self._selector.select(
                scope.store(), canonical_model_id, now=self._clock.now()
            )
        return candidates[0]

    async def _adapter_for(
        self, candidate: EndpointCandidate
    ) -> ProviderAdapter:
        """Resolve the adapter, revealing the credential at this boundary."""
        api_key: str | None = None
        if candidate.credential_reference:
            secret = await self._secrets.read(candidate.credential_reference)
            api_key = secret.reveal() if secret is not None else None
        return self._adapter_factory.resolve(
            candidate.protocol_mode,
            base_url=candidate.base_url,
            api_key=api_key,
        )

    async def _record_success(
        self,
        lock: RouteLockRecord,
        candidate: EndpointCandidate,
        usage: ProviderUsage,
        attempt_index: int,
        attempt_started: datetime,
    ) -> None:
        """Persist the success to endpoint state and the attempt log."""
        now = self._clock.now()
        async with self._scope_factory() as scope:
            store = scope.store()
            state = await store.get_endpoint_state(candidate.endpoint_id)
            latency_ms = (now - attempt_started).total_seconds() * 1000.0
            await store.save_endpoint_state(
                candidate.endpoint_id,
                self._circuit_policy.after_success(state, now, latency_ms),
            )
            await store.insert_attempt(
                AttemptRow(
                    id=f"att-{now.timestamp():.0f}-{candidate.endpoint_id}-{attempt_index}",
                    route_lock_id=lock.lock_id,
                    endpoint_id=candidate.endpoint_id,
                    binding_id=candidate.binding_id,
                    attempt_index=attempt_index,
                    status="success",
                    started_at=attempt_started,
                    finished_at=now,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    latency_ms=latency_ms,
                )
            )
            await scope.commit()

    async def _record_failure(
        self,
        lock: RouteLockRecord,
        candidate: EndpointCandidate,
        attempt_index: int,
        failure: ProviderFailure,
        attempt_started: datetime,
    ) -> None:
        """Record the failure, applying cooldowns exactly like the old loop."""
        now = self._clock.now()
        cooldown_until = None
        if isinstance(failure, RateLimitFailure):
            retry_after = failure.context.get("retry_after")
            seconds = (
                rate_limit_cooldown_seconds({"retry-after": str(retry_after)})
                if isinstance(retry_after, (int, float))
                else rate_limit_cooldown_seconds(None)
            )
            cooldown_until = now + timedelta(seconds=seconds)
        elif failure.kind in TRANSIENT_KINDS:
            seconds = calculate_backoff_cooldown_seconds(attempt_index)
            cooldown_until = now + timedelta(seconds=seconds)

        async with self._scope_factory() as scope:
            store = scope.store()
            state = await store.get_endpoint_state(candidate.endpoint_id)
            await store.save_endpoint_state(
                candidate.endpoint_id,
                self._circuit_policy.after_failure(
                    state,
                    now,
                    error_class=failure.kind,
                    cooldown_until=cooldown_until,
                ),
            )
            latency_ms = (now - attempt_started).total_seconds() * 1000.0
            await store.insert_attempt(
                AttemptRow(
                    id=f"att-{now.timestamp():.0f}-{candidate.endpoint_id}-{attempt_index}",
                    route_lock_id=lock.lock_id,
                    endpoint_id=candidate.endpoint_id,
                    binding_id=candidate.binding_id,
                    attempt_index=attempt_index,
                    status="failed",
                    error_class=failure.kind,
                    http_status=failure.status_code,
                    started_at=attempt_started,
                    finished_at=utc_now(),
                    latency_ms=latency_ms,
                )
            )
            await scope.commit()
