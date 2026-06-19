"""Session service — in-memory chat session state with optional SQLite mirror.

Phase 1 stored everything in RAM. Phase 2 also writes to SQLite via the
optional `db` constructor arg so the API is unchanged when db=None
(existing tests still pass in pure-RAM mode).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from db.database import Database
from db.models import ChatSessionORM, MessageORM
from schemas.event import EventEnvelope, MessageReceivedData
from schemas.session import ChatSession, Message, SessionStatus
from services.event_bus import EventBus


@dataclass
class _StoredSession:
    session: ChatSession
    messages: List[Message] = field(default_factory=list)


class SessionService:
    """Manages chat sessions and the messages bound to them.

    Public API (Phase 1 + Phase 2 contract — unchanged when db=None):
      - create_session()                  -> ChatSession
      - get_session(id)                   -> ChatSession | None
      - update_status(id, status)         -> None
      - session_count()                   -> int
      - add_user_message(id, content)     -> Message   (emits message_received)
      - list_messages(id)                 -> list[Message]
    """

    def __init__(
        self,
        event_bus: EventBus,
        db: Optional[Database] = None,
    ) -> None:
        self._bus = event_bus
        self._db = db
        self._sessions: Dict[UUID, _StoredSession] = {}

    async def create_session(self) -> ChatSession:
        now = datetime.now(timezone.utc)
        chat = ChatSession(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            status="idle",
        )
        self._sessions[chat.id] = _StoredSession(session=chat)

        if self._db is not None:
            async with self._db.session() as s:
                s.add(ChatSessionORM(
                    id=str(chat.id),
                    created_at=chat.created_at,
                    updated_at=chat.updated_at,
                    status=chat.status,
                ))

        return chat

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        stored = self._sessions.get(session_id)
        return stored.session if stored else None

    async def update_status(self, session_id: UUID, status: SessionStatus) -> None:
        stored = self._sessions.get(session_id)
        if stored is None:
            raise KeyError(f"unknown session {session_id}")
        now = datetime.now(timezone.utc)
        stored.session = stored.session.model_copy(update={
            "status": status,
            "updated_at": now,
        })

        if self._db is not None:
            async with self._db.session() as s:
                row = await s.get(ChatSessionORM, str(session_id))
                if row is not None:
                    row.status = status
                    row.updated_at = now

    def session_count(self) -> int:
        return len(self._sessions)

    async def add_user_message(self, session_id: UUID, content: str) -> Message:
        stored = self._sessions.get(session_id)
        if stored is None:
            raise KeyError(f"unknown session {session_id}")

        now = datetime.now(timezone.utc)
        message = Message(
            id=uuid4(),
            session_id=session_id,
            sender="user",
            content=content,
            created_at=now,
        )
        stored.messages.append(message)
        stored.session = stored.session.model_copy(update={"updated_at": now})

        if self._db is not None:
            async with self._db.session() as s:
                sess_row = await s.get(ChatSessionORM, str(session_id))
                if sess_row is not None:
                    sess_row.updated_at = now
                s.add(MessageORM(
                    id=str(message.id),
                    session_id=str(session_id),
                    sender=message.sender,
                    content=content,
                    created_at=now,
                ))

        envelope = EventEnvelope(
            event="message_received",
            timestamp=now,
            data=MessageReceivedData(
                session_id=session_id,
                message_id=message.id,
                content=content,
            ).model_dump(mode="json"),
        )
        await self._bus.publish(str(session_id), envelope)
        return message

    def list_messages(self, session_id: UUID) -> List[Message]:
        stored = self._sessions.get(session_id)
        return list(stored.messages) if stored else []
