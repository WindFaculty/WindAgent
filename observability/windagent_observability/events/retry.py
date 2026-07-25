"""Retry utilities for WindAgent Observability Layer (Phase 3 / Phase 6)."""

from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta


DEFAULT_MAX_ATTEMPTS = 5


class NonRetryablePublicationError(Exception):
    """Publication failure that must not be retried (validation, schema, auth)."""


def is_retryable_error(exc: BaseException) -> bool:
    """Classify whether a publish failure should be retried."""
    if isinstance(exc, NonRetryablePublicationError):
        return False
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return False
    message = str(exc).lower()
    non_retryable_markers = (
        "invalid payload",
        "schema validation",
        "unauthorized",
        "forbidden",
        "not found",
        "malformed",
    )
    if any(marker in message for marker in non_retryable_markers):
        return False
    return True


def compute_backoff_seconds(
    attempt_count: int,
    base_seconds: float = 2.0,
    max_seconds: float = 300.0,
    jitter: bool = True,
) -> float:
    """Exponential backoff with optional jitter."""
    delay = min(base_seconds * (2 ** attempt_count), max_seconds)
    if jitter:
        delay = delay * (0.5 + random.random())
    return delay


def next_available_at(attempt_count: int, now: datetime | None = None) -> datetime:
    """Compute next retry timestamp."""
    now = now or datetime.now(timezone.utc)
    return now + timedelta(seconds=compute_backoff_seconds(attempt_count))
