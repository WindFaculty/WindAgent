"""Invocation and result domain models (Phase 12).

Frozen shapes from ``windagent_core.contracts.tools.invocation`` and
``windagent_core.contracts.tools.results`` but re-expressed as a
single bounded context.  ``ToolInvocation`` is immutable and validates
that ``tool_name`` is non-blank; ``ToolExecutionContext`` is the
ambient authorization + workspace scope passed to every runtime adapter.

No legacy import appears here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    """Immutable request to execute a single tool."""

    tool_name: str
    call_id: str = field(default_factory=_new_call_id)
    params: dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout_seconds: float | None = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", _required_text(self.tool_name, "tool_name"))
        object.__setattr__(self, "call_id", _required_text(self.call_id, "call_id"))
        if not isinstance(self.params, dict):
            raise TypeError("params must be a dict")
        # freeze shallow copy to prevent mutation surprises
        object.__setattr__(self, "params", dict(self.params))
        if self.timeout_seconds is not None:
            if isinstance(self.timeout_seconds, bool) or not isinstance(
                self.timeout_seconds, (int, float)
            ):
                raise TypeError("timeout_seconds must be a number")
            if self.timeout_seconds <= 0:
                raise ValueError("timeout_seconds must be positive")
            object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        if not isinstance(self.requested_at, datetime):
            raise TypeError("requested_at must be a datetime")

    @property
    def arguments(self) -> dict[str, Any]:
        return self.params

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "params": self.params,
            "requested_at": self.requested_at.isoformat(),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Ambient execution context passed to every adapter."""

    workspace_root: str
    actor_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    session_id: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)
    user_approved: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", _required_text(self.workspace_root, "workspace_root"))
        if self.actor_id is not None:
            object.__setattr__(self, "actor_id", _required_text(self.actor_id, "actor_id"))
        if not isinstance(self.env_vars, dict):
            raise TypeError("env_vars must be a dict")
        # normalize env_vars values to str
        object.__setattr__(self, "env_vars", {str(k): str(v) for k, v in self.env_vars.items()})
        if not isinstance(self.user_approved, bool):
            raise TypeError("user_approved must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "actor_id": self.actor_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "env_vars": self.env_vars,
            "user_approved": self.user_approved,
        }


__all__ = ["ToolExecutionContext", "ToolInvocation"]
