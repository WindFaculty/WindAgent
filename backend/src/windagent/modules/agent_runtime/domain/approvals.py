"""Approval aggregate (Phase 13).

A task in ``WAITING_PERMISSION`` creates an ``ApprovalRecord``; resolution
unblocks the task.  State machine is small but frozen — only PENDING may
transition to terminal states and terminals are immutable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import AgentRuntimeInvalidTransitionError, AgentRuntimeValidationError


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


APPROVAL_TERMINAL: Final[frozenset[ApprovalState]] = frozenset(
    {ApprovalState.APPROVED, ApprovalState.DENIED, ApprovalState.EXPIRED}
)


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str | None = None
    requested_by: str = Field(default="system", min_length=1)
    state: ApprovalState = ApprovalState.PENDING
    payload: dict[str, Any] = Field(default_factory=dict)
    resolution: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("approval_id", "task_id", "requested_by")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeValidationError("Approval field cannot be blank.")
        return v.strip()

    def is_terminal(self) -> bool:
        return self.state in APPROVAL_TERMINAL

    def transition_to(
        self, target: ApprovalState, *, resolution: dict[str, Any] | None = None, reason: str | None = None
    ) -> ApprovalRecord:
        if self.state in APPROVAL_TERMINAL and target != self.state:
            raise AgentRuntimeInvalidTransitionError(
                f"Cannot transition terminal approval {self.state.value} -> {target.value}.",
                context={"approval_id": self.approval_id},
            )
        allowed: dict[ApprovalState, frozenset[ApprovalState]] = {
            ApprovalState.PENDING: frozenset({ApprovalState.APPROVED, ApprovalState.DENIED, ApprovalState.EXPIRED}),
            ApprovalState.APPROVED: frozenset(),
            ApprovalState.DENIED: frozenset(),
            ApprovalState.EXPIRED: frozenset(),
        }
        if target != self.state and target not in allowed[self.state]:
            raise AgentRuntimeInvalidTransitionError(
                f"Illegal approval transition {self.state.value} -> {target.value}.",
                context={"approval_id": self.approval_id},
            )
        upd: dict[str, Any] = {"state": target}
        if target in APPROVAL_TERMINAL:
            upd["resolved_at"] = datetime.now(UTC)
            if resolution is not None:
                upd["resolution"] = dict(resolution)
            if reason is not None:
                merged = dict(self.resolution)
                merged["reason"] = reason
                upd["resolution"] = merged
        return self.model_copy(update=upd)


__all__ = ["APPROVAL_TERMINAL", "ApprovalRecord", "ApprovalState"]
