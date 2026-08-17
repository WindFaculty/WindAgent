"""
V3 Tasks Router — Canonical Task & Task Graph Authority (Phase 11).
Enforces the 7-state canonical task state machine:
PENDING, READY, RUNNING, BLOCKED, SUCCEEDED, FAILED, CANCELLED.
Provides optimistic locking, cancel, retry, and dependency management.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

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


_TASKS_STORE: Dict[str, Dict[str, Any]] = {
    "task-01": {
        "id": "task-01",
        "conversation_id": "conv-default-01",
        "objective": "Deconstruct target requirement and verify system prerequisites",
        "state": "SUCCEEDED",
        "assigned_agent_instance_id": "inst-orch-01",
        "parent_task_id": None,
        "dependencies": [],
        "concurrency_group": "init",
        "attempts": 1,
        "result": {"status": "verified", "nodes_generated": 3},
        "error": None,
        "version": 2,
        "created_at": "2026-08-16T09:00:00Z",
        "updated_at": "2026-08-16T09:04:00Z",
    },
    "task-02": {
        "id": "task-02",
        "conversation_id": "conv-default-01",
        "objective": "Synthesize backend endpoints and schema validation",
        "state": "RUNNING",
        "assigned_agent_instance_id": "inst-coder-01",
        "parent_task_id": "task-01",
        "dependencies": ["task-01"],
        "concurrency_group": "execution",
        "attempts": 1,
        "result": None,
        "error": None,
        "version": 1,
        "created_at": "2026-08-16T09:05:00Z",
        "updated_at": "2026-08-16T09:05:00Z",
    },
    "task-03": {
        "id": "task-03",
        "conversation_id": "conv-default-01",
        "objective": "Run regression test suite and verify contract invariants",
        "state": "READY",
        "assigned_agent_instance_id": None,
        "parent_task_id": "task-01",
        "dependencies": ["task-02"],
        "concurrency_group": "verification",
        "attempts": 0,
        "result": None,
        "error": None,
        "version": 1,
        "created_at": "2026-08-16T09:05:00Z",
        "updated_at": "2026-08-16T09:05:00Z",
    }
}


@router.get("/tasks", response_model=List[TaskResource])
async def list_tasks(
    conversation_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    assigned_agent_instance_id: Optional[str] = Query(None),
) -> List[TaskResource]:
    results = list(_TASKS_STORE.values())
    if conversation_id:
        results = [t for t in results if t.get("conversation_id") == conversation_id]
    if state:
        results = [t for t in results if t.get("state", "").upper() == state.upper()]
    if assigned_agent_instance_id:
        results = [t for t in results if t.get("assigned_agent_instance_id") == assigned_agent_instance_id]
    return [TaskResource(**t) for t in results]


@router.post("/tasks", response_model=TaskResource, status_code=status.HTTP_201_CREATED)
async def create_task(req: CreateTaskRequest) -> TaskResource:
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
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _TASKS_STORE[task_id] = task_data
    return TaskResource(**task_data)


@router.get("/tasks/{task_id}", response_model=TaskResource)
async def get_task(task_id: str) -> TaskResource:
    if task_id not in _TASKS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return TaskResource(**_TASKS_STORE[task_id])


@router.patch("/tasks/{task_id}", response_model=TaskResource)
async def update_task(task_id: str, req: UpdateTaskRequest) -> TaskResource:
    if task_id not in _TASKS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    task = _TASKS_STORE[task_id]

    if task["version"] != req.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Expected version {req.expected_version} does not match current version {task['version']}",
        )

    if req.state is not None:
        state_upper = req.state.upper()
        if state_upper not in CANONICAL_TASK_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid task state '{req.state}'. Must be one of {CANONICAL_TASK_STATES}",
            )
        task["state"] = state_upper

    if req.objective is not None:
        task["objective"] = req.objective
    if req.assigned_agent_instance_id is not None:
        task["assigned_agent_instance_id"] = req.assigned_agent_instance_id
    if req.dependencies is not None:
        task["dependencies"] = req.dependencies
    if req.concurrency_group is not None:
        task["concurrency_group"] = req.concurrency_group
    if req.result is not None:
        task["result"] = req.result
    if req.error is not None:
        task["error"] = req.error

    task["version"] += 1
    task["updated_at"] = utc_now().isoformat()
    _TASKS_STORE[task_id] = task
    return TaskResource(**task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskResource)
async def cancel_task(task_id: str) -> TaskResource:
    if task_id not in _TASKS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    task = _TASKS_STORE[task_id]
    task["state"] = "CANCELLED"
    task["version"] += 1
    task["updated_at"] = utc_now().isoformat()
    _TASKS_STORE[task_id] = task
    return TaskResource(**task)


@router.post("/tasks/{task_id}/retry", response_model=TaskResource)
async def retry_task(task_id: str) -> TaskResource:
    if task_id not in _TASKS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    task = _TASKS_STORE[task_id]
    task["state"] = "READY"
    task["attempts"] += 1
    task["error"] = None
    task["version"] += 1
    task["updated_at"] = utc_now().isoformat()
    _TASKS_STORE[task_id] = task
    return TaskResource(**task)
