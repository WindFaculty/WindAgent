"""Verified request identity: bearer authentication and policy guards."""

from .authentication import (
    AUTHORIZATION_HEADER,
    PUBLIC_PATHS,
    AuthenticationMiddleware,
    unauthorized_response,
)
from .policy import require_policy
from .principal import (
    ANONYMOUS_PRINCIPAL,
    PRINCIPAL_ATTR,
    Principal,
    get_principal,
)

__all__ = [
    "ANONYMOUS_PRINCIPAL",
    "AUTHORIZATION_HEADER",
    "PRINCIPAL_ATTR",
    "PUBLIC_PATHS",
    "AuthenticationMiddleware",
    "Principal",
    "get_principal",
    "require_policy",
    "unauthorized_response",
]
