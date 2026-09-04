"""Circuit breaker policy for provider endpoints.

REWRITE of the frozen ``providers/windagent_providers/routing/circuit_breaker.py``
semantics as pure functions over a frozen state record, so the durable SQL
adapter (infrastructure) applies exactly the same rules the old in-memory
manager did: a circuit opens after ``failure_threshold`` consecutive
failures, stays open for ``half_open_timeout_s``, closes again on the first
success, and cooldowns only ever extend.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final

from windagent.kernel.time import normalize_utc

DEFAULT_FAILURE_THRESHOLD: Final[int] = 3
DEFAULT_HALF_OPEN_TIMEOUT_S: Final[float] = 30.0

CIRCUIT_CLOSED: Final[str] = "closed"
CIRCUIT_OPEN: Final[str] = "open"


@dataclass(frozen=True, slots=True)
class EndpointRuntimeState:
    """The durable runtime state of one provider endpoint."""

    consecutive_failures: int = 0
    success_count: int = 0
    failure_count: int = 0
    cooldown_until: datetime | None = None
    circuit_open_until: datetime | None = None
    last_latency_ms: float = 0.0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_class: str | None = None

    def circuit_state(self, now: datetime) -> str:
        """Report the observable circuit state at ``now``."""
        open_until = self.circuit_open_until
        if open_until is not None and normalize_utc(now) < normalize_utc(open_until):
            return CIRCUIT_OPEN
        return CIRCUIT_CLOSED


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    """Configurable threshold and recovery window (old defaults preserved)."""

    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    half_open_timeout_s: float = DEFAULT_HALF_OPEN_TIMEOUT_S

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.half_open_timeout_s <= 0:
            raise ValueError("half_open_timeout_s must be positive")

    def is_available(self, state: EndpointRuntimeState, now: datetime) -> bool:
        """An endpoint is selectable when neither cooldown nor circuit blocks it."""
        current = normalize_utc(now)
        if state.cooldown_until is not None and current < normalize_utc(state.cooldown_until):
            return False
        if state.circuit_open_until is not None and current < normalize_utc(
            state.circuit_open_until
        ):
            return False
        return True

    def after_success(
        self, state: EndpointRuntimeState, now: datetime, latency_ms: float
    ) -> EndpointRuntimeState:
        """Record a success: reset the failure streak and close the circuit."""
        return replace(
            state,
            consecutive_failures=0,
            success_count=state.success_count + 1,
            cooldown_until=None,
            circuit_open_until=None,
            last_latency_ms=latency_ms,
            last_success_at=normalize_utc(now),
        )

    def after_failure(
        self,
        state: EndpointRuntimeState,
        now: datetime,
        *,
        error_class: str,
        cooldown_until: datetime | None = None,
    ) -> EndpointRuntimeState:
        """Record a failure, opening the circuit at the consecutive threshold."""
        current = normalize_utc(now)
        streak = state.consecutive_failures + 1
        open_until = state.circuit_open_until
        if streak >= self.failure_threshold:
            open_until = current + timedelta(seconds=self.half_open_timeout_s)
        return replace(
            state,
            consecutive_failures=streak,
            failure_count=state.failure_count + 1,
            last_failure_at=current,
            last_error_class=error_class,
            cooldown_until=_extend(state.cooldown_until, cooldown_until),
            circuit_open_until=open_until,
        )

    def with_cooldown(
        self, state: EndpointRuntimeState, cooldown_until: datetime
    ) -> EndpointRuntimeState:
        """Extend (never shorten) the endpoint cooldown."""
        return replace(
            state, cooldown_until=_extend(state.cooldown_until, cooldown_until)
        )


def _extend(
    current: datetime | None, candidate: datetime | None
) -> datetime | None:
    """Keep the later of two cooldown deadlines."""
    if candidate is None:
        return current
    if current is None:
        return normalize_utc(candidate)
    return max(normalize_utc(current), normalize_utc(candidate))
