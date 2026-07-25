"""
Workflow router: read the workflow bound to a session + control surface.
Durable control surface interacting with Orchestration V2 engine and persistent database storage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from db.models import ParentTaskORM, TaskPlanORM, TaskNodeORM, WorkflowORM, WorkflowStepORM
from schemas.event import EventEnvelope, UserControlData
from schemas.workflow import Workflow, WorkflowStep
from services.event_bus import EventBus
from services.session_service import SessionService
from services.phase14_compatibility import (
    DAGScheduler,
    HermesSupervisor,
    WorkflowRunner,
    WorkflowService,
)
from windagent_orchestration import OrchestrationV2Container, TaskState
from windagent_orchestration.state_machine import WorkflowState, WorkflowStateMachine, StepState, StepStateMachine
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_core.domain.types import SessionId, EventId
from windagent_core.events.catalog import EventCatalog

router = APIRouter(tags=["workflow"])


def _bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def _workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


VALID_TOOL_NAMES = {"open_app", "open_url", "type_text", "hotkey", "press_key", "click_xy", "scroll", "screenshot", "wait"}


async def _load_workflow_steps(session_id: UUID, request: Request) -> Optional[Workflow]:
    """Return the session workflow from durable WorkflowORM storage if it exists."""
    db = request.app.state.db
    async with db.session() as s:
        wf = (await s.execute(
            select(WorkflowORM).where(WorkflowORM.session_id == str(session_id))
        )).scalars().first()
        if not wf:
            return None
        step_rows = (await s.execute(
            select(WorkflowStepORM).where(WorkflowStepORM.workflow_id == wf.id).order_by(WorkflowStepORM.order_index.asc())
        )).scalars().all()
        steps = [
            WorkflowStep(
                id=UUID(row.id),
                order=row.order_index,
                name=row.name,
                tool_name=row.tool_name if row.tool_name in VALID_TOOL_NAMES else "open_app",
                params={},
                status=row.status if row.status in ("pending", "running", "success", "failed", "skipped", "cancelled") else "pending",
            )
            for row in step_rows
        ]
        return Workflow(
            workflow_id=UUID(wf.id),
            session_id=session_id,
            created_at=wf.created_at,
            status=wf.status if wf.status in ("pending", "running", "paused", "completed", "failed", "cancelled") else "pending",  # type: ignore
            steps=steps,
        )


@router.get("/sessions/{session_id}/workflow", response_model=Workflow)
async def get_session_workflow(session_id: UUID, request: Request) -> Workflow:
    sessions: SessionService = request.app.state.session_service
    chat = await sessions.get_session(session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")

    db = request.app.state.db
    steps: List[WorkflowStep] = []
    wf_id = session_id
    created_at = chat.created_at if hasattr(chat, "created_at") and chat.created_at else datetime.now(timezone.utc)
    wf_status = "running" if chat.status == "running" else "pending"

    async with db.session() as s:
        pt = (await s.execute(
            select(ParentTaskORM).where(ParentTaskORM.conversation_id == str(session_id))
        )).scalars().first()
        if pt:
            plan = (await s.execute(
                select(TaskPlanORM).where(
                    TaskPlanORM.parent_task_id == pt.id,
                    TaskPlanORM.status == "active",
                )
            )).scalars().first()
            if plan:
                nodes = (await s.execute(
                    select(TaskNodeORM).where(TaskNodeORM.plan_id == plan.id).order_by(TaskNodeORM.id.asc())
                )).scalars().all()
                for idx, node in enumerate(nodes, start=1):
                    tool = node.agent_type if node.agent_type in VALID_TOOL_NAMES else "open_app"
                    st_val = node.status or "pending"
                    if st_val == "completed":
                        st_val = "success"
                    elif st_val not in ("pending", "running", "success", "failed", "skipped", "cancelled"):
                        st_val = "pending"

                    try:
                        node_uuid = UUID(node.id)
                    except ValueError:
                        node_uuid = UUID(f"00000000-0000-0000-0000-{idx:012d}")

                    steps.append(
                        WorkflowStep(
                            id=node_uuid,
                            order=idx,
                            name=node.title or f"Step {idx}",
                            tool_name=tool,  # type: ignore
                            params={},
                            status=st_val,  # type: ignore
                        )
                    )

    # Fallback to legacy backend workflow table (Phase 14 compatibility).
    if not steps:
        fallback = await _load_workflow_steps(session_id, request)
        if fallback:
            return fallback

    return Workflow(
        workflow_id=wf_id,
        session_id=session_id,
        created_at=created_at,
        status=wf_status,  # type: ignore
        steps=steps,
    )


@router.get("/sessions/{session_id}/runner")
async def get_runner_state(session_id: UUID, request: Request) -> Dict[str, Any]:
    sessions: SessionService = request.app.state.session_service
    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    
    db = request.app.state.db
    task_state = "idle"
    task_done = False

    async with db.session() as s:
        async with SqlUnitOfWork(db.session_factory) as uow:
            task_facts = await uow.task_runs.get_by_id(str(session_id))
            if task_facts:
                task_state = task_facts.get("state", "idle")
                task_done = task_state in (TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELLED.value)

    return {
        "session_id": str(session_id),
        "runner": {
            "status": task_state,
            "task_done": task_done,
        },
    }


async def _execute_durable_user_control(
    request: Request,
    session_id: UUID,
    event_name: str,
    target_state: TaskState,
) -> Dict[str, Any]:
    sessions: SessionService = request.app.state.session_service
    if await sessions.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Fail closed if no workflow exists for this session.
    try:
        existing_wf = await get_session_workflow(session_id, request)
    except HTTPException:
        existing_wf = None
    if existing_wf is None:
        raise HTTPException(status_code=404, detail="no workflow for session")

    tm = request.app.state.task_manager
    sid_str = str(session_id)
    
    # Check current facts and step through valid transitions
    facts = tm.get_or_create_facts(sid_str, sid_str)
    curr_state = facts.current_state

    if target_state == TaskState.CANCELLED:
        if curr_state != TaskState.CANCELLED:
            await tm.transition_task_durable(sid_str, sid_str, TaskState.CANCELLED)
    elif target_state == TaskState.PAUSED:
        if curr_state == TaskState.RECEIVED:
            await tm.transition_task_durable(sid_str, sid_str, TaskState.PLANNING)
            await tm.transition_task_durable(sid_str, sid_str, TaskState.RUNNING)
            await tm.transition_task_durable(sid_str, sid_str, TaskState.PAUSED)
        elif curr_state == TaskState.RUNNING:
            await tm.transition_task_durable(sid_str, sid_str, TaskState.PAUSED)
    elif target_state == TaskState.RUNNING:
        if curr_state in (TaskState.PAUSED, TaskState.WAITING_PERMISSION, TaskState.RETRY_WAIT):
            await tm.transition_task_durable(sid_str, sid_str, TaskState.RUNNING)
        elif curr_state == TaskState.RECEIVED:
            await tm.transition_task_durable(sid_str, sid_str, TaskState.PLANNING)
            await tm.transition_task_durable(sid_str, sid_str, TaskState.RUNNING)

    if event_name == "user_stopped":
        # Propagate cancellation to runtime manager / processes
        hermes_mgr = getattr(request.app.state, "hermes_runtime_manager", None)
        if hermes_mgr and hasattr(hermes_mgr, "stop"):
            try:
                await hermes_mgr.stop()
            except Exception:
                pass

    bus: EventBus = _bus(request)
    env = EventEnvelope(
        event=event_name,
        data=UserControlData(
            session_id=session_id,
            workflow_id=session_id,
        ).model_dump(mode="json"),
    )
    await bus.publish(sid_str, env)

    return {
        "status": f"{event_name.replace('user_', '')}_requested",
        "workflow_id": str(session_id),
    }


@router.post("/sessions/{session_id}/pause", status_code=status.HTTP_202_ACCEPTED)
async def pause_session(session_id: UUID, request: Request) -> Dict[str, Any]:
    return await _execute_durable_user_control(request, session_id, "user_paused", TaskState.PAUSED)


@router.post("/sessions/{session_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_session(session_id: UUID, request: Request) -> Dict[str, Any]:
    return await _execute_durable_user_control(request, session_id, "user_resumed", TaskState.RUNNING)


@router.post("/sessions/{session_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_session(session_id: UUID, request: Request) -> Dict[str, Any]:
    return await _execute_durable_user_control(request, session_id, "user_stopped", TaskState.CANCELLED)


@router.post(
    "/workflow/{step_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_step(step_id: UUID, request: Request) -> Dict[str, Any]:
    db = request.app.state.db
    step_str = str(step_id)
    found_node = None
    wf_id = None

    async with db.session() as s:
        node = await s.get(TaskNodeORM, step_str)
        if node:
            node.status = "ready"
            node.started_at = None
            node.finished_at = None
            found_node = node
            wf_id = node.plan_id
            await s.commit()

    # Phase 14: fallback to legacy WorkflowStepORM for native workflows.
    if not found_node:
        async with db.session() as s:
            step = await s.get(WorkflowStepORM, step_str)
            if step:
                step.status = "pending"
                step.started_at = None
                step.finished_at = None
                wf_id = step.workflow_id
                found_node = step
                await s.commit()

    if not found_node:
        raise HTTPException(status_code=404, detail="Step not found for retry")

    # Re-enqueue step via scheduler if available
    scheduler = getattr(request.app.state, "orchestration_scheduler", None)
    if scheduler and hasattr(scheduler, "enqueue"):
        scheduler.enqueue(step_str)

    return {
        "status": "retry_requested",
        "workflow_id": wf_id,
        "step_id": step_str,
        "attempt_index": 2,
    }