"""Exception handlers producing one canonical error envelope.

Every error response uses the same shape so clients never parse two error
formats:

```json
{"error": {"code": "...", "message": "...", "context": {...}}}
```

Unexpected exceptions never leak internals: the response carries a generic
message, and details are only added for non-production environments.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from windagent.kernel.errors.domain import DomainError

from .mapping import DomainErrorStatusMapper

_STATUS_CODE_BY_HTTP_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "request_validation_error",
    429: "rate_limited",
}
_FALLBACK_HTTP_CODE = "request_error"


class ApiError(Exception):
    """Transport-level error carrying its own status and canonical code."""

    def __init__(
        self,
        status_code: int,
        *,
        code: str,
        message: str,
        context: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.context = context or {}
        super().__init__(message)


def error_envelope(
    code: str, message: str, context: dict[str, object] | None = None
) -> dict[str, object]:
    """Return the canonical single-key error response body."""
    return {"error": {"code": code, "message": message, "context": context or {}}}


def install_error_handlers(
    app: FastAPI,
    mapper: DomainErrorStatusMapper | None = None,
    *,
    expose_internals: bool = False,
) -> None:
    """Register the canonical handlers on ``app`` (call once at bootstrap)."""
    domain_mapper = mapper if mapper is not None else DomainErrorStatusMapper()

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            error_envelope(exc.code, exc.message, exc.context),
            status_code=exc.status_code,
        )

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = domain_mapper.status_for(exc)
        return JSONResponse(
            error_envelope(exc.code, exc.message, dict(exc.context)),
            status_code=status,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            error_envelope(
                "request_validation_error",
                "request payload failed validation",
                {"errors": _sanitized_validation_errors(exc.errors())},
            ),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            error_envelope(
                _STATUS_CODE_BY_HTTP_CODE.get(exc.status_code, _FALLBACK_HTTP_CODE),
                str(exc.detail),
            ),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        context: dict[str, object] = {}
        if expose_internals:
            context["detail"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(
            error_envelope("internal_error", "an unexpected error occurred", context),
            status_code=500,
        )


def _sanitized_validation_errors(errors: Sequence[Any]) -> list[dict[str, object]]:
    """Keep location and reason, drop client input from validation output."""
    sanitized: list[dict[str, object]] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        sanitized.append(
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "invalid input")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return sanitized
