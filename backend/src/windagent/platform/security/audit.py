"""Audit trail primitives: who did what, with which outcome.

Audit records are values, not events on the wire; the app layer decides
where they go (the API composition root ships an outbox-backed sink that
turns them into durable ``security.audit.recorded`` events).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from windagent.kernel.ids import (
    ActorId,
    CausationId,
    CorrelationId,
    EntityId,
    EventId,
)
from windagent.kernel.time import normalize_utc, utc_now
from windagent.kernel.types import validate_trace_id
from windagent.kernel.types.json import freeze_json_mapping


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One recorded security-relevant occurrence."""

    action: str
    resource_type: str
    outcome: str
    actor_id: ActorId | None = None
    correlation_id: CorrelationId | None = None
    causation_id: CausationId | None = None
    trace_id: str | None = None
    resource_id: EntityId | None = None
    reason: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=utc_now)
    event_id: EventId = field(default_factory=EventId.new)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _required_text(self.action, "action"))
        object.__setattr__(
            self, "resource_type", _required_text(self.resource_type, "resource_type")
        )
        object.__setattr__(self, "outcome", _required_text(self.outcome, "outcome"))
        if self.actor_id is not None and not isinstance(self.actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId or None")
        if self.correlation_id is not None and not isinstance(
            self.correlation_id, CorrelationId
        ):
            raise TypeError("correlation_id must be a CorrelationId or None")
        if self.causation_id is not None and not isinstance(
            self.causation_id, CausationId
        ):
            raise TypeError("causation_id must be a CausationId or None")
        if self.trace_id is not None:
            object.__setattr__(self, "trace_id", validate_trace_id(self.trace_id))
        if self.resource_id is not None and not isinstance(self.resource_id, EntityId):
            raise TypeError("resource_id must be an EntityId or None")
        if self.reason is not None:
            object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")
        object.__setattr__(self, "details", freeze_json_mapping(self.details))
        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation for durable sinks."""
        return {
            "event_id": str(self.event_id),
            "action": self.action,
            "resource_type": self.resource_type,
            "outcome": self.outcome,
            "actor_id": str(self.actor_id) if self.actor_id is not None else None,
            "correlation_id": (
                str(self.correlation_id) if self.correlation_id is not None else None
            ),
            "causation_id": (
                str(self.causation_id) if self.causation_id is not None else None
            ),
            "trace_id": self.trace_id,
            "resource_id": (
                str(self.resource_id) if self.resource_id is not None else None
            ),
            "reason": self.reason,
            "details": dict(self.details),
            "occurred_at": self.occurred_at.isoformat(),
        }


@runtime_checkable
class AuditSink(Protocol):
    """Receives audit events; implementations decide durability."""

    async def record(self, event: AuditEvent) -> None:
        """Persist (or forward) one audit event."""


@dataclass(slots=True)
class InMemoryAuditSink:
    """Bounded process-local sink for tests and diagnostics."""

    max_events: int = 10_000
    _events: deque[AuditEvent] = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.max_events, bool) or not isinstance(self.max_events, int):
            raise TypeError("max_events must be an integer")
        if self.max_events < 1:
            raise ValueError("max_events must be at least 1")
        object.__setattr__(self, "_events", deque(maxlen=self.max_events))

    async def record(self, event: AuditEvent) -> None:
        if not isinstance(event, AuditEvent):
            raise TypeError("event must be an AuditEvent")
        self._events.append(event)

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """The recorded events in arrival order (oldest first)."""
        return tuple(self._events)
