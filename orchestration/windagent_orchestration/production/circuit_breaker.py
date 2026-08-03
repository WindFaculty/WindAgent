"""
Provider circuit breaker for the Durable Production Workflow (plan 05 §19.5,
gate VP19_COST_AND_QUOTA_CONTROL_VERIFIED).

The circuit opens when:

- insufficient credits;
- repeated provider/account errors;
- observed cost deviates from the estimate beyond policy;
- the UI cannot determine config/cost;
- a repeated account challenge occurs.

Reset rules:

- reset happens by TIME / policy or by HUMAN review — the breaker never
  auto-resets continuously; it moves to HALF_OPEN after a cooldown and only
  closes after a successful probe (or an explicit human reset).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

CIRCUIT_BREAKER_SCHEMA_VERSION = "1.0.0"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class TripReason(str, Enum):
    INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
    REPEATED_PROVIDER_ERROR = "REPEATED_PROVIDER_ERROR"
    COST_DEVIATION = "COST_DEVIATION"
    UNKNOWN_CONFIG_OR_COST = "UNKNOWN_CONFIG_OR_COST"
    ACCOUNT_CHALLENGE = "ACCOUNT_CHALLENGE"
    HUMAN = "HUMAN"


@dataclass(frozen=True)
class CircuitEvent:
    event_id: str
    state: CircuitState
    reason: str
    detail: str = ""
    occurred_at: float = 0.0


class ProviderCircuitBreaker:
    """Stateful circuit breaker with human/time reset (never continuous)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300.0,
        max_cost_deviation_ratio: float = 1.5,
        clock: Optional[object] = None,
        id_fn: Optional[object] = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValidationError(
                "failure_threshold must be >= 1", code="WINDAGENT_ERR_VALIDATION"
            )
        if cooldown_seconds <= 0:
            raise ValidationError(
                "cooldown_seconds must be > 0", code="WINDAGENT_ERR_VALIDATION"
            )
        if max_cost_deviation_ratio < 1.0:
            raise ValidationError(
                "max_cost_deviation_ratio must be >= 1.0", code="WINDAGENT_ERR_VALIDATION"
            )
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.max_cost_deviation_ratio = max_cost_deviation_ratio
        self._clock = clock or time.time
        self._id_fn = id_fn
        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self._half_open_success = False
        self._events: List[CircuitEvent] = []

    # -- state ---------------------------------------------------------------
    @property
    def state(self) -> CircuitState:
        return self._state

    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    # -- trips ---------------------------------------------------------------
    def trip(
        self,
        reason: TripReason,
        detail: str = "",
    ) -> CircuitState:
        """Open the circuit for a concrete reason (never silently)."""
        if self._state == CircuitState.OPEN:
            # already open — record the repeated trigger, keep OPEN
            self._record(CircuitState.OPEN, reason.value, detail)
            return self._state
        self._state = CircuitState.OPEN
        self._consecutive_failures += 1
        self._opened_at = float(self._clock())
        self._half_open_success = False
        self._record(CircuitState.OPEN, reason.value, detail)
        return self._state

    def record_provider_error(self, detail: str = "") -> CircuitState:
        """Count a provider/account error; open at the threshold (§19.5)."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            return self.trip(TripReason.REPEATED_PROVIDER_ERROR, detail or f"{self._consecutive_failures} consecutive failures")
        self._record(self._state, "PROVIDER_ERROR_COUNTED", detail or f"{self._consecutive_failures}/{self.failure_threshold}")
        return self._state

    def record_insufficient_credits(self, detail: str = "") -> CircuitState:
        return self.trip(TripReason.INSUFFICIENT_CREDITS, detail)

    def record_cost_deviation(
        self,
        *,
        observed: int,
        estimated: int,
        detail: str = "",
    ) -> CircuitState:
        """Open when observed cost exceeds the estimate beyond policy."""
        if estimated <= 0:
            return self.trip(TripReason.UNKNOWN_CONFIG_OR_COST, detail or "no estimate to compare against")
        ratio = observed / estimated
        if ratio > self.max_cost_deviation_ratio:
            return self.trip(
                TripReason.COST_DEVIATION,
                detail or f"observed {observed} vs estimated {estimated} (ratio {ratio:.2f} > {self.max_cost_deviation_ratio})",
            )
        self._record(self._state, "COST_WITHIN_POLICY", f"observed {observed} vs estimated {estimated}")
        return self._state

    def record_unknown_config(self, detail: str = "") -> CircuitState:
        return self.trip(TripReason.UNKNOWN_CONFIG_OR_COST, detail or "config/cost cannot be determined")

    def record_account_challenge(self, detail: str = "") -> CircuitState:
        return self.trip(TripReason.ACCOUNT_CHALLENGE, detail or "repeated account challenge")

    # -- success / probe -----------------------------------------------------
    def record_success(self, detail: str = "") -> CircuitState:
        """A successful operation resets failures; closes from HALF_OPEN."""
        self._consecutive_failures = 0
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._record(CircuitState.CLOSED, "PROBE_SUCCESS", detail or "half-open probe succeeded")
        else:
            self._record(self._state, "SUCCESS", detail)
        return self._state

    # -- reset ---------------------------------------------------------------
    def maybe_reset(self) -> CircuitState:
        """Time/policy reset: OPEN -> HALF_OPEN only after the cooldown.

        Never closes automatically; a HALF_OPEN breaker closes only after a
        successful probe (record_success) or an explicit human reset — the
        breaker never continuously auto-resets (§19.5).
        """
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return self._state
        elapsed = float(self._clock()) - self._opened_at
        if elapsed >= self.cooldown_seconds:
            self._state = CircuitState.HALF_OPEN
            self._record(CircuitState.HALF_OPEN, "COOLDOWN_ELAPSED", f"elapsed {elapsed:.0f}s >= {self.cooldown_seconds:.0f}s")
        return self._state

    def human_reset(self, actor: str = "operator", reason: str = "human review") -> CircuitState:
        """Explicit human/policy reset — always closes the circuit."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._record(CircuitState.CLOSED, "HUMAN_RESET", f"{actor}: {reason}")
        return self._state

    # -- introspection ---------------------------------------------------------
    def events(self) -> List[CircuitEvent]:
        return list(self._events)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": CIRCUIT_BREAKER_SCHEMA_VERSION,
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "opened_at": self._opened_at,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "max_cost_deviation_ratio": self.max_cost_deviation_ratio,
            "events": [
                {
                    "event_id": e.event_id,
                    "state": e.state.value,
                    "reason": e.reason,
                    "detail": e.detail,
                    "occurred_at": e.occurred_at,
                }
                for e in self._events
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderCircuitBreaker":
        cb = cls(
            failure_threshold=max(1, data.get("failure_threshold", 3)),
            cooldown_seconds=max(1.0, data.get("cooldown_seconds", 300.0)),
            max_cost_deviation_ratio=max(1.0, data.get("max_cost_deviation_ratio", 1.5)),
        )
        cb._state = CircuitState(data.get("state", "CLOSED"))
        cb._consecutive_failures = data.get("consecutive_failures", 0)
        cb._opened_at = data.get("opened_at")
        for raw in data.get("events", []):
            cb._events.append(
                CircuitEvent(
                    event_id=raw["event_id"],
                    state=CircuitState(raw["state"]),
                    reason=raw["reason"],
                    detail=raw.get("detail", ""),
                    occurred_at=raw.get("occurred_at", 0.0),
                )
            )
        return cb

    # -- internal ---------------------------------------------------------------
    def _record(self, state: CircuitState, reason: str, detail: str) -> None:
        event_id = ""
        if self._id_fn is not None and hasattr(self._id_fn, "__call__"):
            event_id = str(self._id_fn())
        if not event_id:
            event_id = f"cb_{uuid.uuid4().hex[:16]}"
        self._events.append(
            CircuitEvent(
                event_id=event_id,
                state=state,
                reason=reason,
                detail=detail,
                occurred_at=float(self._clock()),
            )
        )


__all__ = [
    "CIRCUIT_BREAKER_SCHEMA_VERSION",
    "CircuitState",
    "TripReason",
    "CircuitEvent",
    "ProviderCircuitBreaker",
]
