"""Sessions router: create, fetch, send message."""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from schemas.session import (
    ChatSession,
    CreateSessionResponse,
    Message,
    SendMessageRequest,
)
from services.session_service import SessionService
from services.workflow_service import WorkflowService


router = APIRouter(prefix="/sessions", tags=["sessions"])


def _session_service(request: Request) -> SessionService:
    return request.app.state.session_service


def _workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


@router.post(
    "",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(request: Request) -> CreateSessionResponse:
    svc = _session_service(request)
    chat = await svc.create_session()
    return CreateSessionResponse(
        session_id=chat.id,
        created_at=chat.created_at,
        status=chat.status,
    )


@router.get("/{session_id}", response_model=ChatSession)
async def get_session(session_id: UUID, request: Request) -> ChatSession:
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")
    return chat


@router.post(
    "/{session_id}/messages",
    response_model=Dict[str, Any],
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    session_id: UUID, payload: SendMessageRequest, request: Request
) -> Dict[str, Any]:
    sessions = _session_service(request)
    workflows = _workflow_service(request)

    chat = await sessions.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    msg: Message = await sessions.add_user_message(session_id, payload.content)
    workflow = await workflows.create_for_message(
        session_id=session_id,
        message_id=msg.id,
        content=payload.content,
    )
    await sessions.update_status(session_id, "pending")

    # Phase 5: kick off the workflow runner as a background task. If the
    # workflow has 0 steps (unknown intent) the runner exits immediately.
    runner = request.app.state.workflow_runner
    runner.start(session_id=session_id, workflow_id=workflow.workflow_id)

    return {
        "message_id": str(msg.id),
        "workflow_id": str(workflow.workflow_id),
        "step_count": len(workflow.steps),
    }