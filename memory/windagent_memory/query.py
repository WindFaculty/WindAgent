"""Memory query service alias for composition roots.

MemoryQueryService is the async facade over MemoryStore used by API/Worker
composition roots.
"""
from __future__ import annotations

from windagent_memory.store import MemoryStore


class MemoryQueryService:
    """Async query service over MemoryStore."""

    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or MemoryStore()

    async def query(self, *args, **kwargs):  # ponytail: thin pass-through
        return self._store.search(*args, **kwargs)

    async def close(self) -> None:
        pass


__all__ = ["MemoryQueryService"]
