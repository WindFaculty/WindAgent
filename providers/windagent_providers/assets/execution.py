"""
Execution policy for the Universal Asset Gateway (VP3D Phase 5).

Per-provider call envelope: timeout, bounded retries with backoff, circuit
breaker (CLOSED/OPEN/HALF_OPEN), cooperative cancellation and per-provider
concurrency limits. Fail-closed: a cancelled or timed-out call never publishes
a partial side effect; retries reuse the SAME typed failure classification.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from windagent_core.domain.video_production.asset_resolution import (
    AssetResolutionError,
    CircuitOpenError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ResolutionCancelledError,
    RetryBudgetExhaustedError,
)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker keyed by adapter_id."""

    adapter_id: str
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0

    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: Optional[float] = None

    def allow_call(self) -> bool:
        if self.state == CircuitState.OPEN:
            assert self.opened_at is not None
            if time.monotonic() - self.opened_at >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if (
            self.state == CircuitState.HALF_OPEN
            or self.consecutive_failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()

    def snapshot(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
        }


@dataclass(frozen=True)
class ExecutionPolicy:
    """Per-request execution envelope applied to every adapter call."""

    timeout_seconds: float = 30.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.5
    per_provider_concurrency: int = 4

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.per_provider_concurrency < 1:
            raise ValueError("per_provider_concurrency must be >= 1")


@dataclass
class CancellationScope:
    """Shared cooperative cancellation token for one resolution."""

    _cancelled: bool = field(default=False)

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise ResolutionCancelledError("Resolution was cancelled before completion.")


@dataclass(frozen=True)
class ExecutionOutcome:
    """Outcome of one policy-wrapped adapter call."""

    ok: bool
    value: Any = None
    error: Optional[AssetResolutionError] = None
    attempts: int = 0
    duration_ms: int = 0

    def error_code(self) -> Optional[str]:
        return self.error.code if self.error else None

    def error_message(self) -> str:
        return str(self.error) if self.error else ""


async def execute_with_policy(
    provider_id: str,
    operation: Callable[[], Awaitable[Any]],
    *,
    policy: ExecutionPolicy,
    breaker: CircuitBreaker,
    scope: CancellationScope,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> ExecutionOutcome:
    """Run one provider operation with timeout/retry/circuit/cancellation.

    - the circuit breaker rejects the call BEFORE execution when OPEN
      (typed ``CircuitOpenError``);
    - cancellation is checked before every attempt (cooperative);
    - each attempt runs under ``asyncio.wait_for`` with the request timeout;
    - failures retry up to ``policy.max_retries`` with backoff; the retry
      budget exhausted is reported as ``RetryBudgetExhaustedError``.
    """
    if not breaker.allow_call():
        return ExecutionOutcome(
            ok=False,
            error=CircuitOpenError(
                f"Circuit breaker OPEN for provider {provider_id}.",
                details={"provider_id": provider_id, **breaker.snapshot()},
            ),
            attempts=0,
        )

    if scope.cancelled:
        scope.raise_if_cancelled()

    started = time.monotonic()
    last_error: Optional[AssetResolutionError] = None
    attempts = 0
    budget = policy.max_retries + 1

    for attempt in range(budget):
        if scope.cancelled:
            scope.raise_if_cancelled()
        attempts = attempt + 1
        try:
            async def _guarded_call() -> Any:
                scope.raise_if_cancelled()
                if semaphore is not None:
                    async with semaphore:
                        scope.raise_if_cancelled()
                        return await operation()
                return await operation()

            result = await asyncio.wait_for(
                _guarded_call(),
                timeout=policy.timeout_seconds,
            )
            # Cancellation that arrived while the operation ran is honored
            # AFTER completion: no side effect of a cancelled call is published.
            scope.raise_if_cancelled()
            breaker.record_success()
            duration_ms = int((time.monotonic() - started) * 1000)
            return ExecutionOutcome(ok=True, value=result, attempts=attempts, duration_ms=duration_ms)
        except asyncio.TimeoutError:
            last_error = ProviderTimeoutError(
                f"Provider {provider_id} timed out after {policy.timeout_seconds}s.",
                details={"provider_id": provider_id, "timeout_seconds": policy.timeout_seconds},
            )
        except ResolutionCancelledError as exc:
            breaker.record_failure()
            raise exc
        except AssetResolutionError as exc:
            last_error = exc
        except Exception as exc:  # unexpected failure -> retryable, fail closed
            last_error = ProviderExecutionError(
                f"Provider {provider_id} failed unexpectedly: {exc.__class__.__name__}",
                details={"provider_id": provider_id},
            )
        breaker.record_failure()
        if attempt < budget - 1:
            await asyncio.sleep(policy.retry_backoff_seconds)

    duration_ms = int((time.monotonic() - started) * 1000)
    if last_error is not None and last_error.retryable and attempts > 1:
        return ExecutionOutcome(
            ok=False,
            error=RetryBudgetExhaustedError(
                f"Provider {provider_id} exhausted retry budget ({attempts} attempts).",
                details={"provider_id": provider_id, "attempts": attempts, "cause_code": last_error.code},
            ),
            attempts=attempts,
            duration_ms=duration_ms,
        )
    return ExecutionOutcome(
        ok=False,
        error=last_error,
        attempts=attempts,
        duration_ms=duration_ms,
    )


__all__ = [
    "CircuitState",
    "CircuitBreaker",
    "ExecutionPolicy",
    "CancellationScope",
    "ExecutionOutcome",
    "execute_with_policy",
]
