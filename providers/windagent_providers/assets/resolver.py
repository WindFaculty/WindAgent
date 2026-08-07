"""
AssetResolver — Universal Asset Gateway (VP3D Phase 5).

Implements ``AssetResolverPort`` over ``AssetAdapterRegistry``:

1. CAPABILITY MATCHING first — a provider that cannot serve the requirement is
   a typed rejection and is never called;
2. IDEMPOTENCY cache lookup — canonical requirement + adapter/version is looked
   up before any network or generation call;
3. DISCOVER then ACQUIRE — candidates are DISCOVERED only, never usable;
4. EXECUTION POLICY — timeout, retry budget, circuit breaker, cancellation,
   per-provider concurrency;
5. CREDENTIAL-FREE receipts — any credential-like payload raises
   ``SecretLeakError`` before acceptance.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from windagent_core.domain.video_production.asset_resolution import (
    AssetCandidate,
    AssetProviderCapability,
    AssetResolutionAttempt,
    AssetResolutionRequest,
    AssetResolutionResult,
    AssetResolutionStatus,
    AssetResolutionError,
    CapabilityRejectedError,
    NoCapableAdapterError,
    ProviderTimeoutError,
    RetryBudgetExhaustedError,
    ResolutionCancelledError,
)
from windagent_core.domain.video_production.asset_resolution.models import utc_now
from windagent_core.domain.video_production.ids import AssetResolutionId

from windagent_providers.assets.adapter import AssetAdapter
from windagent_providers.assets.cache import AssetResolutionCache
from windagent_providers.assets.capability import CapabilityMatcher
from windagent_providers.assets.execution import (
    CancellationScope,
    CircuitBreaker,
    ExecutionOutcome,
    ExecutionPolicy,
    execute_with_policy,
)
from windagent_providers.assets.redaction import assert_no_credentials
from windagent_providers.assets.registry import AssetAdapterRegistry


def _make_resolution_id() -> AssetResolutionId:
    return AssetResolutionId.generate("ast_res")


class AssetResolver:
    """Gateway orchestrating discovery/acquire across asset adapters."""

    def __init__(
        self,
        registry: AssetAdapterRegistry,
        *,
        cache: Optional[AssetResolutionCache] = None,
        policy: Optional[ExecutionPolicy] = None,
        matcher: Optional[CapabilityMatcher] = None,
    ) -> None:
        self._registry = registry
        self._cache = cache or AssetResolutionCache()
        self._policy = policy or ExecutionPolicy()
        self._matcher = matcher or CapabilityMatcher()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}

    # ------------------------------------------------------------------
    # AssetResolverPort surface
    # ------------------------------------------------------------------

    def capabilities(self) -> List[AssetProviderCapability]:
        return self._registry.capabilities()

    async def discover(
        self,
        request: AssetResolutionRequest,
        *,
        scope: Optional[CancellationScope] = None,
    ) -> AssetResolutionResult:
        started = time.monotonic()
        assert_no_credentials(request.metadata, context="AssetResolutionRequest.metadata")
        cancel = scope or CancellationScope()
        requirement_hash = request.requirement.canonical_hash

        adapters, plan_attempts = self._plan_adapters(request)
        attempts = list(plan_attempts)
        exec_attempts: List[AssetResolutionAttempt] = []
        results: Dict[str, tuple[List[AssetCandidate], bool]] = {}
        try:
            await asyncio.gather(
                *[
                    self._run_discover(adapter, request, cancel, results, exec_attempts)
                    for adapter in adapters
                ],
                return_exceptions=False,
            )
        except (ResolutionCancelledError, asyncio.CancelledError):
            duration_ms = int((time.monotonic() - started) * 1000)
            return AssetResolutionResult(
                resolution_id=_make_resolution_id(),
                requirement_hash=requirement_hash,
                status=AssetResolutionStatus.CANCELLED,
                candidates=[],
                attempts=exec_attempts + self._compact_attempts(attempts, results, cancelled=True),
                cache_hit=False,
                duration_ms=duration_ms,
            )

        candidates: List[AssetCandidate] = []
        for adapter in adapters:
            found, _ = results.get(adapter.adapter_id, ([], False))
            candidates.extend(found)

        duration_ms = int((time.monotonic() - started) * 1000)
        attempts = exec_attempts + self._compact_attempts(attempts, results)
        if candidates:
            status = AssetResolutionStatus.DISCOVERED
        elif any(a.error_code for a in attempts):
            statuses = {a.status for a in attempts}
            if AssetResolutionStatus.TIMEOUT in statuses:
                status = AssetResolutionStatus.TIMEOUT
            elif AssetResolutionStatus.CANCELLED in statuses:
                status = AssetResolutionStatus.CANCELLED
            else:
                status = AssetResolutionStatus.REJECTED
        else:
            status = AssetResolutionStatus.NOT_FOUND

        return AssetResolutionResult(
            resolution_id=_make_resolution_id(),
            requirement_hash=requirement_hash,
            status=status,
            candidates=candidates,
            attempts=attempts,
            cache_hit=any(a.cache_hit for a in attempts),
            duration_ms=duration_ms,
        )

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
        *,
        scope: Optional[CancellationScope] = None,
    ) -> AssetResolutionResult:
        started = time.monotonic()
        assert_no_credentials(request.metadata, context="AssetResolutionRequest.metadata")
        cancel = scope or CancellationScope()
        requirement_hash = request.requirement.canonical_hash

        if candidate.requirement_hash != requirement_hash:
            return AssetResolutionResult(
                resolution_id=_make_resolution_id(),
                requirement_hash=requirement_hash,
                status=AssetResolutionStatus.REJECTED,
                attempts=[
                    AssetResolutionAttempt(
                        provider_id=candidate.provider_id,
                        adapter_version=candidate.adapter_version,
                        status=AssetResolutionStatus.REJECTED,
                        error_code=NoCapableAdapterError.code,
                        error_message="candidate requirement hash does not match request",
                    )
                ],
                cache_hit=False,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        adapter = self._registry.get(candidate.provider_id)
        if adapter is None:
            return self._rejected_result(
                requirement_hash,
                NoCapableAdapterError(
                    f"No adapter registered for provider {candidate.provider_id!r}."
                ),
                provider_id=candidate.provider_id,
                adapter_version=candidate.adapter_version,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        match = self._matcher.match(request.requirement, adapter.capability())
        if not match.matched:
            return self._rejected_result(
                requirement_hash,
                CapabilityRejectedError(adapter.adapter_id, match.rejection_reasons),
                provider_id=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        cache_key = request.requirement.cache_key(
            adapter.adapter_id, adapter.adapter_version
        )
        cached = self._cache.get(cache_key)
        if cached is not None and cached.acquired is not None:
            result = cached.model_copy(
                update={
                    "resolution_id": _make_resolution_id(),
                    "cache_hit": True,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                }
            )
            return result

        outcome = await execute_with_policy(
            adapter.adapter_id,
            lambda: adapter.acquire(candidate, request),
            policy=self._policy,
            breaker=self._breaker(adapter.adapter_id),
            scope=cancel,
            semaphore=self._semaphore(adapter.adapter_id),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        if outcome.ok:
            acquired = outcome.value
            result = AssetResolutionResult(
                resolution_id=_make_resolution_id(),
                requirement_hash=requirement_hash,
                status=AssetResolutionStatus.RESOLVED,
                acquired=acquired.asset,
                acquisition=acquired.acquisition,
                attempts=[
                    AssetResolutionAttempt(
                        provider_id=adapter.adapter_id,
                        adapter_version=adapter.adapter_version,
                        status=AssetResolutionStatus.RESOLVED,
                        started_at=utc_now(),
                        duration_ms=outcome.duration_ms,
                    )
                ],
                provider_id=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
                cache_hit=False,
                duration_ms=duration_ms,
            )
            self._cache.put(cache_key, result)
            return result

        return self._failed_result(
            requirement_hash,
            outcome,
            provider_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _plan_adapters(
        self, request: AssetResolutionRequest
    ) -> tuple[List[AssetAdapter], List[AssetResolutionAttempt]]:
        """Capability-match and order adapters; reject incapable ones typed."""
        attempts: List[AssetResolutionAttempt] = []
        if request.adapter_ids:
            adapters: List[AssetAdapter] = []
            for adapter_id in request.adapter_ids:
                adapter = self._registry.get(adapter_id)
                if adapter is None:
                    attempts.append(
                        self._attempt(
                            adapter_id,
                            "0.0.0",
                            AssetResolutionStatus.REJECTED,
                            NoCapableAdapterError.code,
                            f"unknown adapter id {adapter_id!r}",
                        )
                    )
                    continue
                match = self._matcher.match(request.requirement, adapter.capability())
                if not match.matched:
                    attempts.append(
                        self._attempt(
                            adapter.adapter_id,
                            adapter.adapter_version,
                            AssetResolutionStatus.REJECTED,
                            CapabilityRejectedError.code,
                            "; ".join(match.rejection_reasons),
                        )
                    )
                    continue
                adapters.append(adapter)
            return adapters, attempts

        capable = []
        for adapter in self._registry.list():
            match = self._matcher.match(request.requirement, adapter.capability())
            if match.matched:
                capable.append(adapter)
            else:
                attempts.append(
                    self._attempt(
                        adapter.adapter_id,
                        adapter.adapter_version,
                        AssetResolutionStatus.REJECTED,
                        CapabilityRejectedError.code,
                        "; ".join(match.rejection_reasons),
                    )
                )
        return capable, attempts

    async def _run_discover(
        self,
        adapter: AssetAdapter,
        request: AssetResolutionRequest,
        scope: CancellationScope,
        results: Dict[str, tuple[List[AssetCandidate], bool]],
        exec_attempts: List[AssetResolutionAttempt],
    ) -> None:
        cache_key = request.requirement.cache_key(
            adapter.adapter_id, adapter.adapter_version
        )
        cached = self._cache.get(cache_key)
        if cached is not None and cached.status == AssetResolutionStatus.DISCOVERED:
            results[adapter.adapter_id] = (list(cached.candidates), True)
            return

        outcome = await execute_with_policy(
            adapter.adapter_id,
            lambda: adapter.discover(request),
            policy=self._policy,
            breaker=self._breaker(adapter.adapter_id),
            scope=scope,
            semaphore=self._semaphore(adapter.adapter_id),
        )
        if not outcome.ok:
            if isinstance(outcome.error, ResolutionCancelledError):
                status = AssetResolutionStatus.CANCELLED
            elif isinstance(outcome.error, ProviderTimeoutError):
                status = AssetResolutionStatus.TIMEOUT
            elif outcome.error is not None and not outcome.error.retryable:
                status = AssetResolutionStatus.REJECTED
            else:
                status = AssetResolutionStatus.FAILED
            exec_attempts.append(
                AssetResolutionAttempt(
                    provider_id=adapter.adapter_id,
                    adapter_version=adapter.adapter_version,
                    status=status,
                    error_code=outcome.error_code(),
                    error_message=outcome.error_message(),
                )
            )
            return
        found = list(outcome.value or [])
        if found:
            self._cache.put(
                cache_key,
                AssetResolutionResult(
                    resolution_id=_make_resolution_id(),
                    requirement_hash=request.requirement.canonical_hash,
                    status=AssetResolutionStatus.DISCOVERED,
                    candidates=found,
                    provider_id=adapter.adapter_id,
                    adapter_version=adapter.adapter_version,
                    cache_hit=False,
                ),
            )
        results[adapter.adapter_id] = (found, False)

    def _compact_attempts(
        self,
        planned: List[AssetResolutionAttempt],
        results: Dict[str, tuple[List[AssetCandidate], bool]],
        *,
        cancelled: bool = False,
    ) -> List[AssetResolutionAttempt]:
        """Merge planned (rejection) attempts with executed outcomes."""
        attempts = list(planned)
        for adapter in self._registry.list():
            if any(a.provider_id == adapter.adapter_id for a in attempts):
                continue
            found, cache_hit = results.get(adapter.adapter_id, ([], False))
            if found is not None and not cache_hit and found:
                attempts.append(
                    AssetResolutionAttempt(
                        provider_id=adapter.adapter_id,
                        adapter_version=adapter.adapter_version,
                        status=AssetResolutionStatus.DISCOVERED,
                        candidates_found=len(found),
                    )
                )
            elif found is not None and cache_hit:
                attempts.append(
                    AssetResolutionAttempt(
                        provider_id=adapter.adapter_id,
                        adapter_version=adapter.adapter_version,
                        status=AssetResolutionStatus.DISCOVERED,
                        candidates_found=len(found),
                        cache_hit=True,
                    )
                )
            elif cancelled:
                attempts.append(
                    self._attempt(
                        adapter.adapter_id,
                        adapter.adapter_version,
                        AssetResolutionStatus.CANCELLED,
                        ResolutionCancelledError.code,
                        "cancelled before completion",
                    )
                )
        return attempts

    def _failed_result(
        self,
        requirement_hash: str,
        outcome: ExecutionOutcome,
        *,
        provider_id: str,
        adapter_version: str,
        duration_ms: int,
    ) -> AssetResolutionResult:
        error = outcome.error
        if isinstance(error, ResolutionCancelledError):
            status = AssetResolutionStatus.CANCELLED
        elif isinstance(error, ProviderTimeoutError):
            status = AssetResolutionStatus.TIMEOUT
        elif isinstance(error, RetryBudgetExhaustedError):
            status = AssetResolutionStatus.TIMEOUT
        elif error is not None and not error.retryable:
            status = AssetResolutionStatus.REJECTED
        else:
            status = AssetResolutionStatus.FAILED
        return AssetResolutionResult(
            resolution_id=_make_resolution_id(),
            requirement_hash=requirement_hash,
            status=status,
            attempts=[
                AssetResolutionAttempt(
                    provider_id=provider_id,
                    adapter_version=adapter_version,
                    status=status,
                    error_code=outcome.error_code(),
                    error_message=outcome.error_message(),
                )
            ],
            provider_id=provider_id,
            adapter_version=adapter_version,
            cache_hit=False,
            duration_ms=duration_ms,
        )

    def _rejected_result(
        self,
        requirement_hash: str,
        error: AssetResolutionError,
        *,
        provider_id: str,
        adapter_version: str,
        duration_ms: int,
    ) -> AssetResolutionResult:
        return AssetResolutionResult(
            resolution_id=_make_resolution_id(),
            requirement_hash=requirement_hash,
            status=AssetResolutionStatus.REJECTED,
            attempts=[
                self._attempt(
                    provider_id,
                    adapter_version,
                    AssetResolutionStatus.REJECTED,
                    error.code,
                    str(error),
                )
            ],
            provider_id=provider_id,
            adapter_version=adapter_version,
            cache_hit=False,
            duration_ms=duration_ms,
        )

    def _breaker(self, adapter_id: str) -> CircuitBreaker:
        breaker = self._breakers.get(adapter_id)
        if breaker is None:
            breaker = CircuitBreaker(adapter_id=adapter_id)
            self._breakers[adapter_id] = breaker
        return breaker

    def _semaphore(self, adapter_id: str) -> asyncio.Semaphore:
        semaphore = self._semaphores.get(adapter_id)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._policy.per_provider_concurrency)
            self._semaphores[adapter_id] = semaphore
        return semaphore

    @staticmethod
    def _attempt(
        provider_id: str,
        adapter_version: str,
        status: AssetResolutionStatus,
        error_code: Optional[str],
        error_message: str,
    ) -> AssetResolutionAttempt:
        return AssetResolutionAttempt(
            provider_id=provider_id,
            adapter_version=adapter_version,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )


__all__ = ["AssetResolver"]
