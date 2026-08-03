"""
Pure Python Domain Models for WindAgent Architecture V2.
Encapsulates domain entities, value objects, invariants, and state transitions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import (
    TaskId, RunId, SessionId, WorkflowId, StepId,
    ModelCallId, ArtifactId
)


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class Session:
    id: SessionId
    created_at: datetime = field(default_factory=default_utc_now)
    updated_at: datetime = field(default_factory=default_utc_now)
    status: SessionStatus = SessionStatus.IDLE
    title: Optional[str] = None
    agent_id: Optional[str] = None
    workspace_root: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition_to(self, new_status: SessionStatus) -> None:
        self.status = new_status
        self.updated_at = default_utc_now()


@dataclass
class TaskRequest:
    prompt: str
    session_id: Optional[SessionId] = None
    agent_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt or not self.prompt.strip():
            raise ValueError("TaskRequest prompt cannot be empty.")


@dataclass
class Task:
    id: TaskId
    prompt: str
    session_id: SessionId
    created_at: datetime = field(default_factory=default_utc_now)
    status: SessionStatus = SessionStatus.PENDING
    tags: List[str] = field(default_factory=list)


@dataclass
class TaskRun:
    run_id: RunId
    task_id: TaskId
    session_id: SessionId
    started_at: datetime = field(default_factory=default_utc_now)
    ended_at: Optional[datetime] = None
    status: SessionStatus = SessionStatus.RUNNING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class WorkflowStep:
    id: StepId
    order: int
    name: str
    tool_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError("WorkflowStep order must be >= 1.")
        if not self.name or not self.name.strip():
            raise ValueError("WorkflowStep name cannot be empty.")


@dataclass
class WorkflowDefinition:
    id: WorkflowId
    name: str
    description: str
    steps: List[WorkflowStep] = field(default_factory=list)
    version: str = "1.0.0"


@dataclass
class WorkflowRun:
    run_id: RunId
    workflow_id: WorkflowId
    session_id: SessionId
    created_at: datetime = field(default_factory=default_utc_now)
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: List[WorkflowStep] = field(default_factory=list)


@dataclass
class ModelRequest:
    id: ModelCallId
    model: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.model or not self.model.strip():
            raise ValueError("ModelRequest model cannot be empty.")


@dataclass
class ModelResponse:
    id: ModelCallId
    model: str
    content: str
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=default_utc_now)


@dataclass
class ArtifactRef:
    id: ArtifactId
    name: str
    mime_type: str
    uri: str
    size_bytes: int = 0
    created_at: datetime = field(default_factory=default_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionRequest:
    id: str
    action: str
    target: str
    tool_name: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class VerificationResult:
    passed: bool
    score: float = 1.0
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
