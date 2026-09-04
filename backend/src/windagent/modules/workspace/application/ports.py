"""Persistence and transaction scope ports for Workspace."""

from __future__ import annotations

from typing import Protocol, Self, runtime_checkable

from windagent.kernel.events import EventEnvelope

from ..domain.models import (
    WorkspaceAggregate,
    WorkspaceLock,
    WorkspaceSnapshot,
)


@runtime_checkable
class WorkspaceStore(Protocol):
    """Repository port for persisting and querying workspaces."""

    async def get_by_id(self, workspace_id: str) -> WorkspaceAggregate | None:
        """Fetch full aggregate by primary ID."""

    async def get_by_slug(self, slug: str) -> WorkspaceAggregate | None:
        """Fetch full aggregate by slug."""

    async def list_workspaces(
        self,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkspaceAggregate]:
        """List workspaces with optional filtering."""

    async def save(self, aggregate: WorkspaceAggregate, expected_version: int | None = None) -> None:
        """Persist aggregate with optimistic concurrency check."""

    async def delete(self, workspace_id: str) -> bool:
        """Delete workspace record."""

    async def save_snapshot(self, snapshot: WorkspaceSnapshot) -> None:
        """Persist a point-in-time snapshot."""

    async def get_latest_snapshot(self, workspace_id: str) -> WorkspaceSnapshot | None:
        """Fetch most recent snapshot."""

    async def list_locks(self, workspace_id: str) -> list[WorkspaceLock]:
        """List active locks in a workspace."""


@runtime_checkable
class TransactionScope(Protocol):
    """Context boundary for atomic store operations and outbox events."""

    @property
    def store(self) -> WorkspaceStore:
        """Access the scoped workspace store."""

    def record_event(self, envelope: EventEnvelope) -> None:
        """Queue an outbox event to be atomically committed."""

    async def commit(self) -> None:
        """Commit store mutations and recorded outbox events."""

    async def rollback(self) -> None:
        """Rollback uncommitted mutations."""

    async def __aenter__(self) -> Self:
        """Enter transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool | None:
        """Exit transaction scope."""
