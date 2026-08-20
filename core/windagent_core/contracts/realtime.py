"""Realtime replay port for WindAgent Core (Phase 6).

The API owns a read-only replay adapter and a WS hub; the Worker remains the
only outbox publisher owner.  This port is the seam that keeps the hub free of
concrete SQL/SQLAlchemy imports.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from windagent_core.events.envelope import EventEnvelope


@runtime_checkable
class RealtimeReplayPort(Protocol):
    """Read-only replay of committed aggregate events for realtime delivery.

    Implementations must:
    - filter by exact aggregate type + aggregate id;
    - return events strictly after ``after_sequence``, ascending, bounded;
    - never claim or mutate outbox rows (read-only relay).
    """

    async def events_after(
        self,
        aggregate_type: str,
        aggregate_id: str,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> List[EventEnvelope]:
        """Return ordered ``EventEnvelope`` values strictly after the cursor."""
        ...


__all__ = ["RealtimeReplayPort"]