"""Realtime composer for the API composition root (Phase 7).

The API owns a read-only SQL replay adapter and the WS hub; the Worker remains
the only outbox publisher owner.  Live delivery is wired to the dispatcher
wildcard so every published envelope reaches matching subscriptions in-process.
"""

from __future__ import annotations

from dataclasses import dataclass

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.realtime.sql_replay import SqlRealtimeReplayAdapter
from windagent_api.services.realtime_hub import RealtimeHub
from windagent_observability.events.dispatcher import EventDispatcher


@dataclass
class RealtimeBundle:
    """Typed result of the realtime composer."""

    realtime_replay: SqlRealtimeReplayAdapter
    realtime_hub: RealtimeHub


class RealtimeComposer:
    """Constructs the canonical realtime hub over the read-only replay adapter."""

    def compose(
        self,
        db: DatabaseManager,
        event_dispatcher: EventDispatcher,
    ) -> RealtimeBundle:
        realtime_replay = SqlRealtimeReplayAdapter(db.session_factory)
        realtime_hub = RealtimeHub(realtime_replay)
        event_dispatcher.subscribe("*", realtime_hub.publish)
        return RealtimeBundle(
            realtime_replay=realtime_replay,
            realtime_hub=realtime_hub,
        )


__all__ = ["RealtimeBundle", "RealtimeComposer"]