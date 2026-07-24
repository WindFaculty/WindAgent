"""
EventEnvelope V2 for WindAgent Architecture (Pydantic v2 Canonical Implementation).
Durable event envelope containing standard metadata, correlation, sequence, and payload.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.domain.types import EventId, SessionId
from windagent_core.errors.exceptions import ValidationError


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventEnvelope(BaseModel):
    """
    Canonical Pydantic v2 EventEnvelope for all event emission across WindAgent.
    Enforces immutability, schema versioning, dotted taxonomy, and sequence metadata.
    """
    event_id: EventId
    event_type: str
    schema_version: int = 1
    stream_id: Optional[str] = None
    aggregate_id: Optional[str] = None
    aggregate_type: Optional[str] = None
    sequence: int = 0
    occurred_at: datetime = Field(default_factory=default_utc_now)
    recorded_at: Optional[datetime] = None
    session_id: Optional[SessionId] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[EventId] = None
    trace_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)

    def model_post_init(self, __context: Any) -> None:
        if not self.stream_id:
            derived_stream = str(self.session_id) if self.session_id else (self.aggregate_id or str(self.event_id))
            object.__setattr__(self, "stream_id", derived_stream)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValidationError("EventEnvelope event_type cannot be empty.")
        return v.strip()

    @field_validator("sequence")
    @classmethod
    def validate_sequence(cls, v: int) -> int:
        if v < 0:
            raise ValidationError("EventEnvelope sequence must be >= 0.")
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Serialize EventEnvelope to plain JSON-compatible dictionary."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "stream_id": self.stream_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "correlation_id": self.correlation_id,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "trace_id": self.trace_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EventEnvelope:
        """
        Construct EventEnvelope from dictionary with strict field validation.
        """
        if not isinstance(data, dict):
            raise ValidationError(f"Invalid EventEnvelope data type: {type(data)}")

        raw_event_id = data.get("event_id")
        event_id = EventId(raw_event_id) if raw_event_id else EventId.generate()

        raw_session_id = data.get("session_id")
        session_id = SessionId(raw_session_id) if raw_session_id else None

        stream_id = data.get("stream_id")
        if not stream_id:
            stream_id = str(session_id) if session_id else (data.get("aggregate_id") or str(event_id))

        occurred_at = data.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)
        elif not isinstance(occurred_at, datetime):
            occurred_at = default_utc_now()

        recorded_at = data.get("recorded_at")
        if isinstance(recorded_at, str):
            recorded_at = datetime.fromisoformat(recorded_at)
        elif not isinstance(recorded_at, datetime):
            recorded_at = None

        raw_causation = data.get("causation_id")
        causation_id = EventId(raw_causation) if raw_causation else None

        raw_schema_version = data.get("schema_version", 1)
        try:
            schema_version = int(raw_schema_version)
        except (ValueError, TypeError):
            schema_version = 1

        return cls(
            event_id=event_id,
            event_type=str(data.get("event_type", "system.unknown")),
            schema_version=schema_version,
            stream_id=stream_id,
            aggregate_id=data.get("aggregate_id"),
            aggregate_type=data.get("aggregate_type"),
            sequence=int(data.get("sequence", 0)),
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            session_id=session_id,
            correlation_id=data.get("correlation_id"),
            causation_id=causation_id,
            trace_id=data.get("trace_id"),
            payload=data.get("payload", {}) or {},
            metadata=data.get("metadata", {}) or {},
        )
