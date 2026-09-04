"""Studio error taxonomy (Phase 15).

Every failure is a kernel ``DomainError`` with a stable ``code`` preserved
from the old ``windagent_core.contracts.studio.errors`` so API mapping stays
deterministic.  The hierarchy mirrors the frozen studio.contract/v0.1 error
codes (docs/plans/studio_roadmap_01 fixtures) plus V2 module scoping.
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class StudioError(DomainError):
    """Base class for every Studio domain failure."""

    default_code: ClassVar[str] = "studio_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        normalized = message.strip() if message.strip() else "studio failure"
        super().__init__(normalized, context=context)


class StudioValidationError(StudioError):
    """Request payload violated a module invariant."""

    default_code = "validation_error"


class StudioNotFoundError(StudioError):
    """Referenced aggregate or artifact does not exist."""

    default_code = "not_found"


class StudioStaleRevisionError(StudioError):
    """Optimistic version or content hash is stale (409)."""

    default_code = "conflict"


class StudioArtifactHashMismatchError(StudioError):
    """Submitted artifact hash does not match canonical hash."""

    default_code = "conflict"


class StudioLockedRevisionError(StudioError):
    """Operation rejected because the revision is locked."""

    default_code = "conflict"


class StudioInvalidTransitionError(StudioError):
    """Episode state transition not allowed by the lifecycle contract."""

    default_code = "conflict"


class StudioApprovalRequiredError(StudioError):
    """Action requires an approval that has not been granted."""

    default_code = "conflict"


class StudioStateError(StudioError):
    """Aggregate is in a state that forbids the requested mutation."""

    default_code = "conflict"


class StudioCapabilityUnavailableError(StudioError):
    """Required runtime capability is unavailable."""

    default_code = "conflict"


__all__ = [
    "StudioApprovalRequiredError",
    "StudioArtifactHashMismatchError",
    "StudioCapabilityUnavailableError",
    "StudioError",
    "StudioInvalidTransitionError",
    "StudioLockedRevisionError",
    "StudioNotFoundError",
    "StudioStaleRevisionError",
    "StudioStateError",
    "StudioValidationError",
]
