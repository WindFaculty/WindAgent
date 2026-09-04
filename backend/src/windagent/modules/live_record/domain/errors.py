"""Live Record error taxonomy (Phase 17).

Mirrors ``windagent_core.contracts.live_record.errors`` so HTTP mapping stays
stable. Every failure is a kernel ``DomainError`` with a stable code.
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class LiveRecordError(DomainError):
    """Base class for every Live Record domain failure."""

    default_code: ClassVar[str] = "live_record_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        normalized = message.strip() if message.strip() else "live record failure"
        super().__init__(normalized, context=context)


class LiveRecordValidationError(LiveRecordError):
    default_code = "validation_error"


class LiveRecordNotFoundError(LiveRecordError):
    default_code = "not_found"


class LiveRecordStaleVersionError(LiveRecordError):
    """Optimistic version or hash stale (409)."""

    default_code = "conflict"


class LiveRecordPlanFrozenError(LiveRecordError):
    """Mutation rejected because plan is FROZEN."""

    default_code = "conflict"


class LiveRecordNotFrozenError(LiveRecordError):
    """Operation requires a FROZEN plan."""

    default_code = "conflict"


class LiveRecordPlanStaleError(LiveRecordError):
    """Plan episode revision no longer matches current episode."""

    default_code = "conflict"


class LiveRecordInvalidTransitionError(LiveRecordError):
    default_code = "conflict"


class LiveRecordCapabilityUnavailableError(LiveRecordError):
    default_code = "conflict"


class LiveRecordPrivacyBlockedError(LiveRecordError):
    default_code = "conflict"


__all__ = [
    "LiveRecordCapabilityUnavailableError",
    "LiveRecordError",
    "LiveRecordInvalidTransitionError",
    "LiveRecordNotFoundError",
    "LiveRecordNotFrozenError",
    "LiveRecordPlanFrozenError",
    "LiveRecordPlanStaleError",
    "LiveRecordPrivacyBlockedError",
    "LiveRecordStaleVersionError",
    "LiveRecordValidationError",
]
