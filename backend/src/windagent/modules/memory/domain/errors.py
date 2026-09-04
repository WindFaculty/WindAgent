"""Memory domain error taxonomy (Phase 14).

Every domain failure is a kernel DomainError with stable code preserved
for deterministic API mapping. Codes are memory.* namespaced.
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class MemoryError(DomainError):
    """Base class for every Memory domain failure."""

    default_code: ClassVar[str] = "memory_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        normalized = message.strip() if message.strip() else "memory failure"
        super().__init__(normalized, context=context)


class MemoryValidationError(MemoryError):
    """Memory record payload violated a validation rule."""

    default_code = "validation_error"


class MemoryNotFoundError(MemoryError):
    """Referenced memory record does not exist."""

    default_code = "not_found"


class MemoryPermissionDeniedError(MemoryError):
    """Memory write or operation denied by policy (e.g. secret credentials)."""

    default_code = "forbidden"


class MemoryConflictError(MemoryError):
    """Optimistic version conflict or unique constraint mismatch."""

    default_code = "conflict"


class MemoryStaleVersionError(MemoryError):
    """Optimistic version stale."""

    default_code = "conflict"


__all__ = [
    "MemoryConflictError",
    "MemoryError",
    "MemoryNotFoundError",
    "MemoryPermissionDeniedError",
    "MemoryStaleVersionError",
    "MemoryValidationError",
]
