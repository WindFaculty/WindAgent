"""StudioUnitOfWork — transactional Studio boundary (Plan A — A3, studio.contract/v0.1).

Implements ``StudioUnitOfWorkPort``: one session unites the canonical Studio
repositories, the per-aggregate event store, and the transactional outbox.

- ``append_event`` allocates the next per-aggregate sequence (DB max +
  in-session max) and inserts into ``studio_events``; the unique
  (aggregate_id, sequence) index rejects cross-session races at commit.
- ``publish_outbox`` writes the same event into the existing
  ``v2_outbox_records`` outbox with ``aggregate_type='studio'`` and the
  per-aggregate sequence, so the existing publisher/dispatcher ordering
  (aggregate_id, sequence_number) applies unchanged.
- Commit/rollback are atomic across aggregates, events, and outbox rows.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.events.studio import StudioEventEnvelope
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_storage.studio.repositories import (
    SqlApprovalRepository,
    SqlEpisodeRepository,
    SqlSeriesProjectRepository,
    SqlStoryArtifactRepository,
    SqlStudioEventRepository,
    SqlStudioRevisionRepository,
    SqlStudioRunRepository,
)
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


class StudioUnitOfWork:
    """Async transactional boundary for all canonical Studio aggregates."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: Optional[AsyncSession] = None
        self.series: Optional[SqlSeriesProjectRepository] = None
        self.episodes: Optional[SqlEpisodeRepository] = None
        self.revisions: Optional[SqlStudioRevisionRepository] = None
        self.artifacts: Optional[SqlStoryArtifactRepository] = None
        self.approvals: Optional[SqlApprovalRepository] = None
        self.runs: Optional[SqlStudioRunRepository] = None
        self.nodes: Optional[SqlStudioRunNodeRepository] = None
        self.events: Optional[SqlStudioEventRepository] = None
        self._assigned_events: Dict[str, StudioEventEnvelope] = {}

    async def __aenter__(self) -> StudioUnitOfWork:
        self.session = self._session_factory()
        self.series = SqlSeriesProjectRepository(self.session)
        self.episodes = SqlEpisodeRepository(self.session)
        self.revisions = SqlStudioRevisionRepository(self.session)
        self.artifacts = SqlStoryArtifactRepository(self.session)
        self.approvals = SqlApprovalRepository(self.session)
        self.runs = SqlStudioRunRepository(self.session)
        self.nodes = SqlStudioRunNodeRepository(self.session)
        self.events = SqlStudioEventRepository(self.session)
        self._assigned_events = {}
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()
        if self.session is not None:
            await self.session.close()

    async def append_event(self, event: StudioEventEnvelope) -> None:
        """Persist the event with the next per-aggregate sequence (idempotent by event_id)."""
        if self.session is None or self.events is None:
            raise RuntimeError("StudioUnitOfWork context not active.")
        if event.event_id in self._assigned_events:
            return
        assigned = await self.events.append(event)
        self._assigned_events[event.event_id] = assigned

    async def publish_outbox(self, event: StudioEventEnvelope) -> None:
        """Write the event into the transactional outbox with per-aggregate ordering."""
        if self.session is None:
            raise RuntimeError("StudioUnitOfWork context not active.")
        assigned = self._assigned_events.get(event.event_id) or event
        repository = SqlOutboxRepository(self.session)
        await repository.save(
            OutboxRecord(
                id=f"studio_{uuid.uuid4().hex[:12]}",
                event_id=assigned.event_id,
                aggregate_id=assigned.aggregate_id,
                aggregate_type="studio",
                event_type=assigned.event_type,
                payload_json=json.dumps(assigned.to_dict()),
                schema_version=1,
                sequence_number=assigned.sequence,
                created_at=_naive(assigned.occurred_at),
                available_at=_naive(datetime.now(timezone.utc)),
                deduplication_key=assigned.event_id,
            )
        )

    async def commit(self) -> None:
        if self.session is not None:
            await self.session.commit()
            self._assigned_events.clear()

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()
        self._assigned_events.clear()


__all__ = ["StudioUnitOfWork"]
