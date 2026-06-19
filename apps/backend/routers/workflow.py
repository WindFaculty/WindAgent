"""Workflow router: read the workflow bound to a session + control surface.

Phase 5: pause / resume / stop now talk to the WorkflowRunner. The runner
emits the `user_*` events back to subscribers (echo pattern), and updates
the workflow / session status as appropriate.
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from schemas.event import EventEnvelope, UserControlData
from schemas.workflow import Workflow
from services.event_bus import EventBus
from services.session_service import SessionService
from services.workflow_runner import WorkflowRunner
from services.workflow_service import WorkflowService


router = APIRouter(tags=["workflow"])


def _bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def _runner(request: Request) -> WorkflowRunner:
    return request.app.state.workflow_runner


@router.get("/sessions/{session_id}/workflow", response_model=Workflow)
async def get_session_workflow(session_id: UUID, request: Request) -> Workflow:
    sessions: SessionService = request.app.state.session_service
    workflows: WorkflowService = request.app.state.workflow_service

    chat = await sessions.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    wf = await workflows.get_for_session(session_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="no workflow for this session")
    return wf


@router.get("/sessions/{session_id}/runner")
async def get_runner_state(session_id: UUID, request: Request) -> Dict[str, Any]:
    """Inspect the in-memory runner state for a session.

    Phase 5 — useful for the frontend to render control button states
    (disabled when task is done, etc.).
    """
    sessions: SessionService = request.app.state.session_service
    runner = _runner(request)
    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    state = runner.get_state(session_id)
    if state is None:
        # Session exists but no runner has been started (e.g. 0-step workflow).
        return {
            "session_id": str(session_id),
            "runner": None,
        }
    return {"session_id": str(session_id), "runner": state}


async def _emit_user_event(
    request: Request,
    session_id: UUID,
    event_name: str,
) -> Dict[str, Any]:
    """Ask the runner to act, then echo the user_* event back to subscribers.

    Returns a small JSON body for the HTTP caller. 404 if no runner is
    tracking the session.
    """
    runner = _runner(request)
    state = runner.get_state(session_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail="no active runner for this session",
        )
    if state["task_done"]:
        raise HTTPException(
            status_code=409,
            detail="workflow already finished",
        )

    if event_name == "user_paused":
        ok = runner.pause(session_id)
    elif event_name == "user_resumed":
        ok = runner.resume(session_id)
    elif event_name == "user_stopped":
        ok = runner.stop(session_id)
    else:
        raise HTTPException(status_code=400, detail=f"unknown event {event_name}")
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=f"runner rejected {event_name}",
        )

    bus: EventBus = _bus(request)
    workflow_id = state.get("workflow_id")
    env = EventEnvelope(
        event=event_name,
        data=UserControlData(
            session_id=session_id,
            workflow_id=UUID(workflow_id) if workflow_id else None,
        ).model_dump(mode="json"),
    )
    await bus.publish(str(session_id), env)

    return {
        "status": f"{event_name.replace('user_', '')}_requested",
        "workflow_id": workflow_id,
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
    """Re-run the workflow from the step with the given id.

    Resolves the session from the step_id by walking in-memory workflows
    (small N). If the workflow has no recorded runner state, the call 404s.
    """
    workflows: WorkflowService = request.app.state.workflow_service
    runner = _runner(request)

    target_session: UUID | None = None
    for wf in (await _all_workflows(workflows)):
        if any(s.id == step_id for s in wf.steps):
            target_session = wf.session_id
            break
    if target_session is None:
        raise HTTPException(status_code=404, detail="step not found")

    state = runner.get_state(target_session)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail="no runner for the owning session",
        )

    ok = runner.retry(target_session)
    if not ok:
        raise HTTPException(status_code=409, detail="runner refused retry")

    return {
        "status": "retry_requested",
        "workflow_id": state["workflow_id"],
        "step_id": str(step_id),
    }


async def _all_workflows(workflows: WorkflowService):
    """Helper — current WorkflowService only exposes get_for_session.

    We walk all workflows via the underlying in-memory dict. Cheap for MVP.
    """
    return list(workflows._workflows.values())  # type: ignore[attr-defined]