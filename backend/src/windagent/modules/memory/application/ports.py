"""Application ports for the Memory bounded context (Phase 14)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable

from windagent.kernel.events import EventEnvelope

from .models import MemoryRecordRow


@runtime_checkable
class MemoryStore(Protocol):
    """Repository port for persisting Memory records."""

    async def get(
        self,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> MemoryRecordRow | None: ...

    async def get_by_id(self, memory_id: str) -> MemoryRecordRow | None: ...

    async def get_by_hash(self, content_hash: str) -> MemoryRecordRow | None: ...

    async def insert(self, row: MemoryRecordRow) -> MemoryRecordRow: ...

    async def update(self, row: MemoryRecordRow, expected_version: int) -> MemoryRecordRow: ...

    async def delete(self, memory_id: str) -> bool: ...

    async def delete_by_scope_key(
        self,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> bool: ...

    async def list_records(
        self,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecordRow]: ...

    async def count_by_scope(self) -> dict[str, int]: ...

    async def evict_expired(
        self,
        reference_time: datetime | None = None,
        scope: str | None = None,
    ) -> int: ...


@runtime_checkable
class MemoryTransactionScope(Protocol):
    """Transactional boundary combining MemoryStore and outbox events."""

    async def __aenter__(self) -> MemoryTransactionScope: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...

    @property
    def store(self) -> MemoryStore: ...

    async def record_event(
        self, event: EventEnvelope, *, deduplication_key: str | None = None
    ) -> bool: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


MemoryScopeFactory = Callable[[], MemoryTransactionScope]
