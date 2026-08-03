"""
Durable outbox journal for the Durable Production Workflow (plan 05 §8.3).

The outbox lives inside the same atomic journal as the run state and
checkpoint (see engine.ProductionUnitOfWork). Rules enforced here:

- an event is only PUBLISHED after the state/checkpoint commit succeeded;
- external provider result ingestion is idempotent by generation/event ID —
  the same result delivered twice is ingested once;
- the journal is append-only for audit: published events are never deleted,
  only marked published (or dead-lettered on repeated failure).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OutboxEvent:
    """A durable outbound event committed atomically with run state."""

    event_id: str
    event_type: str
    payload: Dict[str, Any]
    status: str = "pending"  # pending | published | dead_letter
    deduplication_key: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    published_at: Optional[float] = None
    attempt_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "status": self.status,
            "deduplication_key": self.deduplication_key,
            "created_at": self.created_at,
            "published_at": self.published_at,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutboxEvent":
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            payload=data.get("payload", {}),
            status=data.get("status", "pending"),
            deduplication_key=data.get("deduplication_key"),
            created_at=data.get("created_at", 0.0),
            published_at=data.get("published_at"),
            attempt_count=data.get("attempt_count", 0),
            last_error=data.get("last_error"),
        )


def new_event(event_type: str, payload: Dict[str, Any], dedup_key: Optional[str] = None) -> OutboxEvent:
    return OutboxEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        payload=payload,
        deduplication_key=dedup_key,
    )


class OutboxJournal:
    """Ordered, append-only outbox for one run."""

    def __init__(self, events: Optional[List[OutboxEvent]] = None) -> None:
        self._events: List[OutboxEvent] = list(events or [])

    def events(self) -> List[OutboxEvent]:
        return list(self._events)

    def pending(self) -> List[OutboxEvent]:
        return [e for e in self._events if e.status == "pending"]

    def append(self, event: OutboxEvent) -> bool:
        """Append a new event; False if the dedup key already exists (idempotent)."""
        if event.deduplication_key and self.find_by_dedup(event.deduplication_key):
            return False
        self._events.append(event)
        return True

    def find_by_dedup(self, key: str) -> Optional[OutboxEvent]:
        for e in self._events:
            if e.deduplication_key == key:
                return e
        return None

    def mark_published(self, event_id: str) -> bool:
        """Mark an event published. Only pending events can be published."""
        for e in self._events:
            if e.event_id == event_id:
                if e.status != "pending":
                    return False
                e.status = "published"
                e.published_at = time.time()
                return True
        return False

    def mark_dead_letter(self, event_id: str, error: str) -> bool:
        for e in self._events:
            if e.event_id == event_id and e.status == "pending":
                e.status = "dead_letter"
                e.last_error = error
                e.attempt_count += 1
                return True
        return False

    def ingest_external_result(self, external_id: str) -> bool:
        """Idempotent ingestion guard by external generation/event ID.

        Returns True the FIRST time an external result for this id is
        ingested; False on any duplicate delivery. The caller only applies
        side effects when True.
        """
        for e in self._events:
            if e.deduplication_key == f"external:{external_id}":
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {"events": [e.to_dict() for e in self._events]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutboxJournal":
        return cls([OutboxEvent.from_dict(e) for e in data.get("events", [])])


__all__ = [
    "OutboxEvent",
    "new_event",
    "OutboxJournal",
]
