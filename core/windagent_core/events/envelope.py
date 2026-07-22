"""
EventEnvelope V2 for WindAgent Architecture.
Durable event envelope containing standard metadata, correlation, sequence, and payload.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.domain.types import EventId, SessionId


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EventEnvelope:
    event_id: EventId
    event_type: str
    session_id: SessionId
    sequence: int
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0"
    occurred_at: datetime = field(default_factory=default_utc_now)
    aggregate_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type or not self.event_type.strip():
            raise ValueError("EventEnvelope event_type cannot be empty.")
        if self.sequence < 0:
            raise ValueError("EventEnvelope sequence must be >= 0.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at.isoformat(),
            "session_id": str(self.session_id),
            "aggregate_id": self.aggregate_id,
            "sequence": self.sequence,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "trace_id": self.trace_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EventEnvelope:
        raw_id = data.get("event_id")
        event_id = EventId(raw_id) if raw_id else EventId.generate()
        
        raw_session_id = data.get("session_id")
        session_id = SessionId(raw_session_id) if raw_session_id else SessionId.generate()

        occurred_at = data.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)
        elif not isinstance(occurred_at, datetime):
            occurred_at = default_utc_now()

        return cls(
            event_id=event_id,
            event_type=str(data.get("event_type", "system.unknown")),
            schema_version=str(data.get("schema_version", "2.0")),
            occurred_at=occurred_at,
            session_id=session_id,
            aggregate_id=data.get("aggregate_id"),
            sequence=int(data.get("sequence", 0)),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            trace_id=data.get("trace_id"),
            payload=data.get("payload", {}) or {},
            metadata=data.get("metadata", {}) or {},
        )
