"""Read-only SQL realtime replay adapter for WindAgent Storage (Phase 6).

The API owns this read-only replay surface.  It never claims or mutates outbox
rows — the Worker remains the only outbox publisher owner.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.domain.types import EventId
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import OutboxRecordORM
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository


def _aware(dt: Any) -> Optional[datetime]:
    """Coerce a stored timestamp to a timezone-aware datetime.

    SQLite text queries return ``created_at`` as a string (space-separated ISO
    with optional timezone, or a trailing ``Z``).  Parse those safely and keep
    the result timezone-aware so downstream code never sees a naive datetime.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        text = dt.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _coerce_event_id(raw: str) -> EventId:
    """Return a valid EventId, deriving a deterministic UUID for opaque ids.

    Production conversation events use UUID event ids; legacy/test fixtures may
    use opaque ids.  The original id is preserved in envelope metadata so the
    wire event_id always matches the durable row.
    """
    try:
        return EventId(raw)
    except Exception:
        return EventId(str(uuid.uuid5(uuid.NAMESPACE_URL, raw)))


class SqlRealtimeReplayAdapter:
    """Read-only replay of committed aggregate events for the realtime hub.

    - ``aggregate_type == "conversation"`` replays ``conversation_events``
      through ``MultiAgentRepository.conversation_events_after`` and maps rows
      to canonical ``EventEnvelope`` values.
    - any other aggregate type replays committed non-dead-letter outbox records
      filtered by exact aggregate type + id.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def events_after(
        self,
        aggregate_type: str,
        aggregate_id: str,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> List[EventEnvelope]:
        if aggregate_type == "conversation":
            return await self._conversation_events_after(
                aggregate_id, after_sequence, limit
            )
        return await self._outbox_events_after(
            aggregate_type, aggregate_id, after_sequence, limit
        )

    async def _conversation_events_after(
        self,
        conversation_id: str,
        after_sequence: int,
        limit: int,
    ) -> List[EventEnvelope]:
        async with self._session_factory() as session:
            rows = await MultiAgentRepository(session).conversation_events_after(
                conversation_id, after_sequence, limit
            )
        return [self._conversation_row_to_envelope(row) for row in rows]

    async def _outbox_events_after(
        self,
        aggregate_type: str,
        aggregate_id: str,
        after_sequence: int,
        limit: int,
    ) -> List[EventEnvelope]:
        async with self._session_factory() as session:
            stmt = (
                select(OutboxRecordORM)
                .where(OutboxRecordORM.aggregate_type == aggregate_type)
                .where(OutboxRecordORM.aggregate_id == aggregate_id)
                .where(OutboxRecordORM.sequence_number > after_sequence)
                .where(OutboxRecordORM.status != "dead_letter")
                .order_by(OutboxRecordORM.sequence_number.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._outbox_row_to_envelope(row) for row in rows]

    @staticmethod
    def _conversation_row_to_envelope(row: dict[str, Any]) -> EventEnvelope:
        raw_event_id = str(row["event_id"])
        return EventEnvelope(
            event_id=_coerce_event_id(raw_event_id),
            event_type=str(row["event_type"]),
            aggregate_type="conversation",
            aggregate_id=str(row["conversation_id"]),
            sequence=int(row["sequence"]),
            occurred_at=_aware(row["created_at"]) or datetime.now(timezone.utc),
            payload=dict(row.get("data") or {}),
            metadata={
                "event_id": raw_event_id,
                "idempotency_key": str(row.get("idempotency_key") or raw_event_id),
                "agent_instance_id": row.get("agent_instance_id"),
                "agent_session_id": row.get("agent_session_id"),
            },
        )

    @staticmethod
    def _outbox_row_to_envelope(row: OutboxRecordORM) -> EventEnvelope:
        payload = json.loads(row.payload_json) if row.payload_json else {}
        return EventEnvelope(
            event_id=_coerce_event_id(str(row.event_id)),
            event_type=str(row.event_type),
            aggregate_type=row.aggregate_type,
            aggregate_id=row.aggregate_id,
            sequence=int(row.sequence_number),
            occurred_at=_aware(row.created_at) or datetime.now(timezone.utc),
            payload=payload,
        )


__all__ = ["SqlRealtimeReplayAdapter"]