"""Bearer-token enforcement for HTTP requests.

The middleware is secure by default: when an authenticator is configured at
composition, every route except the declared public probes requires a valid
``Authorization: Bearer <token>`` header.  When no authenticator exists
(explicitly unsecured development mode) requests proceed anonymously.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp
from windagent.platform.observability import (
    bind_operation_context,
    current_operation_context,
)
from windagent.platform.security import AuthenticationFailedError, Authenticator

from ..errors import error_envelope
from .principal import PRINCIPAL_ATTR, Principal

PUBLIC_PATHS = frozenset(
    {"/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"}
)
AUTHORIZATION_HEADER = "authorization"
BEARER_PREFIX = "bearer "
WWW_AUTHENTICATE_VALUE = "Bearer"


def _bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    value = header.strip()
    if not value.lower().startswith(BEARER_PREFIX):
        return None
    token = value[len(BEARER_PREFIX) :].strip()
    return token or None


def unauthorized_response() -> JSONResponse:
    """The canonical 401 envelope with a Bearer challenge."""
    return JSONResponse(
        error_envelope("unauthorized", "authentication required", {}),
        status_code=401,
        headers={"WWW-Authenticate": WWW_AUTHENTICATE_VALUE},
    )


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Verifies bearer credentials before any route handler runs."""

    def __init__(self, app: ASGIApp, authenticator: Authenticator) -> None:
        super().__init__(app)
        self._authenticator = authenticator

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        token = _bearer_token(request.headers.get(AUTHORIZATION_HEADER))
        if token is None:
            return unauthorized_response()
        try:
            identity = await self._authenticator.authenticate(token)
        except AuthenticationFailedError:
            return unauthorized_response()
        setattr(request.state, PRINCIPAL_ATTR, Principal(
            actor_id=identity.actor_id, source="bearer", identity=identity
        ))
        operation_context = current_operation_context()
        if operation_context is None:
            return await call_next(request)
        with bind_operation_context(operation_context.with_actor(identity.actor_id)):
            return await call_next(request)
