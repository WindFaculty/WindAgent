"""
Command Definitions (CQRS Write Side) for WindAgent Orchestration V2 (Phase 8 Adoption).
Typed dataclasses representing state mutation requests using canonical domain IDs and states.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import (
    TaskId, SessionId, WorkflowId, WorkflowRunId, StepId, WorkerId
)
from windagent_core.domain.lifecycle import TaskState, utc_now


@dataclass(frozen=True)
class CreateTaskCommand:
    task_id: TaskId
    session_id: SessionId
    prompt: str
    priority: int = 2  # 1=HIGH, 2=MEDIUM, 3=LOW
    project_id: Optional[str] = None
    worktree_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class TransitionTaskCommand:
    task_id: TaskId
    session_id: SessionId
    target_state: TaskState
    expected_version: int
    reason: Optional[str] = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class CancelTaskCommand:
    task_id: TaskId
    reason: str
    requested_by: str = "user"
    graceful: bool = True
    requested_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class StartWorkflowCommand:
    run_id: WorkflowRunId
    workflow_id: WorkflowId
    session_id: SessionId
    task_id: TaskId
    definition: Dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ClaimLeaseCommand:
    step_id: StepId
    run_id: WorkflowRunId
    worker_id: WorkerId
    ttl_seconds: float = 30.0
    idempotency_key: str = ""


@dataclass(frozen=True)
class WorkerHeartbeatCommand:
    worker_id: WorkerId
    runtime_type: str
    active_leases: int = 0
    timestamp: datetime = field(default_factory=utc_now)
