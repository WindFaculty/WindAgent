"""The transport-neutral envelope for an immutable domain event."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from ..ids import ActorId, CausationId, CorrelationId, EntityId, EventId, Identifier
from ..time import normalize_utc, utc_now
from ..types import JSONValue, Version, freeze_json_mapping, thaw_json
from .domain import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class EventEnvelope:
    """Canonical event metadata plus a JSON-safe immutable payload.

    It has no knowledge of an event bus, an outbox, persistence, or a transport;
    those concerns are introduced in later platform phases.
    """

    event_type: str
    aggregate_type: str
    aggregate_id: EntityId
    sequence: int
    payload: Mapping[str, JSONValue] = field(default_factory=dict)
    event_id: EventId = field(default_factory=EventId.new)
    event_version: Version = field(default_factory=lambda: Version(1))
    occurred_at: datetime = field(default_factory=utc_now)
    actor_id: ActorId | None = None
    correlation_id: CorrelationId | None = None
    causation_id: CausationId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", _required_name(self.event_type, "event_type"))
        object.__setattr__(self, "aggregate_type", _required_name(self.aggregate_type, "aggregate_type"))
        if not isinstance(self.aggregate_id, EntityId):
            raise TypeError("aggregate_id must be an EntityId")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise TypeError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if not isinstance(self.event_id, EventId):
            raise TypeError("event_id must be an EventId")
        if not isinstance(self.event_version, Version):
            raise TypeError("event_version must be a Version")
        if self.event_version.value < 1:
            raise ValueError("event_version must be at least 1")
        _assert_optional_identifier(self.actor_id, ActorId, "actor_id")
        _assert_optional_identifier(self.correlation_id, CorrelationId, "correlation_id")
        _assert_optional_identifier(self.causation_id, CausationId, "causation_id")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")

        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at))
        object.__setattr__(self, "payload", freeze_json_mapping(self.payload))

    @classmethod
    def from_event(
        cls,
        event: DomainEvent,
        *,
        aggregate_type: str,
        aggregate_id: EntityId,
        sequence: int,
        payload: Mapping[str, object] | None = None,
        actor_id: ActorId | None = None,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationId | None = None,
    ) -> EventEnvelope:
        """Create an envelope while preserving a ``DomainEvent``'s identity."""

        if not isinstance(event, DomainEvent):
            raise TypeError("event must be a DomainEvent")
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence=sequence,
            occurred_at=event.occurred_at,
            payload=cast(Mapping[str, JSONValue], {} if payload is None else payload),
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a plain JSON-compatible representation for future adapters."""

        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": int(self.event_version),
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "sequence": self.sequence,
            "actor_id": str(self.actor_id) if self.actor_id is not None else None,
            "correlation_id": str(self.correlation_id) if self.correlation_id is not None else None,
            "causation_id": str(self.causation_id) if self.causation_id is not None else None,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": thaw_json(self.payload),
        }


def _required_name(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _assert_optional_identifier(value: object, identifier_type: type[Identifier], field_name: str) -> None:
    if value is not None and not isinstance(value, identifier_type):
        raise TypeError(f"{field_name} must be a {identifier_type.__name__} or None")
