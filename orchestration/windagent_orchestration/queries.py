"""
Query Definitions (CQRS Read Side) for Orchestration V2.
Dataclasses representing read requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetTaskFactsQuery:
    task_id: str


@dataclass(frozen=True)
class ListSessionTasksQuery:
    session_id: str
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetWorkflowRunQuery:
    run_id: str


@dataclass(frozen=True)
class GetExecutionLeaseQuery:
    lease_id: str


@dataclass(frozen=True)
class GetWorkerStatusQuery:
    worker_id: str
