"""Agent Runtime error taxonomy (Phase 13).

Every failure is a kernel ``DomainError`` with a stable code. Codes are
``agent_runtime.*`` namespaced; HTTP mapping mirrors other modules
(validation 400, not_found 404, conflict 409, forbidden 403).
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class AgentRuntimeError(DomainError):
    """Base class for every Agent Runtime domain failure."""

    default_code: ClassVar[str] = "agent_runtime_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        normalized = message.strip() if message.strip() else "agent runtime failure"
        super().__init__(normalized, context=context)


class AgentRuntimeValidationError(AgentRuntimeError):
    """Request payload violated a module invariant."""

    default_code = "validation_error"


class AgentRuntimeNotFoundError(AgentRuntimeError):
    """Referenced aggregate does not exist."""

    default_code = "not_found"


class AgentRuntimeStaleVersionError(AgentRuntimeError):
    """Optimistic version mismatch (409)."""

    default_code = "conflict"


class AgentRuntimeInvalidTransitionError(AgentRuntimeError):
    """State transition not allowed."""

    default_code = "conflict"


class AgentRuntimeStateError(AgentRuntimeError):
    """Aggregate is in a state that forbids the mutation."""

    default_code = "conflict"


class AgentRuntimeBudgetExhaustedError(AgentRuntimeError):
    """Budget limits exhausted — fail closed."""

    default_code = "conflict"


class AgentRuntimeApprovalRequiredError(AgentRuntimeError):
    """Task is waiting for approval."""

    default_code = "conflict"


class AgentRuntimeDelegationError(AgentRuntimeError):
    """Delegation invariant violation."""

    default_code = "conflict"


class AgentRuntimeWorkflowError(AgentRuntimeError):
    """Workflow DAG or step error."""

    default_code = "validation_error"


__all__ = [
    "AgentRuntimeApprovalRequiredError",
    "AgentRuntimeBudgetExhaustedError",
    "AgentRuntimeDelegationError",
    "AgentRuntimeError",
    "AgentRuntimeInvalidTransitionError",
    "AgentRuntimeNotFoundError",
    "AgentRuntimeStaleVersionError",
    "AgentRuntimeStateError",
    "AgentRuntimeValidationError",
    "AgentRuntimeWorkflowError",
]
