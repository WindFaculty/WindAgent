"""Session service — chat session state with SQLite persistence.

Phase 1: in-memory only.
Phase 2: writes to SQLite via optional `db` constructor arg.
Phase 4: adds snapshot, list, archive, pagination APIs.
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
from sqlalchemy import select


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

    Phase 4 additions:
      - list_sessions(limit, offset, exclude_archived) -> list[ChatSession]
      - get_session_snapshot(id)          -> dict with session + messages + events
      - archive_session(id)              -> None
      - delete_session(id)               -> None
      - update_last_event_sequence(id, seq) -> None
    """

    def __init__(
        self,
        event_bus: EventBus,
        db: Optional[Database] = None,
    ) -> None:
        self._bus = event_bus
        self._db = db
        self._sessions: Dict[UUID, _StoredSession] = {}

    async def create_session(self, agent_id: Optional[str] = None, title: Optional[str] = None) -> ChatSession:
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
                    agent_id=agent_id,
                    title=title or "New Session",
                    last_event_sequence=0,
                ))

        return chat

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        stored = self._sessions.get(session_id)
        if stored is not None:
            return stored.session

        if self._db is not None:
            async with self._db.session() as s:
                row = await s.get(ChatSessionORM, str(session_id))
                if row is not None:
                    chat = ChatSession(
                        id=UUID(row.id),
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        status=row.status,
                    )

                    msg_rows = (await s.execute(
                        select(MessageORM)
                        .where(MessageORM.session_id == str(session_id))
                        .order_by(MessageORM.created_at)
                    )).scalars().all()

                    messages = [
                        Message(
                            id=UUID(m.id),
                            session_id=UUID(m.session_id),
                            sender=m.sender,
                            content=m.content,
                            created_at=m.created_at,
                        )
                        for m in msg_rows
                    ]

                    self._sessions[session_id] = _StoredSession(
                        session=chat,
                        messages=messages,
                    )
                    return chat

        return None

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
                    # Mark completed_at for terminal statuses
                    if status in ("completed", "cancelled", "failed") and row.completed_at is None:
                        row.completed_at = now

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

    # ---------- Phase 4: snapshot, list, archive, delete ----------

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        exclude_archived: bool = True,
        status_filter: Optional[List[str]] = None,
    ) -> List[dict]:
        """Return a paginated list of sessions. Uses DB if available."""
        if self._db is None:
            # In-memory fallback
            sessions = list(self._sessions.values())
            return [
                {
                    "id": str(s.session.id),
                    "status": s.session.status,
                    "created_at": s.session.created_at.isoformat(),
                    "updated_at": s.session.updated_at.isoformat(),
                    "message_count": len(s.messages),
                }
                for s in sessions[offset:offset + limit]
            ]

        async with self._db.session() as s:
            stmt = select(ChatSessionORM).order_by(ChatSessionORM.updated_at.desc())
            if exclude_archived:
                stmt = stmt.where(ChatSessionORM.archived_at.is_(None))
            if status_filter:
                stmt = stmt.where(ChatSessionORM.status.in_(status_filter))
            stmt = stmt.limit(limit).offset(offset)
            rows = (await s.execute(stmt)).scalars().all()

        return [
            {
                "id": row.id,
                "title": row.title or "New Session",
                "agent_id": row.agent_id,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "archived_at": row.archived_at.isoformat() if row.archived_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "last_event_sequence": row.last_event_sequence or 0,
            }
            for row in rows
        ]

    async def get_session_snapshot(self, session_id: UUID) -> dict | None:
        """Return full session snapshot for frontend recovery.

        Returns:
            {
                "session": {...},
                "messages": [...],
                "tool_calls": [...],   # from DB if available
                "workflow": null,      # loaded separately
                "last_event_sequence": N
            }
        """
        chat = await self.get_session(session_id)
        if chat is None:
            return None

        stored = self._sessions.get(session_id)
        messages_data = []
        tool_calls_data = []
        last_event_sequence = 0

        if stored:
            messages_data = [
                {
                    "id": str(m.id),
                    "session_id": str(m.session_id),
                    "sender": m.sender,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in stored.messages
            ]

        if self._db is not None:
            async with self._db.session() as s:
                # Get session metadata
                row = await s.get(ChatSessionORM, str(session_id))
                if row:
                    # NOTE: chat_sessions.last_event_sequence is only advanced by
                    # the Hermes bridge (which calls update_last_event_sequence).
                    # The native workflow path never updates it, so it under-
                    # reports the cursor (stays 0). The authoritative replay
                    # source is execution_events, whose max seq we use instead.
                    try:
                        from sqlalchemy import func
                        from db.models import ExecutionEventORM
                        max_seq_res = await s.execute(
                            select(func.max(ExecutionEventORM.event_seq)).where(ExecutionEventORM.session_id == str(session_id))
                        )
                        max_seq = max_seq_res.scalar()
                        last_event_sequence = max_seq if max_seq is not None else (row.last_event_sequence or 0)
                    except Exception:  # noqa: BLE001
                        last_event_sequence = row.last_event_sequence or 0

                if last_event_sequence == 0 and hasattr(self._bus, "_seq"):
                    last_event_sequence = self._bus._seq.get(str(session_id), self._bus._seq.get(session_id, 0))

                # Get tool calls
                from db.models import ToolCallORM
                from sqlalchemy import select
                tc_rows = (await s.execute(
                    select(ToolCallORM)
                    .where(ToolCallORM.session_id == str(session_id))
                    .order_by(ToolCallORM.created_at)
                )).scalars().all()

                import json
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "tool_name": tc.tool_name,
                        "status": tc.status,
                        "input": json.loads(tc.input_json or "{}"),
                        "output": json.loads(tc.output_json or "{}"),
                        "created_at": tc.created_at.isoformat() if tc.created_at else None,
                    }
                    for tc in tc_rows
                ]

        return {
            "session": {
                "id": str(chat.id),
                "status": chat.status,
                "created_at": chat.created_at.isoformat() if chat.created_at else None,
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            },
            "messages": messages_data,
            "tool_calls": tool_calls_data,
            "workflow": None,  # loaded separately via workflow service
            "last_event_sequence": last_event_sequence,
        }

    async def archive_session(self, session_id: UUID) -> None:
        """Mark a session as archived (hidden from default list, data preserved)."""
        now = datetime.now(timezone.utc)
        stored = self._sessions.get(session_id)
        if stored:
            stored.session = stored.session.model_copy(update={"updated_at": now})

        if self._db is not None:
            async with self._db.session() as s:
                row = await s.get(ChatSessionORM, str(session_id))
                if row is not None:
                    row.archived_at = now
                    row.updated_at = now

    async def delete_session(self, session_id: UUID) -> None:
        """Hard-delete a session and its messages."""
        self._sessions.pop(session_id, None)

        if self._db is not None:
            async with self._db.session() as s:
                # Delete messages first (FK constraint)
                await s.execute(
                    MessageORM.__table__.delete().where(
                        MessageORM.session_id == str(session_id)
                    )
                )
                row = await s.get(ChatSessionORM, str(session_id))
                if row is not None:
                    await s.delete(row)

    async def update_last_event_sequence(self, session_id: UUID, seq: int) -> None:
        """Update the last persisted event sequence for cursor-based reconnect."""
        if self._db is None:
            return

        async with self._db.session() as s:
            row = await s.get(ChatSessionORM, str(session_id))
            if row is not None and (row.last_event_sequence or 0) < seq:
                row.last_event_sequence = seq
