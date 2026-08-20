"""Event dispatcher for WindAgent Observability Layer (Phase 3)."""

from __future__ import annotations
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List

from windagent_core.events.envelope import EventEnvelope

logger = logging.getLogger("windagent.observability.events.dispatcher")


class EventDispatcher:
    """Routes published events to registered subscribers by event_type.

    A handler registered under the ``"*"`` wildcard receives every event.
    If a handler is registered both for an exact event type and as a wildcard,
    it is invoked only once per dispatch.
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable[[EventEnvelope], Any]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[EventEnvelope], Any]) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[EventEnvelope], Any]) -> None:
        if handler in self._handlers.get(event_type, []):
            self._handlers[event_type].remove(handler)

    async def dispatch(self, envelope: EventEnvelope) -> None:
        """Dispatch event to all subscribers. Errors are logged but do not stop other handlers."""
        handlers = list(self._handlers.get(envelope.event_type, []))
        wildcard = self._handlers.get("*", [])
        for handler in wildcard:
            if handler not in handlers:
                handlers.append(handler)
        for handler in handlers:
            try:
                result = handler(envelope)
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                logger.error(
                    f"Event handler error for {envelope.event_type} "
                    f"(event_id={envelope.event_id}): {exc}"
                )
