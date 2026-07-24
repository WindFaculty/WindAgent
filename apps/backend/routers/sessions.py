"""Sessions router: create, fetch, send message."""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from schemas.session import (
    ChatSession,
    CreateSessionRequest,
    CreateSessionResponse,
    Message,
    SendMessageRequest,
)
from schemas.event import EventEnvelope
from services.session_service import SessionService
from services.phase14_compatibility import WorkflowRunner, WorkflowService
from db.models import (
    AgentORM,
    AgentSessionORM,
    ParentTaskORM,
    TaskPlanORM,
    TaskNodeORM,
)
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
                hermes_sess_id = None
                if agent.runtime_type == "hermes":
                    bridge = request.app.state.hermes_session_bridge
                    hermes_sess_id = await bridge.create_session(
                        windagent_session_id=str(chat.id),
                        agent_id=payload.agent_id,
                        workspace_root=payload.workspace_root or agent.workspace_root
                    )

                agent_sess = AgentSessionORM(
                    id=str(uuid.uuid4()),
                    windagent_session_id=str(chat.id),
                    agent_id=payload.agent_id,
                    runtime_type=agent.runtime_type,
                    status="idle",
                    workspace_root=payload.workspace_root or agent.workspace_root,
                    router_role=agent.router_role,
                    started_at=chat.created_at,
                    hermes_session_id=hermes_sess_id,
                )
                db_sess.add(agent_sess)

    return CreateSessionResponse(
        session_id=chat.id,
        created_at=chat.created_at,
        status=chat.status,
    )


@router.get("", response_model=List[Dict[str, Any]])
async def list_sessions(
    request: Request,
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    exclude_archived: bool = True,
) -> List[Dict[str, Any]]:
    svc = _session_service(request)
    return await svc.list_sessions(
        limit=limit, offset=offset, exclude_archived=exclude_archived
    )


@router.get("/{session_id}", response_model=ChatSession)
async def get_session(session_id: UUID, request: Request) -> ChatSession:
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")
    return chat


@router.get("/{session_id}/snapshot")
async def get_session_snapshot(session_id: UUID, request: Request) -> Dict[str, Any]:
    svc = _session_service(request)
    snap = await svc.get_session_snapshot(session_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="session not found")
    return snap


@router.get("/{session_id}/events")
async def get_session_events(
    session_id: UUID,
    request: Request,
    after_seq: int = Query(0, ge=0),
) -> Dict[str, Any]:
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    events: List[Dict[str, Any]] = []
    if request.app.state.db is not None:
        async with request.app.state.db.session() as s:
            from db.models import ExecutionEventORM
            from sqlalchemy import select
            import json
            rows = (await s.execute(
                select(ExecutionEventORM)
                .where(
                    ExecutionEventORM.session_id == str(session_id),
                    ExecutionEventORM.event_seq > after_seq,
                )
                .order_by(ExecutionEventORM.event_seq)
            )).scalars().all()
            for r in rows:
                data = json.loads(r.data_json or "{}")
                events.append({
                    "seq": r.event_seq,
                    "event": r.event_type,
                    "event_type": r.event_type,
                    "data": data,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })
    return {
        "session_id": str(session_id),
        "events": events,
    }


