"""FastAPI exception handler for the Live Record error family."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from windagent_core.contracts.live_record.errors import LiveRecordError


def live_record_error_handler(request: Request, exc: LiveRecordError) -> JSONResponse:
    data = exc.to_dict()
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "type": f"https://windagent.io/errors/live-record/{exc.live_record_code.value.lower()}",
            "title": exc.live_record_code.value.replace("_", " ").title(),
            "status": exc.http_status,
            "detail": exc.message,
            "code": data.get("code", f"LIVE_RECORD_{exc.live_record_code.value}"),
            "live_record_code": exc.live_record_code.value,
            "category": exc.category,
            "retryable": bool(getattr(exc, "retryable", False)),
            "details": data.get("details", {}),
        },
    )


__all__ = ["live_record_error_handler"]
