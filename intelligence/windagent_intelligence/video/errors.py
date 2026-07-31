"""
Typed failures for the video pre-production kernel (Phase 6).

Characterization (DEF-001, DEF-002, DEF-005) showed upstream silently returned
`None` or empty values on broken/empty/partial provider responses. The
canonical kernel surfaces typed failures instead of silent fallbacks so the
workflow can retry or escalate deterministically.
"""

from __future__ import annotations

from typing import Optional


class VideoKernelError(Exception):
    """Base class for all video kernel failures."""

    code = "VIDEO_KERNEL_ERROR"
    retryable = False

    def __init__(self, message: str, *, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ResponseParseError(VideoKernelError):
    """Provider returned content that could not be parsed as the contract."""

    code = "VIDEO_KERNEL_RESPONSE_PARSE"
    retryable = True


class EmptyResponseError(VideoKernelError):
    """Provider returned empty content."""

    code = "VIDEO_KERNEL_EMPTY_RESPONSE"
    retryable = True


class MissingModelConfigError(VideoKernelError):
    """A required canonical model was not configured for this capability."""

    code = "VIDEO_KERNEL_MISSING_MODEL"
    retryable = False


class ValidationFailureError(VideoKernelError):
    """Domain output failed validation before publish."""

    code = "VIDEO_KERNEL_VALIDATION"
    retryable = False


class CancellationError(VideoKernelError):
    """Capability was cancelled between stages."""

    code = "VIDEO_KERNEL_CANCELLED"
    retryable = False


class LockedScreenplayMutationError(VideoKernelError):
    """Attempt to mutate a locked screenplay without an explicit revision."""

    code = "VIDEO_KERNEL_LOCKED_MUTATION"
    retryable = False


__all__ = [
    "VideoKernelError",
    "ResponseParseError",
    "EmptyResponseError",
    "MissingModelConfigError",
    "ValidationFailureError",
    "CancellationError",
    "LockedScreenplayMutationError",
]
