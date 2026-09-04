"""Domain events and immutable envelopes (Phase 2)."""

from .domain import DomainEvent
from .envelope import EventEnvelope

__all__ = ["DomainEvent", "EventEnvelope"]
