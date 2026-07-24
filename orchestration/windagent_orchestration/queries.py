"""
Query Definitions (CQRS Read Side) for WindAgent Orchestration V2 (Phase 8 Adoption).
Dataclasses representing read requests using canonical domain IDs.
"""

from __future__ import annotations
from dataclasses import dataclass
from windagent_core.domain.types import TaskId, SessionId, WorkflowRunId, WorkerId


@dataclass(frozen=True)
class GetTaskFactsQuery:
    task_id: TaskId


@dataclass(frozen=True)
class ListSessionTasksQuery:
    session_id: SessionId
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetWorkflowRunQuery:
    run_id: WorkflowRunId


@dataclass(frozen=True)
class GetExecutionLeaseQuery:
    lease_id: str


@dataclass(frozen=True)
class GetWorkerStatusQuery:
    worker_id: WorkerId
