"""Request principal plumbing.

Phase 9 replaces the Phase 8 trust-on-first-sight header resolver with
verified authentication: ``AuthenticationMiddleware`` validates the bearer
token and stamps the resulting principal onto ``request.state``.  Routes and
handlers read it through :func:`get_principal` without knowing how it was
verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from starlette.requests import Request
from windagent.kernel.ids import ActorId
from windagent.platform.security import Identity

PRINCIPAL_ATTR = "windagent_principal"

PrincipalSource = Literal["anonymous", "bearer"]


@dataclass(frozen=True, slots=True)
class Principal:
    """The verified (or anonymous) actor behind one request."""

    actor_id: ActorId | None
    source: PrincipalSource
    identity: Identity | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.actor_id is not None


ANONYMOUS_PRINCIPAL = Principal(actor_id=None, source="anonymous")


def get_principal(request: Request) -> Principal:
    """FastAPI dependency returning the request principal.

    When no authentication middleware is configured (explicitly unsecured
    development mode) every request is anonymous.
    """
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if isinstance(principal, Principal):
        return principal
    return ANONYMOUS_PRINCIPAL
