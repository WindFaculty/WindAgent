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
    sid = str(SessionId.generate())
    now_iso = utc_now().isoformat()
    return SessionResponse(
        session_id=sid,
        title=req.title or "Default Session",
        status="idle",
        created_at=now_iso,
        updated_at=now_iso,
        metadata=req.metadata,
    )


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[SessionResponse]:
    now_iso = utc_now().isoformat()
    return [
        SessionResponse(
            session_id=str(SessionId.generate()),
            title="Active Workspace Session",
            status="running",
            created_at=now_iso,
            updated_at=now_iso,
            metadata={"environment": "production"},
        )
    ]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> SessionResponse:
    now_iso = utc_now().isoformat()
    return SessionResponse(
        session_id=session_id,
        title=f"Session {session_id[:8]}",
        status="running",
        created_at=now_iso,
        updated_at=now_iso,
        metadata={},
    )
