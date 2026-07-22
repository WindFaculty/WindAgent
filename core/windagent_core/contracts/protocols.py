"""
Contract Ports (Protocols) for WindAgent Architecture V2.
Defines abstract interfaces for storage, eventing, repositories, security, and time.
Pure Python protocols with zero framework dependencies.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.domain.types import (
    TaskId, RunId, SessionId, WorkflowId, StepId, ArtifactId
)
from windagent_core.domain.models import (
    Task, Session, WorkflowRun, ArtifactRef, PermissionRequest
)


@runtime_checkable
class Clock(Protocol):
    """Protocol for time abstraction."""
    def now(self) -> datetime:
        ...


@runtime_checkable
class IdGenerator(Protocol):
    """Protocol for generating entity identifiers."""
    def generate_id(self) -> str:
        ...


@runtime_checkable
class TaskRepository(Protocol):
    """Protocol for persisting and retrieving Task entities."""
    async def get_by_id(self, task_id: TaskId) -> Optional[Task]:
        ...

    async def save(self, task: Task) -> None:
        ...

    async def list_by_session(self, session_id: SessionId) -> List[Task]:
        ...


@runtime_checkable
class SessionRepository(Protocol):
    """Protocol for persisting and retrieving Session entities."""
    async def get_by_id(self, session_id: SessionId) -> Optional[Session]:
        ...

    async def save(self, session: Session) -> None:
        ...

    async def delete(self, session_id: SessionId) -> bool:
        ...

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        ...


@runtime_checkable
class WorkflowRepository(Protocol):
    """Protocol for persisting and retrieving Workflow runs."""
    async def get_by_id(self, run_id: RunId) -> Optional[WorkflowRun]:
        ...

    async def save(self, run: WorkflowRun) -> None:
        ...


@runtime_checkable
class EventStore(Protocol):
    """Protocol for append-only domain event persistence."""
    async def append_event(self, event_type: str, payload: Dict[str, Any], sequence: Optional[int] = None) -> int:
        ...

    async def get_events(self, after_sequence: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        ...


@runtime_checkable
class EventPublisher(Protocol):
    """Protocol for publishing domain events."""
    async def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        ...


@runtime_checkable
class ArtifactRepository(Protocol):
    """Protocol for artifact storage and metadata tracking."""
    async def store(self, name: str, data: bytes, mime_type: str) -> ArtifactRef:
        ...

    async def get_by_id(self, artifact_id: ArtifactId) -> Optional[ArtifactRef]:
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Protocol for transactional atomicity across repositories."""
    async def __aenter__(self) -> UnitOfWork:
        ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...


@runtime_checkable
class SecretStore(Protocol):
    """Protocol for secure secret storage and retrieval."""
    async def get_secret(self, key: str) -> Optional[str]:
        ...

    async def set_secret(self, key: str, value: str) -> None:
        ...


@runtime_checkable
class PermissionEvaluator(Protocol):
    """Protocol for evaluating tool and action permissions."""
    async def evaluate(self, request: PermissionRequest) -> bool:
        ...
