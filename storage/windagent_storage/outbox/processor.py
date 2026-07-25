"""
Transactional Outbox Processor for WindAgent Storage Layer.
Fetches pending outbox records, dispatches events post-commit, and tracks publication status.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.domain.types import EventId
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import OutboxRecordORM

logger = logging.getLogger("windagent.storage.outbox")


class TransactionalOutboxManager:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_handler: Optional[Callable[[EventEnvelope], Any]] = None,
    ):
        self._session_factory = session_factory
        self.event_handler = event_handler

    async def process_pending_outbox(self, limit: int = 50) -> int:
        """Fetches pending outbox records and dispatches them via the event handler."""
        processed_count = 0
        async with self._session_factory() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.status == "pending")
                .order_by(OutboxRecordORM.sequence_number.asc())
                .limit(limit)
            )
            # ponytail: SKIP LOCKED unsupported on SQLite; claim by status flip instead
            if session.bind.dialect.name != "sqlite":
                stmt = stmt.with_for_update(skip_locked=True)
            res = await session.execute(stmt)
            records = res.scalars().all()

            # Claim records atomically by flipping status before dispatch
            claimed = []
            for record in records:
                claim = (
                    update(OutboxRecordORM)
                    .where(OutboxRecordORM.id == record.id)
                    .where(OutboxRecordORM.status == "pending")
                    .values(status="publishing")
                )
                result = await session.execute(claim)
                if result.rowcount == 1:
                    claimed.append(record)
            await session.flush()

            for record in claimed:
                try:
                    payload = json.loads(record.payload_json) if record.payload_json else {}
                    envelope = EventEnvelope(
                        event_id=EventId(record.event_id),
                        event_type=record.event_type,
                        aggregate_id=record.aggregate_id,
                        aggregate_type=record.aggregate_type,
                        sequence=record.sequence_number,
                        payload=payload,
                        occurred_at=record.created_at or datetime.now(timezone.utc),
                    )

                    if self.event_handler:
                        res_maybe = self.event_handler(envelope)
                        if hasattr(res_maybe, "__await__"):
                            await res_maybe

                    record.status = "published"
                    record.published_at = datetime.now(timezone.utc)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Failed to publish outbox record {record.id}: {e}")
                    record.attempt_count += 1
                    record.last_error = str(e)
                    if record.attempt_count >= 5:
                        record.status = "dead_letter"
                    else:
                        record.status = "pending"

            await session.commit()

        return processed_count
