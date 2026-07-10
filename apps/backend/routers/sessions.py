"""Sessions router: create, fetch, send message."""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from schemas.session import (
    ChatSession,
    CreateSessionRequest,
    CreateSessionResponse,
    Message,
    SendMessageRequest,
)
from services.session_service import SessionService
from services.workflow_service import WorkflowService
from db.models import AgentSessionORM, AgentORM
from sqlalchemy import select
import uuid


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
async def create_session(
    request: Request,
    payload: CreateSessionRequest = CreateSessionRequest(),
) -> CreateSessionResponse:
    svc = _session_service(request)
    chat = await svc.create_session()
    
    # Map this session to the requested agent
    if payload.agent_id:
        async with request.app.state.db.session() as db_sess:
            stmt = select(AgentORM).where(AgentORM.id == payload.agent_id)
            res = await db_sess.execute(stmt)
            agent = res.scalar_one_or_none()
            if agent:
                agent_sess = AgentSessionORM(
                    id=str(uuid.uuid4()),
                    windagent_session_id=str(chat.id),
                    agent_id=payload.agent_id,
                    runtime_type=agent.runtime_type,
                    status="idle",
                    workspace_root=payload.workspace_root or agent.workspace_root,
                    router_role=agent.router_role,
                    started_at=chat.created_at,
                )
                db_sess.add(agent_sess)

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

    # Check if this session is mapped to a hermes agent
    async with request.app.state.db.session() as db_sess:
        stmt = select(AgentSessionORM).where(AgentSessionORM.windagent_session_id == str(session_id))
        res = await db_sess.execute(stmt)
        agent_sess = res.scalar_one_or_none()

    if agent_sess and agent_sess.runtime_type == "hermes":
        bridge = request.app.state.hermes_session_bridge
        msg = await sessions.add_user_message(session_id, payload.content)
        await sessions.update_status(session_id, "running")
        
        # Start Hermes run in background
        run_info = await bridge.submit_message(
            windagent_session_id=str(session_id),
            agent_id=agent_sess.agent_id,
            content=payload.content,
            workspace_root=agent_sess.workspace_root,
        )
        return {
            "message_id": str(msg.id),
            "hermes_run_id": run_info["run_id"],
            "hermes_session_id": run_info["session_id"],
            "step_count": 0,
        }

    # Fallback to native workflow dispatching
    msg: Message = await sessions.add_user_message(session_id, payload.content)
    workflow = await workflows.create_for_message(
        session_id=session_id,
        message_id=msg.id,
        content=payload.content,
    )
    await sessions.update_status(session_id, "pending")

    runner = request.app.state.workflow_runner
    runner.start(session_id=session_id, workflow_id=workflow.workflow_id)

    return {
        "message_id": str(msg.id),
        "workflow_id": str(workflow.workflow_id),
        "step_count": len(workflow.steps),
    }