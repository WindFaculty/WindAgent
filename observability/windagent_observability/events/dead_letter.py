"""Dead-letter utilities for WindAgent Observability Layer (Phase 3 / Phase 6)."""

from __future__ import annotations
import logging
import uuid
from typing import List, Optional

from windagent_core.contracts.outbox import OutboxRecord, OutboxRepositoryPort

logger = logging.getLogger("windagent.observability.events.dead_letter")


class DeadLetterReplayer:
    """Replays dead-lettered outbox records with audit trail."""

    def __init__(self, outbox_repo: OutboxRepositoryPort):
        self._outbox_repo = outbox_repo

    async def list_dead_letters(self, limit: int = 100) -> List[OutboxRecord]:
        return await self._outbox_repo.get_dead_letters(limit=limit)

    async def replay(self, event_id: str, operator: Optional[str] = None) -> Optional[OutboxRecord]:
        """Reset a dead-letter record to pending for reprocessing.

        Preserves original event_id and attempt history. Creates replay_attempt_id audit entry.
        """
        replay_attempt_id = f"replay_{uuid.uuid4().hex[:12]}"
        record = await self._outbox_repo.replay_dead_letter(
            event_id=event_id,
            replay_attempt_id=replay_attempt_id,
            operator=operator,
        )
        if record:
            logger.info(
                f"Dead-letter event {event_id} queued for replay "
                f"(replay_attempt_id={replay_attempt_id}, attempt_count={record.attempt_count})."
            )
        return record
