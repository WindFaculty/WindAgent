"""In-memory Memory store and transaction scope for unit tests (Phase 14)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from windagent.kernel.events import EventEnvelope

from ..application.models import MemoryRecordRow
from ..application.ports import MemoryStore
from ..domain.errors import MemoryConflictError, MemoryNotFoundError, MemoryStaleVersionError
from ..domain.models import MemoryRecord
from ..domain.scope import MemoryScope


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class InMemoryMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self.records: dict[str, MemoryRecordRow] = {}
        self.events: list[EventEnvelope] = []

    async def get(
        self,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> MemoryRecordRow | None:
        for r in self.records.values():
            if (
                r.scope == scope
                and r.key == key
                and r.project_id == project_id
                and r.session_id == session_id
            ):
                return r
        return None

    async def get_by_id(self, memory_id: str) -> MemoryRecordRow | None:
        return self.records.get(memory_id)

    async def get_by_hash(self, content_hash: str) -> MemoryRecordRow | None:
        for r in self.records.values():
            if r.content_hash == content_hash:
                return r
        return None

    async def insert(self, row: MemoryRecordRow) -> MemoryRecordRow:
        if row.memory_id in self.records:
            raise MemoryConflictError(f"Memory record already exists: {row.memory_id}")
        self.records[row.memory_id] = row
        return row

    async def update(self, row: MemoryRecordRow, expected_version: int) -> MemoryRecordRow:
        existing = self.records.get(row.memory_id)
        if existing is None:
            raise MemoryNotFoundError(f"Memory record not found: {row.memory_id}")
        if existing.optimistic_version != expected_version:
            raise MemoryStaleVersionError(
                f"Memory record conflict for {row.memory_id}: expected {expected_version}, got {existing.optimistic_version}"
            )
        self.records[row.memory_id] = row
        return row

    async def delete(self, memory_id: str) -> bool:
        return self.records.pop(memory_id, None) is not None

    async def delete_by_scope_key(
        self,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        existing = await self.get(scope, key, project_id, session_id)
        if existing is None:
            return False
        return await self.delete(existing.memory_id)

    async def list_records(
        self,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecordRow]:
        matched: list[MemoryRecordRow] = []
        for r in self.records.values():
            if scope is not None and r.scope != scope:
                continue
            if project_id is not None and r.project_id != project_id:
                continue
            if session_id is not None and r.session_id != session_id:
                continue
            matched.append(r)

        matched.sort(
            key=lambda r: r.updated_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return matched[offset : offset + limit]

    async def count_by_scope(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.records.values():
            counts[r.scope] = counts.get(r.scope, 0) + 1
        return counts

    async def evict_expired(
        self,
        reference_time: datetime | None = None,
        scope: str | None = None,
    ) -> int:
        ref = reference_time or datetime.now(UTC)
        to_delete: list[str] = []
        for r in self.records.values():
            if scope is not None and r.scope != scope:
                continue
            try:
                scope_enum = MemoryScope(r.scope)
            except ValueError:
                scope_enum = MemoryScope.WORKING
            rec = MemoryRecord(
                id=r.memory_id,
                scope=scope_enum,
                key=r.key,
                value=None,
                provenance_source=r.provenance_source,
                ttl_seconds=r.ttl_seconds,
                created_at=r.created_at or ref,
                updated_at=r.updated_at or ref,
            )
            if rec.is_expired(reference_time=ref):
                to_delete.append(r.memory_id)

        for mem_id in to_delete:
            self.records.pop(mem_id, None)

        return len(to_delete)


class InMemoryTransactionScope:
    def __init__(self, store: InMemoryMemoryStore) -> None:
        self._store = store
        self._pending_events: list[EventEnvelope] = []

    async def __aenter__(self) -> InMemoryTransactionScope:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        return False

    @property
    def store(self) -> MemoryStore:
        return self._store

    async def record_event(self, event: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        self._pending_events.append(event)
        return True

    async def commit(self) -> None:
        self._store.events.extend(self._pending_events)
        self._pending_events = []

    async def rollback(self) -> None:
        self._pending_events = []


def memory_scope_factory(
    shared_store: InMemoryMemoryStore | None = None,
) -> Callable[[], InMemoryTransactionScope]:
    active_store = shared_store if shared_store is not None else InMemoryMemoryStore()
    return lambda: InMemoryTransactionScope(active_store)
