"""
V3 Studio error mapping (Plan C1).

``studio_error_handler`` serializes any ``StudioError`` to the frozen error
shape (errors.json): RFC 7807 fields plus ``studio_code``, ``retryable``,
``category``, and redaction-safe details. Registered in ``main.py``; Starlette
resolves it for every ``StudioError`` subclass before the generic
``WindAgentError`` handler.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from windagent_core.contracts.studio.errors import StudioError


def studio_error_handler(request: Request, exc: StudioError) -> JSONResponse:
    data = exc.to_dict()
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "type": f"https://windagent.io/errors/studio/{exc.studio_code.value.lower()}",
            "title": exc.studio_code.value.replace("_", " ").title(),
            "status": exc.http_status,
            "detail": exc.message,
            "code": data.get("code", f"STUDIO_{exc.studio_code.value}"),
            "studio_code": exc.studio_code.value,
            "category": exc.category,
            "retryable": bool(getattr(exc, "retryable", False)),
            "details": data.get("details", {}),
        },
    )


__all__ = ["studio_error_handler"]
