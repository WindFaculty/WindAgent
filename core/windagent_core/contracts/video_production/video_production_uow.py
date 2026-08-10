"""
Video Production Unit-of-Work port for core application services.

Plan A A1 boundary repair: core application services depend on this provider-
neutral port instead of the concrete storage ``VideoProductionUnitOfWork``.
The SQL adapter in ``windagent_storage`` implements this surface structurally;
core never imports storage.

Only the repository surface actually consumed by core services is declared.
Anything added here is a contract change and must remain storage-neutral.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProjectRepositoryPort(Protocol):
    """Project and revision persistence surface used by core services."""

    async def get_project(self, project_id: str) -> dict[str, Any] | None: ...

    async def save_project(
        self, project_id: str, name: str, status: str, active_revision_id: str
    ) -> dict[str, Any]: ...

    async def get_revision(self, revision_id: str) -> dict[str, Any] | None: ...

    async def save_revision(
        self,
        revision_id: str,
        project_id: str,
        parent_revision_id: str | None,
        status: str,
        content_hash: str,
        sequence: int,
    ) -> dict[str, Any]: ...


@runtime_checkable
class EventRepositoryPort(Protocol):
    """Production domain event persistence surface used by core services."""

    async def append_event(
        self,
        event_id: str,
        sequence: int,
        project_id: str,
        revision_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def get_max_sequence(self, project_id: str | None = None) -> int: ...


@runtime_checkable
class IdempotencyRepositoryPort(Protocol):
    """Idempotency record surface used by core command services."""

    async def get_record(self, scope: str, idempotency_key: str) -> dict[str, Any] | None: ...

    async def save_record(
        self,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, Any],
        status: str = "COMPLETED",
        expires_at: datetime | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class ReadModelRepositoryPort(Protocol):
    """Workspace read-model projection surface used by core query services."""

    async def get_read_model(self, project_id: str) -> dict[str, Any] | None: ...

    async def save_read_model(
        self, project_id: str, projection: dict[str, Any], current_sequence: int
    ) -> None: ...


@runtime_checkable
class VideoProductionUnitOfWorkPort(Protocol):
    """Transactional boundary for Video Production API V2 operations.

    Implemented by ``windagent_storage.unit_of_work.video_production_uow.
    VideoProductionUnitOfWork``. Core services type against this port so the
    package graph stays core -> contracts only.
    """

    projects: ProjectRepositoryPort
    idempotency: IdempotencyRepositoryPort
    events: EventRepositoryPort
    read_models: ReadModelRepositoryPort

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
