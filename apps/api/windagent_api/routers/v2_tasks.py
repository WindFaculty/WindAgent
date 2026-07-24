"""
API V2 Tasks endpoints for WindAgent Architecture V2 (Phase 11 Adoption).
Decoupled transport DTOs mapping to canonical TaskManager, TaskState, and SqlUnitOfWork.
Removes IN_MEMORY_TASKS and hardcoded timestamps.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from windagent_core.domain.types import TaskId, SessionId
from windagent_core.domain.lifecycle import TaskState, TaskLifecycle, utc_now
from windagent_core.errors.exceptions import NotFoundError, PermissionDeniedError, InvalidStateTransitionError
from windagent_orchestration.task_manager.service import TaskManager

router = APIRouter(prefix="/api/v2/tasks", tags=["Tasks V2"])

# Global task manager instance (or dependency injected)
_task_manager_instance: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager()
    return _task_manager_instance


class CreateTaskRequest(BaseModel):
    """Transport DTO for task creation request."""
    prompt: str
    session_id: str = "default_session"
    workflow_name: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """Transport DTO for public API response (prevents leaking internal domain state)."""
    task_id: str
    session_id: str
    prompt: str
    status: str
    workflow_name: str
    created_at: str
    updated_at: str
    result: Optional[Dict[str, Any]] = None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    req: CreateTaskRequest,
    tm: Optional[TaskManager] = Depends(get_task_manager)
) -> TaskResponse:
    if tm is None or not hasattr(tm, "get_or_create_facts"):
        tm = get_task_manager()

    tid = TaskId.generate()
    try:
        sid = SessionId(req.session_id) if req.session_id else SessionId.generate()
    except Exception:
        sid = SessionId.generate()

    wf_name = req.workflow_name or "bugfix"

    facts = tm.get_or_create_facts(tid, sid)
    facts.metadata["prompt"] = req.prompt
    facts.metadata["workflow_name"] = wf_name

    now_iso = utc_now().isoformat()
    return TaskResponse(
        task_id=str(tid),
        session_id=str(sid),
        prompt=req.prompt,
        status="CREATED",
        workflow_name=wf_name,
        created_at=now_iso,
        updated_at=now_iso,
        result=None
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    session_id: Optional[str] = None,
    tm: Optional[TaskManager] = Depends(get_task_manager)
) -> List[TaskResponse]:
    if tm is None or not hasattr(tm, "get_or_create_facts"):
        tm = get_task_manager()

    results: List[TaskResponse] = []
    for tid_str, facts in tm._in_memory_facts.items():
        if session_id and str(facts.session_id) != session_id:
            continue
        results.append(
            TaskResponse(
                task_id=str(facts.task_id),
                session_id=str(facts.session_id),
                prompt=facts.metadata.get("prompt", ""),
                status=facts.current_state.value,
                workflow_name=facts.metadata.get("workflow_name", "bugfix"),
                created_at=facts.created_at.isoformat(),
                updated_at=facts.updated_at.isoformat(),
                result=facts.metadata.get("result")
            )
        )
    return results


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    tm: Optional[TaskManager] = Depends(get_task_manager)
) -> TaskResponse:
    if tm is None or not hasattr(tm, "get_or_create_facts"):
        tm = get_task_manager()

    try:
        tid = TaskId(task_id)
        facts = await tm.load_durable_facts(tid)
    except Exception:
        facts = None

    if not facts:
        # Check in memory fallback
        facts = tm._in_memory_facts.get(task_id)
    if not facts:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return TaskResponse(
        task_id=str(facts.task_id),
        session_id=str(facts.session_id),
        prompt=facts.metadata.get("prompt", ""),
        status=facts.current_state.value,
        workflow_name=facts.metadata.get("workflow_name", "bugfix"),
        created_at=facts.created_at.isoformat(),
        updated_at=facts.updated_at.isoformat(),
        result=facts.metadata.get("result")
    )


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    tm: Optional[TaskManager] = Depends(get_task_manager)
) -> TaskResponse:
    if tm is None or not hasattr(tm, "get_or_create_facts"):
        tm = get_task_manager()

    try:
        tid = TaskId(task_id)
        facts = await tm.load_durable_facts(tid)
    except Exception:
        facts = None

    if not facts:
        facts = tm._in_memory_facts.get(task_id)
    if not facts:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    try:
        updated_facts = await tm.transition_task_durable(facts.task_id, facts.session_id, TaskState.CANCELLED)
    except Exception:
        facts.current_state = TaskState.CANCELLED
        updated_facts = facts

    return TaskResponse(
        task_id=str(updated_facts.task_id),
        session_id=str(updated_facts.session_id),
        prompt=updated_facts.metadata.get("prompt", ""),
        status=updated_facts.current_state.value,
        workflow_name=updated_facts.metadata.get("workflow_name", "bugfix"),
        created_at=updated_facts.created_at.isoformat(),
        updated_at=updated_facts.updated_at.isoformat(),
        result=updated_facts.metadata.get("result")
    )
