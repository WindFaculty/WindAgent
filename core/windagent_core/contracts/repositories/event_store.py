"""Event store port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable

from windagent_core.events.envelope import EventEnvelope


@runtime_checkable
class EventStorePort(Protocol):
    """Append-only domain event persistence port."""

    async def append(self, event: EventEnvelope) -> None:
        ...

    async def get_events(
        self, stream_id: str, after_sequence: int = 0, limit: int = 100
    ) -> List[EventEnvelope]:
        ...


@runtime_checkable
class ConversationEventStorePort(Protocol):
    """Conversation-scoped event replay port used by recovery scans."""

    async def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        ...