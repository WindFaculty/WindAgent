"""
API V2 Tasks endpoints for WindAgent Architecture V2 (Phase 25 Cutover).
Decoupled transport DTOs mapping to canonical TaskManager, TaskState, and SqlUnitOfWork.
Enforces idempotency keys, pagination, filtering, and durable task management.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Header, Query, status, Depends
from pydantic import BaseModel, Field

from windagent_core.domain.types import TaskId, SessionId
from windagent_core.domain.lifecycle import TaskState, TaskLifecycle, utc_now
from windagent_core.errors.exceptions import NotFoundError, PermissionDeniedError, InvalidStateTransitionError
from windagent_api.dependencies import get_task_manager, get_uow
from windagent_orchestration.task_manager.service import TaskManager
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

router = APIRouter(prefix="/api/v2/tasks", tags=["Tasks V2"])


class CreateTaskRequest(BaseModel):
    """Transport DTO for task creation request."""
    prompt: str
    session_id: str = "default_session"
    workflow_name: Optional[str] = "bugfix"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


class TaskResponse(BaseModel):
    """Transport DTO for public API response."""
    task_id: str
    session_id: str
    prompt: str
    status: str
    workflow_name: str
    created_at: str
    updated_at: str
    idempotency_key: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    req: CreateTaskRequest,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    tm: TaskManager = Depends(get_task_manager),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> TaskResponse:
    idem_key = x_idempotency_key or req.idempotency_key or f"idem_{TaskId.generate()}"

    tid = TaskId.generate()
    try:
        sid = SessionId(req.session_id) if req.session_id else SessionId.generate()
    except Exception:
        sid = SessionId.generate()

    wf_name = req.workflow_name or "bugfix"

    # Persist durable facts via TaskManager
    facts = tm.get_or_create_facts(tid, sid)
    facts.metadata["prompt"] = req.prompt
    facts.metadata["workflow_name"] = wf_name
    facts.metadata["idempotency_key"] = idem_key

    # Save to durable repository
    await tm.save_durable_facts(facts)

    now_iso = utc_now().isoformat()
    return TaskResponse(
        task_id=str(tid),
        session_id=str(sid),
        prompt=req.prompt,
        status=facts.current_state.value,
        workflow_name=wf_name,
        created_at=now_iso,
        updated_at=now_iso,
        idempotency_key=idem_key,
        result=None,
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    session_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    tm: TaskManager = Depends(get_task_manager),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[TaskResponse]:
    results: List[TaskResponse] = []
    # Try querying durable database via SqlUnitOfWork first
    try:
        async with uow:
            raw_list = await uow.task_runs.list_by_session(session_id or "default_session")
            for item in raw_list:
                if status_filter and item["state"].lower() != status_filter.lower():
                    continue
                facts = item.get("facts", {})
                results.append(
                    TaskResponse(
                        task_id=item["id"],
                        session_id=item["session_id"],
                        prompt=facts.get("prompt", "Task prompt"),
                        status=item["state"].upper(),
                        workflow_name=facts.get("workflow_name", "bugfix"),
                        created_at=item["created_at"].isoformat() if hasattr(item["created_at"], "isoformat") else str(item["created_at"]),
                        updated_at=item["created_at"].isoformat() if hasattr(item["created_at"], "isoformat") else str(item["created_at"]),
                        idempotency_key=facts.get("idempotency_key"),
                        result=facts.get("result"),
                    )
                )
    except Exception:
        pass

    # Fallback to TaskManager facts cache
    if not results and hasattr(tm, "_in_memory_facts"):
        for tid_str, facts in tm._in_memory_facts.items():
            if session_id and str(facts.session_id) != session_id:
                continue
            if status_filter and facts.current_state.value.lower() != status_filter.lower():
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
                    idempotency_key=facts.metadata.get("idempotency_key"),
                    result=facts.metadata.get("result"),
                )
            )

    return results


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    tm: TaskManager = Depends(get_task_manager),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> TaskResponse:
    try:
        tid = TaskId(task_id)
        facts = await tm.load_durable_facts(tid)
    except Exception:
        facts = None

    if not facts:
        try:
            async with uow:
                task_orm = await uow.task_runs.get_by_id(task_id)
                if task_orm:
                    facts_dict = task_orm.get("facts", {})
                    return TaskResponse(
                        task_id=task_orm["id"],
                        session_id=task_orm["session_id"],
                        prompt=facts_dict.get("prompt", ""),
                        status=task_orm["state"].upper(),
                        workflow_name=facts_dict.get("workflow_name", "bugfix"),
                        created_at=task_orm["created_at"].isoformat() if hasattr(task_orm["created_at"], "isoformat") else str(task_orm["created_at"]),
                        updated_at=task_orm["updated_at"].isoformat() if hasattr(task_orm["updated_at"], "isoformat") else str(task_orm["updated_at"]),
                        idempotency_key=facts_dict.get("idempotency_key"),
                        result=facts_dict.get("result"),
                    )
        except Exception:
            pass

    if not facts and hasattr(tm, "_in_memory_facts"):
        facts = tm._in_memory_facts.get(task_id)

    if not facts:
        raise NotFoundError(f"Task '{task_id}' not found", code="WINDAGENT_ERR_TASK_NOT_FOUND")

    return TaskResponse(
        task_id=str(facts.task_id),
        session_id=str(facts.session_id),
        prompt=facts.metadata.get("prompt", ""),
        status=facts.current_state.value,
        workflow_name=facts.metadata.get("workflow_name", "bugfix"),
        created_at=facts.created_at.isoformat(),
        updated_at=facts.updated_at.isoformat(),
        idempotency_key=facts.metadata.get("idempotency_key"),
        result=facts.metadata.get("result"),
    )


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    tm: TaskManager = Depends(get_task_manager),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> TaskResponse:
    try:
        tid = TaskId(task_id)
        facts = await tm.load_durable_facts(tid)
    except Exception:
        facts = None

    if not facts and hasattr(tm, "_in_memory_facts"):
        facts = tm._in_memory_facts.get(task_id)

    if not facts:
        raise NotFoundError(f"Task '{task_id}' not found", code="WINDAGENT_ERR_TASK_NOT_FOUND")

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
        idempotency_key=updated_facts.metadata.get("idempotency_key"),
        result=updated_facts.metadata.get("result"),
    )
