"""
Command Definitions (CQRS Write Side) for Orchestration V2.
Dataclasses representing state mutation requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CreateTaskCommand:
    task_id: str
    session_id: str
    prompt: str
    priority: int = 2  # 1=HIGH, 2=MEDIUM, 3=LOW
    project_id: Optional[str] = None
    worktree_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class TransitionTaskCommand:
    task_id: str
    session_id: str
    target_state: str
    expected_version: int
    reason: Optional[str] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CancelTaskCommand:
    task_id: str
    reason: str
    requested_by: str = "user"
    graceful: bool = True
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class StartWorkflowCommand:
    run_id: str
    workflow_id: str
    session_id: str
    task_id: str
    definition: Dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ClaimLeaseCommand:
    step_id: str
    run_id: str
    worker_id: str
    ttl_seconds: float = 30.0
    idempotency_key: str = ""


@dataclass(frozen=True)
class WorkerHeartbeatCommand:
    worker_id: str
    runtime_type: str
    active_leases: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
