"""Workflow router: read the workflow bound to a session + control surface.

Phase 5: pause / resume / stop talk to Orchestration V2 engine.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from schemas.event import EventEnvelope, UserControlData
from schemas.workflow import Workflow
from services.event_bus import EventBus
from services.session_service import SessionService
from windagent_orchestration import TaskState


router = APIRouter(tags=["workflow"])


def _bus(request: Request) -> EventBus:
    return request.app.state.event_bus


@router.get("/sessions/{session_id}/workflow", response_model=Workflow)
async def get_session_workflow(session_id: UUID, request: Request) -> Workflow:
    sessions: SessionService = request.app.state.session_service
    chat = await sessions.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    tm = request.app.state.task_manager
    facts = tm.get_or_create_facts(str(session_id), str(session_id))
    return Workflow(
        id=session_id,
        session_id=session_id,
        steps=[],
    )


@router.get("/sessions/{session_id}/runner")
async def get_runner_state(session_id: UUID, request: Request) -> Dict[str, Any]:
    sessions: SessionService = request.app.state.session_service
    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    
    tm = request.app.state.task_manager
    facts = tm.get_or_create_facts(str(session_id), str(session_id))
    return {
        "session_id": str(session_id),
        "runner": {
            "status": facts.derive_ui_status(),
            "task_done": facts.current_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED),
        },
    }


async def _emit_user_event(
    request: Request,
    session_id: UUID,
    event_name: str,
) -> Dict[str, Any]:
    sessions: SessionService = request.app.state.session_service
    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    tm = request.app.state.task_manager
    facts = tm.get_or_create_facts(str(session_id), str(session_id))

    if event_name == "user_paused":
        tm.transition_task(str(session_id), str(session_id), TaskState.PAUSED)
    elif event_name == "user_resumed":
        tm.transition_task(str(session_id), str(session_id), TaskState.RUNNING)
    elif event_name == "user_stopped":
        tm.transition_task(str(session_id), str(session_id), TaskState.CANCELLED)

    bus: EventBus = _bus(request)
    env = EventEnvelope(
        event=event_name,
        data=UserControlData(
            session_id=session_id,
            workflow_id=None,
        ).model_dump(mode="json"),
    )
    await bus.publish(str(session_id), env)

    return {
        "status": f"{event_name.replace('user_', '')}_requested",
        "workflow_id": None,
    }


@router.post("/sessions/{session_id}/pause", status_code=status.HTTP_202_ACCEPTED)
async def pause_session(session_id: UUID, request: Request) -> Dict[str, Any]:
    return await _emit_user_event(request, session_id, "user_paused")


@router.post("/sessions/{session_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_session(session_id: UUID, request: Request) -> Dict[str, Any]:
    return await _emit_user_event(request, session_id, "user_resumed")


@router.post("/sessions/{session_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_session(session_id: UUID, request: Request) -> Dict[str, Any]:
    return await _emit_user_event(request, session_id, "user_stopped")


@router.post(
    "/workflow/{step_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_step(step_id: UUID, request: Request) -> Dict[str, Any]:
    return {
        "status": "retry_requested",
        "workflow_id": None,
        "step_id": str(step_id),
    }