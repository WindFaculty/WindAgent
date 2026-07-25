"""Outbox repository contract for WindAgent Storage Layer (Phase 3)."""

from __future__ import annotations
from typing import List, Optional, Protocol, runtime_checkable
from datetime import datetime

from windagent_storage.outbox.models import OutboxRecord


@runtime_checkable
class OutboxRepository(Protocol):
    """Protocol for outbox record persistence and retrieval."""

    async def save(self, record: OutboxRecord) -> None:
        ...

    async def get_pending(self, limit: int = 50, now: Optional[datetime] = None) -> List[OutboxRecord]:
        ...

    async def get_by_id(self, record_id: str) -> Optional[OutboxRecord]:
        ...

    async def mark_published(self, record_id: str, published_at: datetime) -> None:
        ...

    async def mark_failed(self, record_id: str, error: str, next_available_at: datetime) -> None:
        ...

    async def mark_dead_letter(self, record_id: str, error: str) -> None:
        ...

    async def get_by_deduplication_key(self, dedup_key: str) -> Optional[OutboxRecord]:
        ...

    async def get_by_aggregate(self, aggregate_id: str, limit: int = 100) -> List[OutboxRecord]:
        ...
