"""Pure, infrastructure-free primitives shared by all V2 layers (Phase 2)."""

from .errors import DomainError, ResultUnwrapError, ValidationError
from .events import DomainEvent, EventEnvelope
from .ids import ActorId, CausationId, CorrelationId, EntityId, EventId, Identifier
from .result import Result
from .time import Clock, FrozenClock, SystemClock, normalize_utc, utc_now
from .types import CurrencyMismatchError, JSONValue, Money, Version

__all__ = [
    "ActorId",
    "CausationId",
    "Clock",
    "CorrelationId",
    "CurrencyMismatchError",
    "DomainError",
    "DomainEvent",
    "EntityId",
    "EventEnvelope",
    "EventId",
    "FrozenClock",
    "Identifier",
    "JSONValue",
    "Money",
    "Result",
    "ResultUnwrapError",
    "SystemClock",
    "ValidationError",
    "Version",
    "normalize_utc",
    "utc_now",
]