@router.post("/{session_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_session(session_id: UUID, request: Request):
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")
    await svc.update_status(session_id, "cancelled")


@router.post("/{session_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_session(session_id: UUID, request: Request):
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    runner = getattr(request.app.state, "workflow_runner", None)
    if runner:
        runner.stop(session_id)

    bridge = getattr(request.app.state, "hermes_session_bridge", None)
    if bridge and hasattr(bridge, "stop_run"):
        try:
            await bridge.stop_run(str(session_id))
        except Exception:
            pass

    if request.app.state.db is not None:
        async with request.app.state.db.session() as s:
            stmt = select(AgentSessionORM).where(AgentSessionORM.windagent_session_id == str(session_id))
            res = await s.execute(stmt)
            agent_sess = res.scalar_one_or_none()
            if agent_sess:
                agent_sess.status = "cancelled"
                await s.commit()

    bus = getattr(request.app.state, "event_bus", None)
    if bus is not None:
        await bus.publish(
            str(session_id),
            EventEnvelope(
                event="user_stopped",
                data={"session_id": str(session_id)},
            ),
        )

    await svc.update_status(session_id, "cancelled")
    return {"session_id": str(session_id), "status": "stopped_requested"}


@router.post("/{session_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_session(session_id: UUID, request: Request):
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")
    await svc.archive_session(session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: UUID, request: Request):
    svc = _session_service(request)
    chat = await svc.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")
    await svc.delete_session(session_id)


@router.get("/{session_id}/messages", response_model=List[Message])
async def list_session_messages(session_id: UUID, request: Request) -> List[Message]:
    sessions = _session_service(request)
    chat = await sessions.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    async with request.app.state.db.session() as db_sess:
        stmt = select(AgentSessionORM).where(AgentSessionORM.windagent_session_id == str(session_id))
        res = await db_sess.execute(stmt)
        agent_sess = res.scalar_one_or_none()

    if agent_sess and agent_sess.runtime_type == "hermes" and agent_sess.hermes_session_id:
        bridge = request.app.state.hermes_session_bridge
        await bridge.sync_messages(str(session_id), agent_sess.hermes_session_id)
        sessions._sessions.pop(session_id, None)
        await sessions.get_session(session_id)

    return sessions.list_messages(session_id)


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
        supervisor = request.app.state.hermes_supervisor
        route_lock_service = request.app.state.route_lock_service
        dag_scheduler = request.app.state.dag_scheduler
        worktree_service = request.app.state.worktree_service
        db = request.app.state.db

        msg = await sessions.add_user_message(session_id, payload.content)
        await sessions.update_status(session_id, "running")

        # 1) Validate workspace root before anything else.
        agent = None
        async with db.session() as db_sess:
            stmt_agent = select(AgentORM).where(AgentORM.id == agent_sess.agent_id)
            agent = (await db_sess.execute(stmt_agent)).scalar_one_or_none()
        base_root = agent_sess.workspace_root or (agent.workspace_root if agent else None)
        safe_workspace_root = base_root
        if safe_workspace_root and worktree_service is not None:
            try:
                safe_workspace_root = worktree_service.safe_workspace_root(base_root)
            except Exception:
                safe_workspace_root = None

        # 2) Ensure orchestrator for this conversation.
        await supervisor.ensure_orchestrator(conversation_id=str(session_id), agent_id=agent_sess.agent_id)

        # 3) Acquire route lock for this session.
        canonical_model_id = agent.router_role or "Coder"
        lock = await route_lock_service.acquire_lock(
            scope_type="conversation",
            scope_id=str(session_id),
            canonical_model_id=canonical_model_id,
        )

        run_info = await bridge.submit_message(
            windagent_session_id=str(session_id),
            agent_id=agent_sess.agent_id,
            content=payload.content,
            workspace_root=safe_workspace_root,
        )

        # 4) Persist minimal orchestration artifacts around this turn.
        parent_task_id = f"parent:{session_id}"
        plan_id = f"plan:{session_id}:{msg.id}"
        async with db.session() as db_sess:
            parent = await db_sess.get(ParentTaskORM, parent_task_id)
            if parent is None:
                db_sess.add(ParentTaskORM(
                    id=parent_task_id,
                    conversation_id=str(session_id),
                    title="Live chat orchestration",
                    status="active",
                ))
                plan = TaskPlanORM(
                    id=plan_id,
                    parent_task_id=parent_task_id,
                    version=1,
                    status="active",
                )
                db_sess.add(plan)
                node = TaskNodeORM(
                    id=f"node:{session_id}:{msg.id}",
                    plan_id=plan_id,
                    title="User turn",
                    status="assigned",
                    agent_type="hermes_chat",
                    max_retries=0,
                    retry_count=0,
                )
                db_sess.add(node)
                await db_sess.commit()

        # 5) Run the single-node plan.
        try:
            await dag_scheduler.run_plan(plan_id)
        except Exception:
            pass

        return {
            "message_id": str(msg.id),
            "hermes_run_id": run_info["run_id"],
            "hermes_session_id": run_info["session_id"],
            "step_count": 1,
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