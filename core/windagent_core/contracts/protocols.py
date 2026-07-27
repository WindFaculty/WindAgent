"""
Contract Ports (Protocols) for WindAgent Architecture V2 (Phase 4 Canonical Contracts).
Defines abstract interfaces for storage, transactional unit of work, execution runtimes,
model gateways, security, secret management, auditing, and time abstractions.
Pure Python protocols with zero framework dependencies.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.domain.types import (
    TaskId, TaskRunId, SessionId, WorkflowId, WorkflowRunId, StepId, StepRunId, ArtifactId
)
from windagent_core.domain.models import (
    Task, TaskRun, Session, WorkflowDefinition, WorkflowRun, WorkflowStep, ArtifactRef,
    ModelRequest, ModelResponse
)
from windagent_core.events.envelope import EventEnvelope
from windagent_core.security.types import (
    PermissionEvaluationRequest, PermissionDecision, SecretRef, SecretName, SecretValue
)


@runtime_checkable
class Clock(Protocol):
    """Protocol for time abstraction."""
    def now(self) -> datetime:
        ...


@runtime_checkable
class AsyncCloseablePort(Protocol):
    """Lifecycle protocol for services requiring asynchronous resource cleanup."""
    async def close(self) -> None:
        ...


@runtime_checkable
class IdGenerator(Protocol):
    """Protocol for generating entity identifiers."""
    def generate_id(self) -> str:
        ...


@runtime_checkable
class TaskRepository(Protocol):
    """Protocol for persisting and retrieving Task domain entities."""
    async def get_by_id(self, task_id: TaskId) -> Optional[Task]:
        ...

    async def save(self, task: Task) -> None:
        ...

    async def list_by_session(self, session_id: SessionId) -> List[Task]:
        ...


@runtime_checkable
class TaskRunRepository(Protocol):
    """Protocol for persisting and retrieving TaskRun execution instances."""
    async def get_by_id(self, run_id: TaskRunId) -> Optional[TaskRun]:
        ...

    async def save(self, task_run: TaskRun) -> None:
        ...


@runtime_checkable
class SessionRepository(Protocol):
    """Protocol for persisting and retrieving Session domain entities."""
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
    """Protocol for persisting and retrieving Workflow definitions."""
    async def get_by_id(self, workflow_id: WorkflowId) -> Optional[WorkflowDefinition]:
        ...

    async def save(self, workflow: WorkflowDefinition) -> None:
        ...


@runtime_checkable
class WorkflowRunRepository(Protocol):
    """Protocol for persisting and retrieving WorkflowRun execution instances."""
    async def get_by_id(self, run_id: WorkflowRunId) -> Optional[WorkflowRun]:
        ...

    async def save(self, workflow_run: WorkflowRun) -> None:
        ...


@runtime_checkable
class WorkRepository(Protocol):
    """Protocol for persisting and retrieving Work submissions."""
    async def submit(self, work: WorkSubmission) -> None:
        ...

    async def get(self, task_id: TaskId) -> Optional[WorkSubmission]:
        ...

    async def claim(self, task_id: TaskId, worker_id: str, lease_seconds: int = 300) -> bool:
        ...

    async def complete(self, task_id: TaskId, result: Optional[dict] = None, error: Optional[str] = None) -> None:
        ...

    async def list_pending(self, limit: int = 100) -> List[WorkSubmission]:
        ...


@runtime_checkable
class EventStore(Protocol):
    """Protocol for append-only domain event persistence."""
    async def append(self, event: EventEnvelope) -> None:
        ...

    async def get_events(self, stream_id: str, after_sequence: int = 0, limit: int = 100) -> List[EventEnvelope]:
        ...


@runtime_checkable
class OutboxWriter(Protocol):
    """Protocol for transactional outbox event storage."""
    async def write(self, event: EventEnvelope) -> None:
        ...


@runtime_checkable
class EventPublisher(Protocol):
    """Protocol for publishing domain events to message buses / subscribers."""
    async def publish(self, event: EventEnvelope) -> None:
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
    """Protocol for transactional atomicity across domain repositories."""
    tasks: TaskRepository
    task_runs: TaskRunRepository
    workflows: WorkflowRepository
    workflow_runs: WorkflowRunRepository
    events: EventStore
    outbox: OutboxWriter

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...

    async def __aenter__(self) -> UnitOfWork:
        ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...


@runtime_checkable
class ExecutionRuntimePort(Protocol):
    """Abstraction for execution runtime engines (Hermes, workers, local agents)."""
    async def dispatch(self, step_run_id: StepRunId, payload: Dict[str, Any]) -> None:
        ...

    async def cancel(self, step_run_id: StepRunId) -> None:
        ...

    async def heartbeat(self, step_run_id: StepRunId) -> None:
        ...


@runtime_checkable
class ModelGatewayPort(Protocol):
    """Abstraction for LLM model provider execution and streaming."""
    async def execute(self, request: ModelRequest) -> ModelResponse:
        ...


@runtime_checkable
class SecretStore(Protocol):
    """Protocol for secure secret storage and resolution."""
    async def resolve(self, ref: SecretRef) -> SecretValue:
        ...

    async def store(self, name: SecretName, value: SecretValue) -> SecretRef:
        ...

    async def delete(self, ref: SecretRef) -> None:
        ...


@runtime_checkable
class PermissionEvaluator(Protocol):
    """Protocol for evaluating security policies and permission requests."""
    async def evaluate(self, request: PermissionEvaluationRequest) -> PermissionDecision:
        ...


@runtime_checkable
class AuditSink(Protocol):
    """Protocol for logging security and operational audit records."""
    async def record_audit(self, event_type: str, details: Dict[str, Any]) -> None:
        ...
