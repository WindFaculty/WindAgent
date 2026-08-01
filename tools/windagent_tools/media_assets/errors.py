"""
Typed failures for the media asset pipeline (plan 02 Phase 7).

Every failure is a typed exception so workflows can retry/escalate
deterministically — no silent partial artifacts, no silent license
auto-approval (LICENSE_UNKNOWN never becomes APPROVED on its own).
"""

from __future__ import annotations

from typing import Optional


class AssetPipelineError(Exception):
    """Base class for media asset pipeline failures."""

    code = "ASSET_PIPELINE_ERROR"
    retryable = False

    def __init__(self, message: str, *, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class UrlBlockedError(AssetPipelineError):
    """URL/IP is blocked (non-HTTP(S) scheme, private/link-local/reserved IP,
    or DNS-rebinding host)."""

    code = "ASSET_URL_BLOCKED"
    retryable = False


class DownloadFailedError(AssetPipelineError):
    """Download failed (timeout, connection, too many redirects, oversize)."""

    code = "ASSET_DOWNLOAD_FAILED"
    retryable = True


class MediaValidationError(AssetPipelineError):
    """Media failed one of the ordered validation steps."""

    code = "ASSET_VALIDATION_FAILED"
    retryable = False


class LicenseUnknownError(AssetPipelineError):
    """Asset license is unknown; cannot be auto-approved (fail closed)."""

    code = "ASSET_LICENSE_UNKNOWN"
    retryable = False


class LikenessRequiresApprovalError(AssetPipelineError):
    """Real-person likeness requires human approval + usage evidence."""

    code = "ASSET_LIKENESS_NEEDS_APPROVAL"
    retryable = False


class RejectedAssetError(AssetPipelineError):
    """Rejected asset cannot be re-selected (no silent REJECTED -> APPROVED)."""

    code = "ASSET_REJECTED"
    retryable = False


__all__ = [
    "AssetPipelineError",
    "UrlBlockedError",
    "DownloadFailedError",
    "MediaValidationError",
    "LicenseUnknownError",
    "LikenessRequiresApprovalError",
    "RejectedAssetError",
]
