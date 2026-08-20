"""Memory record repository port for WindAgent Core (Phase 3).

The port is dict-based so the concrete SQL implementation can live in storage
without importing application-layer domain models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class MemoryRecordRepositoryPort(Protocol):
    """Durable memory record persistence port used by the memory store.

    The concrete SQL implementation lives in storage (SqlMemoryRecordRepository)
    and is injected by composition roots. Methods operate on plain dicts so the
    storage layer never imports application-domain models.
    """

    async def save(self, record: Dict[str, Any]) -> None: ...

    async def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]: ...

    async def get_by_key(
        self, scope: str, key: str, session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]: ...

    async def delete(self, record_id: str) -> bool: ...

    async def delete_by_key(
        self, scope: str, key: str, session_id: Optional[str] = None
    ) -> bool: ...

    async def list_by_session(self, session_id: str) -> List[Dict[str, Any]]: ...

    async def list_by_scope(self, scope: str, limit: int = 100) -> List[Dict[str, Any]]: ...

    async def evict_expired(self, ttl_seconds: Optional[int]) -> int: ...


__all__ = ["MemoryRecordRepositoryPort"]