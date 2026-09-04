"""Immutable Agent Runtime queries."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

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


@dataclass(frozen=True, slots=True)
class GetSession(Query[SessionView]):
    session_id: str


@dataclass(frozen=True, slots=True)
class ListSessions(Query[tuple[SessionView, ...]]):
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetRun(Query[RunView]):
    run_id: str


@dataclass(frozen=True, slots=True)
class ListRuns(Query[tuple[RunView, ...]]):
    session_id: str | None = None
    parent_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetTask(Query[TaskView]):
    task_id: str


@dataclass(frozen=True, slots=True)
class ListTasks(Query[tuple[TaskView, ...]]):
    session_id: str | None = None
    run_id: str | None = None
    workflow_id: str | None = None
    state: str | None = None


@dataclass(frozen=True, slots=True)
class GetWorkflow(Query[WorkflowView]):
    workflow_id: str


@dataclass(frozen=True, slots=True)
class ListWorkflows(Query[tuple[WorkflowView, ...]]):
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetStep(Query[StepView]):
    step_id: str


@dataclass(frozen=True, slots=True)
class ListSteps(Query[tuple[StepView, ...]]):
    workflow_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetCheckpoint(Query[CheckpointView]):
    checkpoint_id: str


@dataclass(frozen=True, slots=True)
class ListCheckpoints(Query[tuple[CheckpointView, ...]]):
    run_id: str | None = None
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetApproval(Query[ApprovalView]):
    approval_id: str


@dataclass(frozen=True, slots=True)
class ListApprovals(Query[tuple[ApprovalView, ...]]):
    task_id: str | None = None
    state: str | None = None


@dataclass(frozen=True, slots=True)
class GetDelegation(Query[DelegationView]):
    delegation_id: str


@dataclass(frozen=True, slots=True)
class ListDelegations(Query[tuple[DelegationView, ...]]):
    parent_run_id: str | None = None
    child_run_id: str | None = None
