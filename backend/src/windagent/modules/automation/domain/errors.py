"""Automation error taxonomy (Phase 12).

Every failure is a kernel ``DomainError`` with a stable ``code`` preserved
for deterministic API mapping.  Codes are ``automation.*`` namespaced.
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class AutomationError(DomainError):
    """Base class for every Automation domain failure."""

    default_code: ClassVar[str] = "automation_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        normalized = message.strip() if message.strip() else "automation failure"
        super().__init__(normalized, context=context)


class AutomationValidationError(AutomationError):
    """Request payload violated a module invariant."""

    default_code = "validation_error"


class AutomationNotFoundError(AutomationError):
    """Referenced tool or run does not exist."""

    default_code = "not_found"


class AutomationConflictError(AutomationError):
    """Namespace collision or optimistic version mismatch (409)."""

    default_code = "conflict"


class AutomationPolicyDeniedError(AutomationError):
    """Tool invocation denied by Policy Engine."""

    default_code = "forbidden"


class AutomationPolicyApprovalRequiredError(AutomationError):
    """Tool invocation requires explicit approval."""

    default_code = "conflict"


class AutomationRuntimeError(AutomationError):
    """Adapter execution failure."""

    default_code = "runtime_error"


class AutomationStaleVersionError(AutomationError):
    """Optimistic version stale."""

    default_code = "conflict"


__all__ = [
    "AutomationConflictError",
    "AutomationError",
    "AutomationNotFoundError",
    "AutomationPolicyApprovalRequiredError",
    "AutomationPolicyDeniedError",
    "AutomationRuntimeError",
    "AutomationStaleVersionError",
    "AutomationValidationError",
]
