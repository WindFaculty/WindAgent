"""Immutable Agent Runtime commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from windagent.platform.commands import Command

from .models import (
    ApprovalView,
    CheckpointView,
    DelegationView,
    RunView,
    SessionView,
    StepView,
    TaskView,
    WorkflowView,
)

# -- sessions ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateSession(Command[SessionView]):
    actor_id: str = "system"
    title: str = "Untitled session"
    budget_limits: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionSession(Command[SessionView]):
    session_id: str
    target_state: str
    expected_version: int | None = None


# -- runs --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateRun(Command[RunView]):
    session_id: str
    parent_run_id: str | None = None
    budget_scope: str = "conversation"
    budget_limits: dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 3
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionRun(Command[RunView]):
    run_id: str
    target_state: str
    expected_version: int | None = None
    exhaustion_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RecordRunBudgetUsage(Command[RunView]):
    run_id: str
    usage_patch: dict[str, Any] = field(default_factory=dict)
    expected_version: int | None = None


# -- tasks -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateTask(Command[TaskView]):
    session_id: str
    title: str
    description: str = ""
    run_id: str | None = None
    workflow_id: str | None = None
    priority: int = 0
    max_attempts: int = 3
    timeout_seconds: float | None = None
    input_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionTask(Command[TaskView]):
    task_id: str
    target_state: str
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class CompleteTask(Command[TaskView]):
    task_id: str
    output_payload: dict[str, Any] = field(default_factory=dict)
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class FailTask(Command[TaskView]):
    task_id: str
    error: str = ""
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class RetryTask(Command[TaskView]):
    task_id: str
    expected_version: int | None = None


# -- workflows ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateWorkflow(Command[WorkflowView]):
    session_id: str
    name: str
    nodes: dict[str, Any] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionWorkflow(Command[WorkflowView]):
    workflow_id: str
    target_state: str
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduleWorkflow(Command[WorkflowView]):
    workflow_id: str
    run_id: str
    expected_version: int | None = None


# -- steps -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransitionStep(Command[StepView]):
    step_id: str
    target_state: str
    expected_version: int | None = None


# -- checkpoints -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateCheckpoint(Command[CheckpointView]):
    run_id: str
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    task_id: str | None = None
    workflow_id: str | None = None
    step_id: str | None = None
    seq: int | None = None


# -- approvals ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestApproval(Command[ApprovalView]):
    task_id: str
    requested_by: str = "system"
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    expires_in_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ResolveApproval(Command[ApprovalView]):
    approval_id: str
    target_state: str
    resolution: dict[str, Any] = field(default_factory=dict)


# -- delegations -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DelegateRun(Command[DelegationView]):
    parent_run_id: str
    child_run_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionDelegation(Command[DelegationView]):
    delegation_id: str
    target_status: str
