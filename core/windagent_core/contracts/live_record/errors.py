"""Canonical Live Record error contract (live_record.contract/v0.1).

Stable error codes and HTTP status mapping for the Live Record boundary.
Fail-closed semantics: a stale or unfrozen plan can never start a recording
(ban_ke_hoach_v1.md Principle A).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from windagent_core.errors.exceptions import WindAgentError


class LiveRecordErrorCode(str, Enum):
    """Frozen canonical error codes for the Live Record boundary."""

    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    PLAN_FROZEN = "PLAN_FROZEN"
    PLAN_NOT_FROZEN = "PLAN_NOT_FROZEN"
    PLAN_STALE = "PLAN_STALE"
    ACTION_TAMPERED = "ACTION_TAMPERED"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


HTTP_STATUS_BY_CODE: Dict[LiveRecordErrorCode, int] = {
    LiveRecordErrorCode.NOT_FOUND: 404,
    LiveRecordErrorCode.VALIDATION_ERROR: 422,
    LiveRecordErrorCode.INVALID_TRANSITION: 409,
    LiveRecordErrorCode.PLAN_FROZEN: 409,
    LiveRecordErrorCode.PLAN_NOT_FROZEN: 409,
    LiveRecordErrorCode.PLAN_STALE: 409,
    LiveRecordErrorCode.ACTION_TAMPERED: 409,
    LiveRecordErrorCode.IDEMPOTENCY_MISMATCH: 409,
    LiveRecordErrorCode.CAPABILITY_UNAVAILABLE: 503,
}


class LiveRecordError(WindAgentError):
    """Base error for the canonical Live Record domain and application boundary."""

    code_value: LiveRecordErrorCode = LiveRecordErrorCode.VALIDATION_ERROR
    category: str = "LIVE_RECORD"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[LiveRecordErrorCode] = None,
        retryable: Optional[bool] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        resolved = code or self.code_value
        super().__init__(
            message,
            code=f"LIVE_RECORD_{resolved.value}",
            retryable=retryable,
            details=details,
            cause=cause,
        )
        self.live_record_code = resolved
        self.http_status = HTTP_STATUS_BY_CODE[resolved]

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["live_record_code"] = self.live_record_code.value
        data["http_status"] = self.http_status
        return data


class LiveRecordNotFoundError(LiveRecordError):
    code_value = LiveRecordErrorCode.NOT_FOUND


class LiveRecordValidationError(LiveRecordError):
    code_value = LiveRecordErrorCode.VALIDATION_ERROR


class LiveRecordInvalidTransitionError(LiveRecordError):
    """Illegal plan lifecycle transition."""

    code_value = LiveRecordErrorCode.INVALID_TRANSITION


class LiveRecordPlanFrozenError(LiveRecordError):
    """Mutation rejected because the plan is FROZEN (immutable after freeze)."""

    code_value = LiveRecordErrorCode.PLAN_FROZEN


class LiveRecordNotFrozenError(LiveRecordError):
    """Recording start rejected because the plan is not FROZEN."""

    code_value = LiveRecordErrorCode.PLAN_NOT_FROZEN


class LiveRecordPlanStaleError(LiveRecordError):
    """Plan's episode_revision no longer matches the episode's current revision."""

    code_value = LiveRecordErrorCode.PLAN_STALE


class LiveRecordCapabilityUnavailableError(LiveRecordError):
    """A required Live Record port is not composed; fail closed (503)."""

    code_value = LiveRecordErrorCode.CAPABILITY_UNAVAILABLE

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)
