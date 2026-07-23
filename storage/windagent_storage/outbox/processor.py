"""
Transactional Outbox Processor for WindAgent Storage Layer.
Fetches pending outbox records, dispatches events post-commit, and tracks publication status.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.domain.types import EventId, SessionId
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
                .order_by(OutboxRecordORM.created_at.asc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            records = res.scalars().all()

            for record in records:
                try:
                    payload = json.loads(record.payload_json) if record.payload_json else {}
                    envelope = EventEnvelope(
                        event_id=EventId(record.event_id),
                        event_type=record.event_type,
                        session_id=SessionId(record.session_id),
                        sequence=record.sequence,
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
                    record.retry_count += 1
                    if record.retry_count >= 5:
                        record.status = "failed"

            await session.commit()

        return processed_count
