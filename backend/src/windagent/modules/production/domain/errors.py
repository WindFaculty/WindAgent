"""Production error taxonomy (Phase 16).

Every failure is a kernel ``DomainError`` with a stable ``code`` so API
mapping stays deterministic.  Codes are ``production.*`` namespaced.
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class ProductionError(DomainError):
    """Base class for every Production domain failure."""

    default_code: ClassVar[str] = "production_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        normalized = message.strip() if message.strip() else "production failure"
        super().__init__(normalized, context=context)


class ProductionValidationError(ProductionError):
    """Request payload violated a module invariant."""

    default_code = "validation_error"


class ProductionNotFoundError(ProductionError):
    """Referenced aggregate or artifact does not exist."""

    default_code = "not_found"


class ProductionStaleRevisionError(ProductionError):
    """Optimistic version or content hash is stale (409)."""

    default_code = "conflict"


class ProductionArtifactHashMismatchError(ProductionError):
    """Submitted artifact hash does not match canonical hash."""

    default_code = "conflict"


class ProductionLockedRevisionError(ProductionError):
    """Operation rejected because the revision is locked."""

    default_code = "conflict"


class ProductionInvalidTransitionError(ProductionError):
    """State transition not allowed by the lifecycle contract."""

    default_code = "conflict"


class ProductionStateError(ProductionError):
    """Aggregate is in a state that forbids the requested mutation."""

    default_code = "conflict"


class ProductionQuarantinedAssetError(ProductionError):
    """Asset is quarantined and requires a fresh review to promote."""

    default_code = "conflict"


__all__ = [
    "ProductionArtifactHashMismatchError",
    "ProductionError",
    "ProductionInvalidTransitionError",
    "ProductionLockedRevisionError",
    "ProductionNotFoundError",
    "ProductionQuarantinedAssetError",
    "ProductionStaleRevisionError",
    "ProductionStateError",
    "ProductionValidationError",
]
