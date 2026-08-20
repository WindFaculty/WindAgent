"""
V3 Tasks Router — Canonical Task & Task Graph Authority (Phase 11).
Enforces the 7-state canonical task state machine:
PENDING, READY, RUNNING, BLOCKED, SUCCEEDED, FAILED, CANCELLED.
Provides optimistic locking, cancel, retry, and dependency management.

Phase 4: all mutable state is persisted through the namespaced durable V3
resource authority. No module-level RAM stores.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_TASKS

router = APIRouter(prefix="/api/v3", tags=["Tasks V3"])

CANONICAL_TASK_STATES = {
    "PENDING",
    "READY",
    "RUNNING",
    "BLOCKED",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
}


class TaskResource(BaseModel):
    id: str
    conversation_id: str
    objective: str
    state: str = "PENDING"
    assigned_agent_instance_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    concurrency_group: Optional[str] = None
    attempts: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    version: int = 1
    created_at: str
    updated_at: str


class CreateTaskRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    assigned_agent_instance_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    concurrency_group: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    objective: Optional[str] = None
    state: Optional[str] = None
    assigned_agent_instance_id: Optional[str] = None
    dependencies: Optional[List[str]] = None
    concurrency_group: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    expected_version: int


def _task_to_resource(t: Dict[str, Any]) -> TaskResource:
    return TaskResource(
        id=t["id"],
        conversation_id=t["conversation_id"],
        objective=t["objective"],
        state=t.get("state", "PENDING"),
        assigned_agent_instance_id=t.get("assigned_agent_instance_id"),
        parent_task_id=t.get("parent_task_id"),
        dependencies=t.get("dependencies", []),
        concurrency_group=t.get("concurrency_group"),
        attempts=t.get("attempts", 0),
        result=t.get("result"),
        error=t.get("error"),
        version=t.get("version", 1),
        created_at=t.get("created_at", ""),
        updated_at=t.get("updated_at", ""),
    )


@router.get("/tasks", response_model=List[TaskResource])
async def list_tasks(
    conversation_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    assigned_agent_instance_id: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[TaskResource]:
    results = await service.list(NS_TASKS)
    if conversation_id:
        results = [t for t in results if t.get("conversation_id") == conversation_id]
    if state:
        results = [t for t in results if t.get("state", "").upper() == state.upper()]
    if assigned_agent_instance_id:
        results = [t for t in results if t.get("assigned_agent_instance_id") == assigned_agent_instance_id]
    return [_task_to_resource(t) for t in results]


@router.post("/tasks", response_model=TaskResource, status_code=status.HTTP_201_CREATED)
async def create_task(
    req: CreateTaskRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> TaskResource:
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    now_iso = utc_now().isoformat()
    task_data = {
        "id": task_id,
        "conversation_id": req.conversation_id,
        "objective": req.objective,
        "state": "READY" if not req.dependencies else "PENDING",
        "assigned_agent_instance_id": req.assigned_agent_instance_id,
        "parent_task_id": req.parent_task_id,
        "dependencies": req.dependencies,
        "concurrency_group": req.concurrency_group,
        "attempts": 0,
        "result": None,
        "error": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    created = await service.create(NS_TASKS, task_id, task_data)
    return _task_to_resource(created)


@router.get("/tasks/{task_id}", response_model=TaskResource)
async def get_task(
    task_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> TaskResource:
    task = await service.get(NS_TASKS, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return _task_to_resource(task)


@router.patch("/tasks/{task_id}", response_model=TaskResource)
async def update_task(
    task_id: str,
    req: UpdateTaskRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> TaskResource:
    task = await service.get(NS_TASKS, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )

    if task["version"] != req.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Expected version {req.expected_version} does not match current version {task['version']}",
        )

    updates = dict(task)
    if req.state is not None:
        state_upper = req.state.upper()
        if state_upper not in CANONICAL_TASK_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid task state '{req.state}'. Must be one of {CANONICAL_TASK_STATES}",
            )
        updates["state"] = state_upper

    if req.objective is not None:
        updates["objective"] = req.objective
    if req.assigned_agent_instance_id is not None:
        updates["assigned_agent_instance_id"] = req.assigned_agent_instance_id
    if req.dependencies is not None:
        updates["dependencies"] = req.dependencies
    if req.concurrency_group is not None:
        updates["concurrency_group"] = req.concurrency_group
    if req.result is not None:
        updates["result"] = req.result
    if req.error is not None:
        updates["error"] = req.error
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_TASKS, task_id, updates, req.expected_version)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Expected version {req.expected_version} does not match current version",
        )
    return _task_to_resource(updated)


@router.post("/tasks/{task_id}/cancel", response_model=TaskResource)
async def cancel_task(
    task_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> TaskResource:
    task = await service.get(NS_TASKS, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    updates = dict(task)
    updates["state"] = "CANCELLED"
    updates["updated_at"] = utc_now().isoformat()
    updated = await service.update(NS_TASKS, task_id, updates, task["version"])
    return _task_to_resource(updated)


@router.post("/tasks/{task_id}/retry", response_model=TaskResource)
async def retry_task(
    task_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> TaskResource:
    task = await service.get(NS_TASKS, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    updates = dict(task)
    updates["state"] = "READY"
    updates["attempts"] = task.get("attempts", 0) + 1
    updates["error"] = None
    updates["updated_at"] = utc_now().isoformat()
    updated = await service.update(NS_TASKS, task_id, updates, task["version"])
    return _task_to_resource(updated)
