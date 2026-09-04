"""Per-client rate limiting for HTTP requests.

The limiter is keyed by client host; when the composition root configures a
limiter, exhausted clients receive the canonical 429 envelope plus a
``Retry-After`` hint.  Successful responses carry ``X-RateLimit-*`` headers
so well-behaved clients can pace themselves.
"""

from __future__ import annotations

from math import ceil

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp
from windagent.platform.security import RateLimiter

from ..errors import error_envelope


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rejects requests once a client exhausts its window budget."""

    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        key = request.client.host if request.client is not None else "unknown"
        decision = await self._limiter.check(key)
        if not decision.allowed:
            headers: dict[str, str] = {}
            if decision.retry_after_s is not None:
                headers["Retry-After"] = str(int(ceil(decision.retry_after_s)))
            return JSONResponse(
                error_envelope("rate_limited", "too many requests", {}),
                status_code=429,
                headers=headers,
            )
        response = await call_next(request)
        response.headers["x-ratelimit-limit"] = str(decision.limit)
        response.headers["x-ratelimit-remaining"] = str(decision.remaining)
        return response
