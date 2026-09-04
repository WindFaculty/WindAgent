"""Session aggregate (Phase 13).

Thin wrapper around ``lifecycle.SessionLifecycle`` providing the
optimistic-version bump helper used by the service layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import AgentRuntimeStaleVersionError, AgentRuntimeValidationError
from .lifecycle import SessionLifecycle, SessionState


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    session_id: str = Field(min_length=1)
    actor_id: str = Field(default="system", min_length=1)
    title: str = Field(default="Untitled session", min_length=1)
    state: SessionState = SessionState.IDLE
    budget_limits: dict[str, Any] = Field(default_factory=dict)
    budget_usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id", "actor_id", "title")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeValidationError("Session field cannot be blank.")
        return v.strip()

    def transition_to(self, target: SessionState, *, expected_version: int | None = None, reason: str | None = None) -> AgentSession:
        if expected_version is not None and expected_version != self.optimistic_version:
            raise AgentRuntimeStaleVersionError(
                "Session optimistic version mismatch.",
                context={"session_id": self.session_id, "expected_version": expected_version, "current_version": self.optimistic_version},
            )
        next_state = SessionLifecycle.transition(self.state, target)
        if next_state == self.state:
            return self
        return self.model_copy(
            update={"state": next_state, "updated_at": _utc_now(), "optimistic_version": self.optimistic_version + 1}
        )


__all__ = ["AgentSession"]
