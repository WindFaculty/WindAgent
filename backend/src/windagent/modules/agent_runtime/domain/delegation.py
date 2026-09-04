"""Delegation aggregate (Phase 13).

Parent run delegates a sub-problem to a child run.  Delegation is
immutable once created except for terminal status update.  Child limits are
inherited component-wise minimum (see ``budget.inherit_limits``) — domain does
not enforce inheritance here, it only validates structural invariants.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import AgentRuntimeDelegationError, AgentRuntimeValidationError


class DelegationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_DELEGATION_TERMINAL: frozenset[DelegationStatus] = frozenset(
    {DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.CANCELLED}
)


class DelegationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    delegation_id: str = Field(min_length=1)
    parent_run_id: str = Field(min_length=1)
    child_run_id: str = Field(min_length=1)
    status: DelegationStatus = DelegationStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("delegation_id", "parent_run_id", "child_run_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise AgentRuntimeValidationError("Delegation field cannot be blank.")
        return v.strip()

    @field_validator("child_run_id")
    @classmethod
    def _not_self(cls, v: str, info: Any) -> str:
        parent = (info.data.get("parent_run_id") or "") if isinstance(info.data, dict) else ""
        if parent and v == parent:
            raise AgentRuntimeDelegationError("Delegation parent and child cannot be identical.", context={"parent_run_id": parent})
        return v

    def is_terminal(self) -> bool:
        return self.status in _DELEGATION_TERMINAL

    def transition_to(self, target: DelegationStatus) -> DelegationRecord:
        allowed: dict[DelegationStatus, frozenset[DelegationStatus]] = {
            DelegationStatus.PENDING: frozenset({DelegationStatus.RUNNING, DelegationStatus.CANCELLED}),
            DelegationStatus.RUNNING: frozenset({DelegationStatus.COMPLETED, DelegationStatus.FAILED, DelegationStatus.CANCELLED}),
            DelegationStatus.COMPLETED: frozenset(),
            DelegationStatus.FAILED: frozenset(),
            DelegationStatus.CANCELLED: frozenset(),
        }
        if target != self.status and target not in allowed[self.status]:
            raise AgentRuntimeDelegationError(
                f"Illegal delegation transition {self.status.value} -> {target.value}.",
                context={"delegation_id": self.delegation_id},
            )
        if self.status in _DELEGATION_TERMINAL and target != self.status:
            raise AgentRuntimeDelegationError(
                f"Cannot transition terminal delegation {self.status.value} -> {target.value}.",
                context={"delegation_id": self.delegation_id},
            )
        upd: dict[str, Any] = {"status": target}
        if target in _DELEGATION_TERMINAL:
            upd["completed_at"] = datetime.now(UTC)
        return self.model_copy(update=upd)


__all__ = ["DelegationRecord", "DelegationStatus"]
