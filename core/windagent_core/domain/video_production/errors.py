"""
Domain-specific errors for the WindAgent Video Production protocol (Phase 3).

These subclass the canonical WindAgent error hierarchy so they remain
serializable and retry-classified by the rest of the platform.
"""

from __future__ import annotations

from windagent_core.errors.exceptions import (
    DomainError,
    ValidationError,
    TerminalStateMutationError,
    IntegrityError,
)


class VideoProductionProtocolError(DomainError):
    """Base error for the video production protocol boundary."""

    code = "VP_PROTOCOL_ERROR"
    category = "VIDEO_PRODUCTION"


class UnsupportedMajorVersionError(ValidationError):
    """Raised when a package/event schema major version is not supported.

    Versioning policy is fail-closed: unknown major versions are rejected
    instead of being silently interpreted.
    """

    code = "VP_UNSUPPORTED_MAJOR_VERSION"
    category = "VIDEO_PRODUCTION_SCHEMA"
    retryable = False


class LockedRevisionMutationError(TerminalStateMutationError):
    """Raised when a locked revision is mutated or re-derived without intent.

    Locked revisions are immutable; any content change must create a new
    revision carrying an explicit downstream invalidation intent.
    """

    code = "VP_LOCKED_REVISION_MUTATION"
    category = "VIDEO_PRODUCTION_REVISION"
    retryable = False


class BrokenReferenceError(IntegrityError):
    """Raised when a package references an identifier that does not exist."""

    code = "VP_BROKEN_REFERENCE"
    category = "VIDEO_PRODUCTION_INTEGRITY"
    retryable = False


class DuplicateIdentifierError(IntegrityError):
    """Raised when two entities in the same aggregate share an identifier."""

    code = "VP_DUPLICATE_IDENTIFIER"
    category = "VIDEO_PRODUCTION_INTEGRITY"
    retryable = False


__all__ = [
    "VideoProductionProtocolError",
    "UnsupportedMajorVersionError",
    "LockedRevisionMutationError",
    "BrokenReferenceError",
    "DuplicateIdentifierError",
]
