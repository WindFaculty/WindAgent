"""Durable audit: outbox-backed sink adapter (app-layer composition).

Audit events become ``security.audit.recorded`` events written through the
Phase 6 transactional outbox, so they inherit the same durability,
idempotency, and delivery guarantees as domain events.  This adapter lives
in the application layer because durability is a composition concern; the
platform security package stays infrastructure-free.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.time import Clock, SystemClock
from windagent.kernel.types import JSONValue
from windagent.platform.events import TransactionalOutbox
from windagent.platform.persistence import Database, SqlUnitOfWork
from windagent.platform.security import AuditEvent, AuditSink

AUDIT_EVENT_TYPE = "security.audit.recorded"
AUDIT_AGGREGATE_TYPE = "security_audit"


class OutboxAuditSink(AuditSink):
    """Records every audit event durably via its own unit-of-work scope."""

    def __init__(self, database: Database, *, clock: Clock | None = None) -> None:
        self._database = database
        self._clock: Clock = clock if clock is not None else SystemClock()

    async def record(self, event: AuditEvent) -> None:
        if not isinstance(event, AuditEvent):
            raise TypeError("event must be an AuditEvent")
        envelope = EventEnvelope(
            event_type=AUDIT_EVENT_TYPE,
            aggregate_type=AUDIT_AGGREGATE_TYPE,
            aggregate_id=EntityId.new(),
            sequence=0,
            payload=cast("Mapping[str, JSONValue]", event.to_dict()),
            actor_id=event.actor_id,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            occurred_at=event.occurred_at,
        )
        unit_of_work = self._database.unit_of_work()
        async with unit_of_work:
            await TransactionalOutbox(
                cast(SqlUnitOfWork, unit_of_work), clock=self._clock
            ).record(envelope, deduplication_key=f"audit:{event.event_id}")
            await unit_of_work.commit()
