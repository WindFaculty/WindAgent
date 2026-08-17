"""
Correlation ID context and middleware for distributed tracing across V3.
"""

from __future__ import annotations
import uuid
import contextvars
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def get_correlation_id() -> Optional[str]:
    """Retrieve the current request's correlation ID from context."""
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the current request's correlation ID in context."""
    _correlation_id_ctx.set(correlation_id)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every incoming HTTP request has an X-Correlation-ID:
    - If supplied by client, preserves it.
    - If absent, generates a new UUIDv4 string.
    - Attaches to request.state and contextvar.
    - Echoes X-Correlation-ID header on the response.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        corr_id = request.headers.get("X-Correlation-ID") or f"corr_{uuid.uuid4().hex}"
        request.state.correlation_id = corr_id
        set_correlation_id(corr_id)
        
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response
