"""Cooldown and backoff computation.

REWRITE of the frozen ``providers/windagent_providers/routing/cooldown.py``.
The exponential backoff formula and the 300-second ceiling are parity
oracles; ``Retry-After`` parsing stays best-effort with a 1.0s default.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

COOLDOWN_CEILING_SECONDS: Final[float] = 300.0
DEFAULT_RETRY_AFTER_SECONDS: Final[float] = 1.0


def retry_after_seconds_from_headers(headers: Mapping[str, str] | None) -> float:
    """Best-effort parse of ``Retry-After`` from provider response headers.

    Falls back to provider-specific rate-limit headers, then to the 1.0s
    default when the value is missing or unparseable (HTTP-date values
    clamp to the default, matching the frozen behavior).
    """
    if not headers:
        return DEFAULT_RETRY_AFTER_SECONDS

    raw: str | None = None
    for key, value in headers.items():
        lowered = key.lower()
        if lowered == "retry-after" or "rate-limit-reset" in lowered:
            raw = value
            break

    if raw is None:
        return DEFAULT_RETRY_AFTER_SECONDS

    try:
        parsed = float(str(raw))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS
    return parsed


def calculate_backoff_cooldown_seconds(attempt_index: int, base: float = 1.0) -> float:
    """Exponential backoff capped at the cooldown ceiling."""
    backoff = base * (2**attempt_index)
    return float(min(backoff, COOLDOWN_CEILING_SECONDS))


def rate_limit_cooldown_seconds(headers: Mapping[str, str] | None) -> float:
    """Cooldown seconds for a 429: parsed Retry-After capped at the ceiling."""
    return min(retry_after_seconds_from_headers(headers), COOLDOWN_CEILING_SECONDS)
