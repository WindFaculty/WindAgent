"""Worker-owned transactional outbox publisher composition."""

from __future__ import annotations

import logging
from typing import Any

from windagent_observability.events.publisher import OutboxEventPublisher
from windagent_storage.outbox.sql_repository import SqlOutboxRepository

logger = logging.getLogger("windagent.worker.composition.outbox")


class OutboxComposer:
    """Construct and control the single Worker outbox publisher."""

    @staticmethod
    async def compose(
        uow_factory: Any, event_dispatcher: Any
    ) -> OutboxEventPublisher:
        publisher = OutboxEventPublisher(
            outbox_repo=SqlOutboxRepository(uow_factory),
            dispatcher=event_dispatcher.dispatch,
        )
        await publisher.start()
        return publisher

    @staticmethod
    async def shutdown(publisher: Any | None) -> None:
        if publisher is None or not hasattr(publisher, "stop"):
            return
        try:
            await publisher.stop(drain=True)
        except Exception as ex:
            logger.warning("Error stopping worker outbox publisher: %s", ex)


__all__ = ["OutboxComposer"]
