"""Routing events emitted through the durable outbox.

Preserved from the old routing ``events.py`` (ModelSelected/RouteLocked/
RouteReleased/ModelReselected) plus the P0.3.5 fallback event.  Events are
recorded inside the same transaction as the domain change that caused them.
"""

from __future__ import annotations

from typing import Final

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now
from windagent.kernel.types import Version

from ..domain.route_lock import RouteLockRecord

EVENT_ROUTE_LOCKED: Final[str] = "model_gateway.route.locked"
EVENT_ROUTE_REUSED: Final[str] = "model_gateway.route.reused"
EVENT_ROUTE_RELEASED: Final[str] = "model_gateway.route.released"
EVENT_MODEL_RESELECTED: Final[str] = "model_gateway.model.reselected"
EVENT_ROUTE_FALLBACK: Final[str] = "model_gateway.route.fallback"

EVENT_VERSION: Final[int] = 1
AGGREGATE_TYPE: Final[str] = "route_lock"


def _envelope(
    event_type: str, lock: RouteLockRecord, payload: dict[str, str]
) -> EventEnvelope:  # noqa: E501
    return EventEnvelope(
        event_type=event_type,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=EntityId(lock.lock_id),
        sequence=0,
        event_version=Version(EVENT_VERSION),
        occurred_at=utc_now(),
        payload={
            "lock_id": lock.lock_id,
            "scope_type": lock.scope_type,
            "scope_id": lock.scope_id,
            "canonical_model_id": lock.canonical_model_id,
            "rule_id": lock.routing_snapshot.rule_id,
            "rule_version": lock.routing_snapshot.rule_version,
            "is_fallback": lock.is_fallback,
            **payload,
        },
    )


def route_locked(lock: RouteLockRecord) -> EventEnvelope:
    """A new lock pinned a canonical model for a scope."""
    return _envelope(EVENT_ROUTE_LOCKED, lock, {"reason": lock.routing_snapshot.reason})


def route_reused(lock: RouteLockRecord) -> EventEnvelope:
    """An existing active lock satisfied a resolution (no re-lock)."""
    return _envelope(EVENT_ROUTE_REUSED, lock, {})


def route_released(lock: RouteLockRecord) -> EventEnvelope:
    """A lock was released."""
    return _envelope(EVENT_ROUTE_RELEASED, lock, {})


def model_reselected(new_lock: RouteLockRecord, *, reason: str) -> EventEnvelope:
    """A scope explicitly reselected its canonical model."""
    return _envelope(EVENT_MODEL_RESELECTED, new_lock, {"reason": reason})


def route_fallback_created(lock: RouteLockRecord, *, source_lock_id: str) -> EventEnvelope:
    """A model-level fallback lock was created (primary lock untouched)."""
    return _envelope(
        EVENT_ROUTE_FALLBACK,
        lock,
        {"source_lock_id": source_lock_id, "reason": lock.routing_snapshot.reason},
    )
