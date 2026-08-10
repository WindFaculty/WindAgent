"""
Canonical Studio error contract (studio.contract/v0.1).

Frozen error codes and HTTP status mapping
(docs/plans/studio_roadmap_01/fixtures/studio_contract_v0.1/errors.json). Each
error carries a stable code, HTTP status, category, and retryability so
application and plan C translation is deterministic. Payloads stay redaction-safe.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from windagent_core.errors.exceptions import WindAgentError, sanitize_error_details


class StudioErrorCode(str, Enum):
    """Frozen canonical error codes for the Studio boundary."""

    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    STALE_REVISION = "STALE_REVISION"
    STALE_NODE = "STALE_NODE"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    LOCKED_REVISION = "LOCKED_REVISION"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_STATUS_BY_CODE: Dict[StudioErrorCode, int] = {
    StudioErrorCode.NOT_FOUND: 404,
    StudioErrorCode.VALIDATION_ERROR: 422,
    StudioErrorCode.STALE_REVISION: 409,
    StudioErrorCode.STALE_NODE: 409,
    StudioErrorCode.ARTIFACT_HASH_MISMATCH: 409,
    StudioErrorCode.LOCKED_REVISION: 409,
    StudioErrorCode.IDEMPOTENCY_MISMATCH: 409,
    StudioErrorCode.INVALID_TRANSITION: 409,
    StudioErrorCode.APPROVAL_REQUIRED: 409,
    StudioErrorCode.CAPABILITY_UNAVAILABLE: 503,
    StudioErrorCode.PROVIDER_UNAVAILABLE: 503,
    StudioErrorCode.INTERNAL_ERROR: 500,
}


class StudioError(WindAgentError):
    """Base error for the canonical Studio domain and application boundary."""

    code_value: StudioErrorCode = StudioErrorCode.INTERNAL_ERROR
    category: str = "STUDIO"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[StudioErrorCode] = None,
        retryable: Optional[bool] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        resolved = code or self.code_value
        super().__init__(
            message,
            code=f"STUDIO_{resolved.value}" if resolved is not StudioErrorCode.INTERNAL_ERROR else "STUDIO_INTERNAL_ERROR",
            retryable=retryable,
            details=details,
            cause=cause,
        )
        self.studio_code = resolved
        self.http_status = HTTP_STATUS_BY_CODE[resolved]

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["studio_code"] = self.studio_code.value
        data["http_status"] = self.http_status
        return data


class StudioNotFoundError(StudioError):
    code_value = StudioErrorCode.NOT_FOUND


class StudioValidationError(StudioError):
    code_value = StudioErrorCode.VALIDATION_ERROR


class StudioStaleRevisionError(StudioError):
    """Expected revision/version does not match the current aggregate state."""

    code_value = StudioErrorCode.STALE_REVISION
    category = "STUDIO_CONCURRENCY"


class StudioStaleNodeError(StudioError):
    """Durable run-node write raced: the node version moved since it was read."""

    code_value = StudioErrorCode.STALE_NODE
    category = "STUDIO_CONCURRENCY"


class StudioArtifactHashMismatchError(StudioError):
    """Artifact content hash does not match the expected canonical hash."""

    code_value = StudioErrorCode.ARTIFACT_HASH_MISMATCH
    category = "STUDIO_INTEGRITY"


class StudioLockedRevisionError(StudioError):
    """Operation rejected because the revision is locked."""

    code_value = StudioErrorCode.LOCKED_REVISION
    category = "STUDIO_LOCK"


class StudioIdempotencyMismatchError(StudioError):
    """Repeated idempotency key used with a different normalized request."""

    code_value = StudioErrorCode.IDEMPOTENCY_MISMATCH
    category = "STUDIO_IDEMPOTENCY"


class StudioInvalidTransitionError(StudioError):
    """Episode state transition is not allowed by the lifecycle contract."""

    code_value = StudioErrorCode.INVALID_TRANSITION
    category = "STUDIO_STATE"


class StudioApprovalRequiredError(StudioError):
    """Command disallowed because approval is required; waiting is a run state."""

    code_value = StudioErrorCode.APPROVAL_REQUIRED
    category = "STUDIO_APPROVAL"


class StudioCapabilityUnavailableError(StudioError):
    """Required runtime capability is unavailable; no silent fallback."""

    code_value = StudioErrorCode.CAPABILITY_UNAVAILABLE
    category = "STUDIO_CAPABILITY"
    retryable = True


class StudioProviderUnavailableError(StudioError):
    """Provider endpoint unavailable."""

    code_value = StudioErrorCode.PROVIDER_UNAVAILABLE
    category = "STUDIO_PROVIDER"
    retryable = True


class StudioInternalError(StudioError):
    code_value = StudioErrorCode.INTERNAL_ERROR


__all__ = [
    "StudioErrorCode",
    "HTTP_STATUS_BY_CODE",
    "StudioError",
    "StudioNotFoundError",
    "StudioValidationError",
    "StudioStaleRevisionError",
    "StudioArtifactHashMismatchError",
    "StudioLockedRevisionError",
    "StudioIdempotencyMismatchError",
    "StudioInvalidTransitionError",
    "StudioApprovalRequiredError",
    "StudioCapabilityUnavailableError",
    "StudioProviderUnavailableError",
    "StudioInternalError",
]
