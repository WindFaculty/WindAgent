"""Dead-letter utilities for WindAgent Observability Layer (Phase 3)."""

from __future__ import annotations
import logging
from typing import List

from windagent_core.events.envelope import EventEnvelope
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.repository import OutboxRepository

logger = logging.getLogger("windagent.observability.events.dead_letter")


class DeadLetterReplayer:
    """Replays dead-lettered outbox records."""

    def __init__(self, outbox_repo: OutboxRepository):
        self._outbox_repo = outbox_repo

    async def list_dead_letters(self, limit: int = 100) -> List[OutboxRecord]:
        """Return dead-letter records. Repository must support status filter."""
        # ponytail: using get_by_aggregate is wrong here; need proper query.
        # This is a placeholder until repository supports dead-letter listing.
        raise NotImplementedError("Dead-letter listing requires repository extension.")

    async def replay(self, record_id: str) -> bool:
        """Reset a dead-letter record back to pending for reprocessing."""
        record = await self._outbox_repo.get_by_id(record_id)
        if not record or record.status != "dead_letter":
            return False
        record.status = "pending"
        record.attempt_count = 0
        record.last_error = None
        await self._outbox_repo.save(record)
        logger.info(f"Dead-letter record {record_id} reset to pending.")
        return True
