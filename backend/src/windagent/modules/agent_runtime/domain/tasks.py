"""Task aggregate helpers (Phase 13).

The Task aggregate is persisted as a row but its state machine lives here so
services can validate transitions before issuing CAS updates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import AgentRuntimeStaleVersionError, AgentRuntimeValidationError
from .lifecycle import TaskLifecycle, TaskState


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    run_id: str | None = None
    workflow_id: str | None = None
    title: str = Field(min_length=1)
    description: str = Field(default="")
    state: TaskState = TaskState.RECEIVED
    priority: int = Field(default=0)
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    awaiting_approval_id: str | None = None
    checkpoint_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_id", "session_id", "title")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeValidationError("Task field cannot be blank.")
        return v.strip()

    def transition_to(self, target: TaskState, *, expected_version: int | None = None) -> AgentTask:
        if expected_version is not None and expected_version != self.optimistic_version:
            raise AgentRuntimeStaleVersionError(
                "Task optimistic version mismatch.",
                context={"task_id": self.task_id, "expected_version": expected_version, "current_version": self.optimistic_version},
            )
        next_state = TaskLifecycle.transition(self.state, target)
        if next_state == self.state:
            return self
        upd: dict[str, Any] = {"state": next_state, "updated_at": _utc_now(), "optimistic_version": self.optimistic_version + 1}
        if next_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            upd["completed_at"] = _utc_now()
        return self.model_copy(update=upd)

    def record_attempt(self, *, error: str | None = None) -> AgentTask:
        return self.model_copy(update={"attempt": self.attempt + 1, "error": error, "updated_at": _utc_now(), "optimistic_version": self.optimistic_version + 1})


__all__ = ["AgentTask"]
