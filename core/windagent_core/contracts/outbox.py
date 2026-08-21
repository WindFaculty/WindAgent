"""
Core contracts for Outbox types.

OutboxRecord and OutboxRepositoryPort moved here from windagent_storage
so that observability layer can depend on core contracts, not on storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class OutboxRecord:
    """Canonical outbox record — pure data contract."""
    id: str
    event_id: str
    event_type: str
    schema_version: str
    aggregate_id: str
    aggregate_type: str
    sequence_number: int
    payload_json: str
    status: str = "pending"  # pending, publishing, published, dead_letter, failed
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    attempt_count: int = 0
    max_attempts: int = 5
    claim_token: Optional[str] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    claim_ttl_seconds: float = 60.0
    next_available_at: Optional[datetime] = None
    last_error: Optional[str] = None
    deduplication_key: Optional[str] = None
    replay_attempt_id: Optional[str] = None
    dead_letter_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "sequence_number": self.sequence_number,
            "payload_json": self.payload_json,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "attempt_count": self.attempt_count,
        }


@runtime_checkable
class OutboxRepositoryPort(Protocol):
    """Protocol for outbox repository operations."""

    async def claim_pending_batch(
        self,
        limit: int,
        claim_token: str,
        claimed_by: str,
        now: datetime,
        claim_ttl_seconds: float,
    ) -> List[OutboxRecord]:
        ...

    async def mark_published(
        self,
        record_id: str,
        published_at: datetime,
        claim_token: Optional[str] = None,
    ) -> None:
        ...

    async def mark_failed(
        self,
        record_id: str,
        error: str,
        next_available_at: datetime,
        claim_token: Optional[str] = None,
    ) -> None:
        ...

    async def mark_dead_letter(
        self,
        record_id: str,
        reason: str,
        claim_token: Optional[str] = None,
    ) -> None:
        ...

    async def recover_expired_claims(self, now: datetime) -> int:
        ...

    async def get_status_counts(self) -> Dict[str, int]:
        ...

    async def get_dead_letters(self, limit: int = 100) -> List[OutboxRecord]:
        ...

    async def replay_dead_letter(
        self,
        event_id: str,
        replay_attempt_id: str,
        operator: Optional[str] = None,
    ) -> Optional[OutboxRecord]:
        ...

    async def get_by_deduplication_key(self, key: str) -> Optional[OutboxRecord]:
        ...
