"""Retry classifier + backoff (Phase 13).

Ports ``windagent_orchestration.retry.*`` semantics: deterministic
error classification (retryable vs terminal), exponential backoff with
jitter bound, and max_attempts gating.  Pure domain — no I/O.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class RetryDecision(StrEnum):
    RETRY = "RETRY"
    FAIL = "FAIL"
    RETRY_WAIT = "RETRY_WAIT"


# Error substrings that are always retryable (transient)
_RETRYABLE_SUBSTRINGS: Final[frozenset[str]] = frozenset(
    {
        "timeout",
        "timed out",
        "rate limited",
        "429",
        "503",
        "502",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "transient",
        "overloaded",
        "throttled",
        "deadline exceeded",
    }
)

_TERMINAL_SUBSTRINGS: Final[frozenset[str]] = frozenset(
    {
        "validation_error",
        "invalid_transition",
        "budget exhausted",
        "approval denied",
        "not_found",
        "forbidden",
        "unauthorized",
        "policy denied",
        "hash mismatch",
        "cycle detected",
        "unknown node",
    }
)


def classify_error(error: str | None, *, attempt: int, max_attempts: int) -> RetryDecision:
    """Deterministic classifier: terminal > retryable > attempts gate."""
    if error is None or not error.strip():
        # Unknown error — be conservative: allow retry if attempts remain
        return RetryDecision.RETRY if attempt < max_attempts else RetryDecision.FAIL
    lowered = error.lower()
    for term in _TERMINAL_SUBSTRINGS:
        if term in lowered:
            return RetryDecision.FAIL
    for term in _RETRYABLE_SUBSTRINGS:
        if term in lowered:
            return RetryDecision.RETRY if attempt < max_attempts else RetryDecision.FAIL
    # Default: retry if attempts remain, else fail
    return RetryDecision.RETRY if attempt < max_attempts else RetryDecision.FAIL


def backoff_seconds(attempt: int, *, base: float = 1.0, factor: float = 2.0, max_seconds: float = 60.0) -> float:
    """Exponential backoff: base * factor^(attempt-1), capped, with deterministic jitter."""
    if attempt <= 0:
        return base
    raw = base * (factor ** (attempt - 1))
    capped = min(raw, max_seconds)
    # Deterministic jitter ±10% derived from attempt hash
    h = int(hashlib.sha256(str(attempt).encode()).hexdigest()[:8], 16)
    jitter = (h % 2000) / 10000.0 - 0.1  # -0.1 .. +0.0999
    return max(0.1, capped * (1.0 + jitter))


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_backoff: float = 1.0
    factor: float = 2.0
    max_backoff: float = 60.0

    def should_retry(self, attempt: int, error: str | None) -> bool:
        return classify_error(error, attempt=attempt, max_attempts=self.max_attempts) == RetryDecision.RETRY

    def next_backoff(self, attempt: int) -> float:
        return backoff_seconds(attempt, base=self.base_backoff, factor=self.factor, max_seconds=self.max_backoff)

    def next_attempt(self, attempt: int) -> int:
        return attempt + 1


__all__ = ["RetryDecision", "RetryPolicy", "backoff_seconds", "classify_error"]
