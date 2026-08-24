"""Live Record V3 shared dependencies.

Idempotency rule mirrors Studio: every mutating endpoint requires a non-blank
``X-Idempotency-Key`` header. Errors raise the Live Record error family so
they map through the live-record problem handler.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, Request

from windagent_api.dependencies import get_container
from windagent_core.contracts.live_record.errors import (
    LiveRecordCapabilityUnavailableError,
    LiveRecordValidationError,
)
from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)


def get_live_record_service(request: Request) -> LiveRecordApplicationService:
    container = get_container(request)
    service = getattr(container, "live_record_application_service", None)
    if service is None:
        raise LiveRecordCapabilityUnavailableError(
            "Live Record application service is not composed.",
            details={"missing": "live_record_application_service"},
        )
    return service


def require_idempotency_key(
    x_idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
) -> str:
    if not x_idempotency_key or not x_idempotency_key.strip():
        raise LiveRecordValidationError(
            "X-Idempotency-Key header is required for Live Record mutating commands.",
            details={"field": "X-Idempotency-Key"},
        )
    return x_idempotency_key.strip()


__all__ = ["get_live_record_service", "require_idempotency_key"]
