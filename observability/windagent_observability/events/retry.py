"""Retry utilities for WindAgent Observability Layer (Phase 3)."""

from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta


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
