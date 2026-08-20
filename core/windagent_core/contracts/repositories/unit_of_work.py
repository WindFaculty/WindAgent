"""Unit of Work ports for WindAgent Core (Phase 3 — Dependency Inversion).

Application-layer orchestration/memory services depend ONLY on these ports.
Concrete transactional boundaries (``SqlUnitOfWork``, ``StudioUnitOfWork``)
live in storage and are injected by composition roots as a factory callable.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.contracts.repositories.cancellation_repository import (
    CancellationRepositoryPort,
)
from windagent_core.contracts.repositories.checkpoint_repository import (
    CheckpointRepositoryPort,
)
from windagent_core.contracts.repositories.event_store import (
    EventStorePort,
)
from windagent_core.contracts.repositories.lease_repository import (
    LeaseRepositoryPort,
)
from windagent_core.contracts.repositories.recovery_leader_repository import (
    RecoveryLeaderLeaseRepositoryPort,
)
from windagent_core.contracts.repositories.runtime_execution_repository import (
    RuntimeExecutionRepositoryPort,
)
from windagent_core.contracts.repositories.task_repository import (
    TaskRunRepositoryPort,
)
from windagent_core.contracts.finalization import (
    FinalizeTaskExecutionRequest,
    FinalizeTaskExecutionResult,
)
from windagent_core.events.envelope import EventEnvelope


@runtime_checkable
class UnitOfWorkPort(Protocol):
    """Transactional boundary exposing the repository surface orchestration needs.

    Concrete implementations (SqlUnitOfWork) additionally expose the raw
    session/ORM for storage-layer internal use; application code must only rely
    on the attributes declared here.
    """

    # Repository surfaces consumed by orchestration services.
    leases: LeaseRepositoryPort
    cancellations: CancellationRepositoryPort
    runtime_executions: RuntimeExecutionRepositoryPort
    events: EventStorePort
    task_runs: TaskRunRepositoryPort
    checkpoints: CheckpointRepositoryPort
    recovery_leader_leases: RecoveryLeaderLeaseRepositoryPort
    session: Any  # opaque; application code must not issue raw SQL

    async def list_non_terminal_task_runs(self, batch_size: int) -> List[Dict[str, Any]]:
        """Return non-terminal task runs as plain dicts (recovery scans)."""

    async def list_in_flight_steps(self, batch_size: int) -> List[Dict[str, Any]]:
        """Return in-flight workflow step runs as plain dicts (recovery scans)."""

    async def set_step_state(
        self, step_id: str, state: str, error: Optional[str] = None
    ) -> None:
        """Persist a reconciled workflow step state (recovery scans)."""

    async def record_outbox_event(self, event: EventEnvelope) -> None:
        ...

    async def finalize_task_execution(
        self, request: FinalizeTaskExecutionRequest
    ) -> FinalizeTaskExecutionResult:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...

    async def __aenter__(self) -> "UnitOfWorkPort":
        ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...


@runtime_checkable
class SqlUnitOfWorkPort(UnitOfWorkPort, Protocol):
    """Union port satisfied by the SQL transaction boundary (SqlUnitOfWork)."""

    pass


@runtime_checkable
class StudioUnitOfWorkPort(Protocol):
    """Transactional Studio boundary used by StudioRunService."""

    session: Any
    series: Any
    episodes: Any
    revisions: Any
    artifacts: Any
    approvals: Any
    runs: Any
    nodes: Any
    events: Any

    async def append_event(self, event: Any) -> None:
        ...

    async def publish_outbox(self, event: Any) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...

    async def __aenter__(self) -> "StudioUnitOfWorkPort":
        ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...


UnitOfWorkFactory = Callable[[], UnitOfWorkPort]
StudioUnitOfWorkFactory = Callable[[], StudioUnitOfWorkPort]


__all__ = [
    "UnitOfWorkPort",
    "SqlUnitOfWorkPort",
    "StudioUnitOfWorkPort",
    "UnitOfWorkFactory",
    "StudioUnitOfWorkFactory",
]