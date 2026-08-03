"""Outbox repository contract for WindAgent Storage Layer (Phase 3 / Phase 6)."""

from __future__ import annotations
from typing import Dict, List, Optional, Protocol, runtime_checkable
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

    async def get_by_event_id(self, event_id: str) -> Optional[OutboxRecord]:
        ...

    async def mark_published(self, record_id: str, published_at: datetime, claim_token: Optional[str] = None) -> None:
        ...

    async def mark_failed(self, record_id: str, error: str, next_available_at: datetime, claim_token: Optional[str] = None) -> None:
        ...

    async def mark_dead_letter(self, record_id: str, error: str, claim_token: Optional[str] = None) -> None:
        ...

    async def get_by_deduplication_key(self, dedup_key: str) -> Optional[OutboxRecord]:
        ...

    async def get_by_aggregate(self, aggregate_id: str, limit: int = 100) -> List[OutboxRecord]:
        ...

    async def claim_pending_batch(
        self,
        limit: int,
        claim_token: str,
        claimed_by: str,
        now: Optional[datetime] = None,
        claim_ttl_seconds: float = 60.0,
    ) -> List[OutboxRecord]:
        ...

    async def recover_expired_claims(self, now: Optional[datetime] = None) -> int:
        ...

    async def get_dead_letters(self, limit: int = 100) -> List[OutboxRecord]:
        ...

    async def get_status_counts(self) -> Dict[str, int]:
        ...

    async def replay_dead_letter(
        self,
        event_id: str,
        replay_attempt_id: str,
        operator: Optional[str] = None,
    ) -> Optional[OutboxRecord]:
        ...


OutboxRepositoryPort = OutboxRepository
__all__ = ["OutboxRepository", "OutboxRepositoryPort"]
