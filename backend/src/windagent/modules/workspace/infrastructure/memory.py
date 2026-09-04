"""In-memory workspace store and transaction scope for testing."""

from __future__ import annotations

import copy

from windagent.kernel.events import EventEnvelope

from ..application.ports import TransactionScope, WorkspaceStore
from ..domain.errors import WorkspaceStaleVersionError
from ..domain.models import (
    WorkspaceAggregate,
    WorkspaceLock,
    WorkspaceSnapshot,
)


class InMemoryWorkspaceStore(WorkspaceStore):
    """In-memory implementation of WorkspaceStore."""

    def __init__(
        self,
        workspaces: dict[str, WorkspaceAggregate] | None = None,
        snapshots: dict[str, list[WorkspaceSnapshot]] | None = None,
    ) -> None:
        self._workspaces: dict[str, WorkspaceAggregate] = workspaces if workspaces is not None else {}
        self._snapshots: dict[str, list[WorkspaceSnapshot]] = snapshots if snapshots is not None else {}

    async def get_by_id(self, workspace_id: str) -> WorkspaceAggregate | None:
        agg = self._workspaces.get(workspace_id)
        return copy.deepcopy(agg) if agg else None

    async def get_by_slug(self, slug: str) -> WorkspaceAggregate | None:
        for agg in self._workspaces.values():
            if agg.slug == slug:
                return copy.deepcopy(agg)
        return None

    async def list_workspaces(
        self,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkspaceAggregate]:
        res: list[WorkspaceAggregate] = []
        for agg in self._workspaces.values():
            if owner_id and agg.owner_id != owner_id:
                continue
            if status and agg.status.value != status:
                continue
            res.append(copy.deepcopy(agg))
        return res[offset : offset + limit]

    async def save(self, aggregate: WorkspaceAggregate, expected_version: int | None = None) -> None:
        ws_id = str(aggregate.id)
        existing = self._workspaces.get(ws_id)
        if existing and expected_version is not None:
            if existing.optimistic_version != expected_version:
                raise WorkspaceStaleVersionError(ws_id, expected_version, existing.optimistic_version)
        self._workspaces[ws_id] = copy.deepcopy(aggregate)

    async def delete(self, workspace_id: str) -> bool:
        if workspace_id in self._workspaces:
            del self._workspaces[workspace_id]
            return True
        return False

    async def save_snapshot(self, snapshot: WorkspaceSnapshot) -> None:
        ws_id = snapshot.workspace_id
        if ws_id not in self._snapshots:
            self._snapshots[ws_id] = []
        self._snapshots[ws_id].append(snapshot)

    async def get_latest_snapshot(self, workspace_id: str) -> WorkspaceSnapshot | None:
        snaps = self._snapshots.get(workspace_id)
        if snaps:
            return snaps[-1]
        return None

    async def list_locks(self, workspace_id: str) -> list[WorkspaceLock]:
        agg = self._workspaces.get(workspace_id)
        if not agg:
            return []
        return list(agg.locks.values())


class InMemoryTransactionScope(TransactionScope):
    """In-memory transaction scope recording outbox events."""

    def __init__(self, store: InMemoryWorkspaceStore) -> None:
        self._store = store
        self._events: list[EventEnvelope] = []
        self._committed = False

    @property
    def store(self) -> WorkspaceStore:
        return self._store

    @property
    def recorded_events(self) -> list[EventEnvelope]:
        return list(self._events)

    def record_event(self, envelope: EventEnvelope) -> None:
        self._events.append(envelope)

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        self._events.clear()

    async def __aenter__(self) -> InMemoryTransactionScope:
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            await self.rollback()


def create_in_memory_scope_factory(
    initial_workspaces: dict[str, WorkspaceAggregate] | None = None,
) -> tuple[InMemoryWorkspaceStore, type[TransactionScope]]:
    store = InMemoryWorkspaceStore(workspaces=initial_workspaces)

    def _factory() -> TransactionScope:
        return InMemoryTransactionScope(store)

    return store, _factory  # type: ignore[return-value]
