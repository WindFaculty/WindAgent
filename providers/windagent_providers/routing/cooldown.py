"""
Cooldown helpers for WindAgent Provider Routing Phase 8.

These are thin wrappers around EndpointStatePort.set_cooldown for rate-limit
and retry backoff semantics.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from windagent_providers.base.errors import ProviderFailure, RateLimitFailure
from windagent_core.contracts.providers.ports import EndpointStatePort


_COOLDOWN_CEILING_SECONDS: float = 300.0


def _retry_after_from_headers(headers: Optional[dict]) -> float:
    """
    Best-effort parse of Retry-After from provider response headers.
    Returns seconds as float; defaults to 1.0 if unparseable.
    """
    if not headers:
        return 1.0

    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        # Some providers use provider-specific rate-limit headers.
        for key in headers:
            lowered = key.lower()
            if "retry-after" in lowered or "rate-limit-reset" in lowered:
                raw = headers[key]
                break

    if raw is None:
        return 1.0

    try:
        return float(raw)
    except (TypeError, ValueError):
        # Could be HTTP-date; for phase 8 we clamp to ceiling.
        return 1.0


async def apply_rate_limit_cooldown(
    state_port: EndpointStatePort,
    endpoint_id: str,
    failure: RateLimitFailure,
) -> None:
    """Record 429 cooldown using parsed Retry-After (capped at 5 minutes)."""
    seconds = _retry_after_from_headers(getattr(failure, "raw_error", None))
    seconds = min(seconds, _COOLDOWN_CEILING_SECONDS) if seconds else 1.0
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await state_port.set_cooldown(endpoint_id, until)


async def apply_transient_failure_cooldown(
    state_port: EndpointStatePort,
    endpoint_id: str,
    failure: ProviderFailure,
    *,
    attempt_index: int,
) -> None:
    """Temporarily remove a 5xx/network endpoint from same-model failover.

    A binding that failed a transient request must not be immediately selected
    again while an exact-equivalent sibling is available.  The duration is a
    bounded backoff and deliberately does not alter the canonical route lock.
    """
    del failure  # Kept in the signature for audit-friendly call sites.
    seconds = calculate_backoff_cooldown_seconds(attempt_index)
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await state_port.set_cooldown(endpoint_id, until)


def calculate_backoff_cooldown_seconds(attempt_index: int, base: float = 1.0) -> float:
    """Exponential backoff capped at ceiling."""
    return min(base * (2**attempt_index), _COOLDOWN_CEILING_SECONDS)
