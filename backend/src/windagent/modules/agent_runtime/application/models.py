"""Application view models and durable row types for Agent Runtime.

Rows are transport-neutral storage shapes; views are the application surface
returned through the command/query buses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Durable rows (1:1 with tables)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SessionRow:
    session_id: str
    actor_id: str
    title: str
    state: str
    budget_limits_json: str
    budget_usage_json: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class RunRow:
    run_id: str
    session_id: str
    parent_run_id: str | None
    state: str
    budget_scope: str
    budget_limits_json: str
    budget_usage_json: str
    exhaustion_reason: str | None
    attempt: int
    max_attempts: int
    timeout_seconds: float | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class TaskRow:
    task_id: str
    session_id: str
    run_id: str | None
    workflow_id: str | None
    title: str
    description: str
    state: str
    priority: int
    attempt: int
    max_attempts: int
    timeout_seconds: float | None
    input_payload_json: str
    output_payload_json: str | None
    error: str | None
    awaiting_approval_id: str | None
    checkpoint_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class WorkflowRow:
    workflow_id: str
    session_id: str
    name: str
    version: int
    state: str
    nodes_json: str
    edges_json: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class StepRow:
    step_id: str
    workflow_id: str
    run_id: str | None
    task_id: str | None
    node_id: str
    state: str
    attempt: int
    max_attempts: int
    priority: int
    result_json: str | None
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int


@dataclass(frozen=True, slots=True)
class CheckpointRow:
    checkpoint_id: str
    run_id: str
    task_id: str | None
    workflow_id: str | None
    step_id: str | None
    seq: int
    state_snapshot_json: str
    snapshot_hash: str
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class ApprovalRow:
    approval_id: str
    task_id: str
    run_id: str | None
    requested_by: str
    state: str
    payload_json: str
    resolution_json: str | None
    created_at: datetime | None
    resolved_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class DelegationRow:
    delegation_id: str
    parent_run_id: str
    child_run_id: str
    status: str
    created_at: datetime | None
    completed_at: datetime | None
    metadata_json: str


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: str
    actor_id: str
    title: str
    state: str
    budget_limits: dict[str, Any]
    budget_usage: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "actor_id": self.actor_id,
            "title": self.title,
            "state": self.state,
            "budget_limits": self.budget_limits,
            "budget_usage": self.budget_usage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class RunView:
    run_id: str
    session_id: str
    parent_run_id: str | None
    state: str
    budget_scope: str
    budget_limits: dict[str, Any]
    budget_usage: dict[str, Any]
    exhaustion_reason: str | None
    attempt: int
    max_attempts: int
    timeout_seconds: float | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "parent_run_id": self.parent_run_id,
            "state": self.state,
            "budget_scope": self.budget_scope,
            "budget_limits": self.budget_limits,
            "budget_usage": self.budget_usage,
            "exhaustion_reason": self.exhaustion_reason,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class TaskView:
    task_id: str
    session_id: str
    run_id: str | None
    workflow_id: str | None
    title: str
    description: str
    state: str
    priority: int
    attempt: int
    max_attempts: int
    timeout_seconds: float | None
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    error: str | None
    awaiting_approval_id: str | None
    checkpoint_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "title": self.title,
            "description": self.description,
            "state": self.state,
            "priority": self.priority,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "timeout_seconds": self.timeout_seconds,
            "input_payload": self.input_payload,
            "output_payload": self.output_payload,
            "error": self.error,
            "awaiting_approval_id": self.awaiting_approval_id,
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class WorkflowView:
    workflow_id: str
    session_id: str
    name: str
    version: int
    state: str
    nodes: dict[str, Any]
    edges: list[dict[str, Any]]
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "name": self.name,
            "version": self.version,
            "state": self.state,
            "nodes": self.nodes,
            "edges": self.edges,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class StepView:
    step_id: str
    workflow_id: str
    run_id: str | None
    task_id: str | None
    node_id: str
    state: str
    attempt: int
    max_attempts: int
    priority: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "state": self.state,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "priority": self.priority,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
        }


@dataclass(frozen=True, slots=True)
class CheckpointView:
    checkpoint_id: str
    run_id: str
    task_id: str | None
    workflow_id: str | None
    step_id: str | None
    seq: int
    state_snapshot: dict[str, Any]
    snapshot_hash: str
    created_at: datetime | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "seq": self.seq,
            "state_snapshot": self.state_snapshot,
            "snapshot_hash": self.snapshot_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass(frozen=True, slots=True)
class ApprovalView:
    approval_id: str
    task_id: str
    run_id: str | None
    requested_by: str
    state: str
    payload: dict[str, Any]
    resolution: dict[str, Any] | None
    created_at: datetime | None
    resolved_at: datetime | None
    expires_at: datetime | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "requested_by": self.requested_by,
            "state": self.state,
            "payload": self.payload,
            "resolution": self.resolution,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(frozen=True, slots=True)
class DelegationView:
    delegation_id: str
    parent_run_id: str
    child_run_id: str
    status: str
    created_at: datetime | None
    completed_at: datetime | None
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "parent_run_id": self.parent_run_id,
            "child_run_id": self.child_run_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }
