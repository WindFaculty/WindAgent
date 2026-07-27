"""
API V2 Sessions Router for WindAgent Architecture V2 (Phase 25).
Endpoints for creating, listing, and retrieving execution sessions via SqlUnitOfWork.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.types import SessionId
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_uow
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

router = APIRouter(prefix="/api/v2/sessions", tags=["Sessions V2"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Default Session"
    agent_id: Optional[str] = "default_agent"
    workspace_root: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    session_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreateSessionRequest,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> SessionResponse:
    from windagent_core.domain.models import Session, SessionStatus
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    sid = str(SessionId.generate())
    now = utc_now()

    session = Session(
        id=SessionId(sid),
        title=req.title or "Default Session",
        status=SessionStatus.IDLE,
        created_at=now,
        updated_at=now,
        metadata=req.metadata,
    )

    await session_repo.save(session)
    await uow.commit()

    return SessionResponse(
        session_id=sid,
        title=req.title or "Default Session",
        status="idle",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        metadata=req.metadata,
    )


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    exclude_archived: bool = Query(True),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[SessionResponse]:
    from windagent_core.domain.types import SessionId
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    sessions = await session_repo.list_sessions(limit=limit, offset=(page - 1) * limit)

    # Filter out archived sessions if requested
    if exclude_archived:
        sessions = [s for s in sessions if not s.metadata.get("archived", False)]

    return [
        SessionResponse(
            session_id=str(session.id),
            title=session.title,
            status=session.status.value,
            created_at=session.created_at.isoformat()
            if session.created_at
            else utc_now().isoformat(),
            updated_at=session.updated_at.isoformat()
            if session.updated_at
            else utc_now().isoformat(),
            metadata=session.metadata or {},
        )
        for session in sessions
    ]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> SessionResponse:
    from windagent_core.domain.types import SessionId
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    session = await session_repo.get_by_id(SessionId(session_id))

    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    return SessionResponse(
        session_id=str(session.id),
        title=session.title,
        status=session.status.value,
        created_at=session.created_at.isoformat()
        if session.created_at
        else utc_now().isoformat(),
        updated_at=session.updated_at.isoformat()
        if session.updated_at
        else utc_now().isoformat(),
        metadata=session.metadata or {},
    )


@router.get("/{session_id}/snapshot")
async def get_session_snapshot(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> Dict[str, Any]:
    """Get session snapshot with messages and last event sequence for recovery."""
    from windagent_core.domain.types import SessionId
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    session = await session_repo.get_by_id(SessionId(session_id))

    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Get events for this session
    events = await uow.events.get_events(
        stream_id=session_id, after_sequence=0, limit=1000
    )

    # Convert to response format
    messages = []
    last_event_sequence = 0
    for i, event in enumerate(events):
        last_event_sequence = max(last_event_sequence, i + 1)
        # Map events to messages format
        if event.event_type == "message_received":
            messages.append(
                {
                    "sender": event.payload.get("sender", "user"),
                    "content": event.payload.get("content", ""),
                }
            )

    return {
        "session": {
            "id": str(session.id),
            "title": session.title,
            "status": session.status.value,
            "created_at": session.created_at.isoformat()
            if session.created_at
            else utc_now().isoformat(),
            "updated_at": session.updated_at.isoformat()
            if session.updated_at
            else utc_now().isoformat(),
        },
        "messages": messages,
        "last_event_sequence": last_event_sequence,
    }


@router.get("/{session_id}/events")
async def get_session_events(
    session_id: str,
    after_seq: int = Query(0, ge=0),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> Dict[str, Any]:
    """Get session events for cursor-based replay (reconnect contract)."""
    events = await uow.events.get_events(
        stream_id=session_id, after_sequence=after_seq, limit=1000
    )

    event_list = []
    for event in events:
        event_list.append(
            {
                "seq": event.sequence,
                "event": event.event_type,
                "event_type": event.event_type,
                "data": event.payload,
                "created_at": event.occurred_at.isoformat()
                if event.occurred_at
                else None,
            }
        )

    return {
        "session_id": session_id,
        "events": event_list,
    }


@router.post("/{session_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_session(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
):
    """Cancel session - stop but keep."""
    from windagent_core.domain.types import SessionId
    from windagent_core.domain.models import SessionStatus
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    session = await session_repo.get_by_id(SessionId(session_id))

    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    session.transition_to(SessionStatus.CANCELLED)
    await session_repo.save(session)
    await uow.commit()


@router.post("/{session_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_session(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
):
    """Archive session - hide but keep."""
    from windagent_core.domain.types import SessionId
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    session = await session_repo.get_by_id(SessionId(session_id))

    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Mark as archived via metadata
    session.metadata["archived"] = True
    await session_repo.save(session)
    await uow.commit()


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
):
    """Delete session - permanently remove."""
    from windagent_core.domain.types import SessionId
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    deleted = await session_repo.delete(SessionId(session_id))

    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")

    await uow.commit()


@router.get("/{session_id}/messages", response_model=List[Dict[str, Any]])
async def list_session_messages(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[Dict[str, Any]]:
    """List session messages."""
    events = await uow.events.get_events(
        stream_id=session_id, after_sequence=0, limit=1000
    )

    messages = []
    for event in events:
        if event.event_type == "message_received":
            messages.append(
                {
                    "id": str(event.event_id),
                    "sender": event.payload.get("sender", "user"),
                    "content": event.payload.get("content", ""),
                    "created_at": event.occurred_at.isoformat()
                    if event.occurred_at
                    else None,
                }
            )

    return messages


@router.post(
    "/{session_id}/messages",
    response_model=Dict[str, Any],
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    session_id: str,
    payload: Dict[str, Any],
    uow: SqlUnitOfWork = Depends(get_uow),
) -> Dict[str, Any]:
    """Send a message to a session - triggers workflow/task creation."""
    from windagent_core.domain.types import SessionId
    from windagent_core.domain.models import SessionStatus
    from windagent_storage.repositories.sql_repositories import SqlSessionRepository

    session_repo = SqlSessionRepository(uow.session)
    session = await session_repo.get_by_id(SessionId(session_id))

    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    content = payload.get("content", "")

    # Get next sequence number for this session stream
    existing_events = await uow.events.get_events(
        stream_id=session_id, after_sequence=0, limit=1000
    )
    next_sequence = len(existing_events) + 1

    # Emit message_received event with proper sequence and session_id
    from windagent_core.events.envelope import EventEnvelope
    from windagent_core.domain.lifecycle import utc_now
    from uuid import uuid4
    from windagent_core.domain.types import SessionId

    event = EventEnvelope(
        event_id=uuid4(),
        event_type="message_received",
        aggregate_id=session_id,
        aggregate_type="session",
        session_id=SessionId(session_id),
        payload={"sender": "user", "content": content},
        occurred_at=utc_now(),
        sequence=next_sequence,
    )
    await uow.events.append_event(event)

    # Record in durable event store for WebSocket replay
    from windagent_api.routers.v2_events import record_event_durable

    record_event_durable(event)

    # Update session status
    session.transition_to(SessionStatus.RUNNING)
    await session_repo.save(session)
    await uow.commit()

    return {
        "message_id": str(event.event_id),
        "status": "accepted",
    }
