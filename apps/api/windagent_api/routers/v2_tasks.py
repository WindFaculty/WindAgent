"""
API V2 Tasks endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v2/tasks", tags=["Tasks V2"])

# In-memory store for demonstration & API contract testing
IN_MEMORY_TASKS: Dict[str, Dict[str, Any]] = {}


class CreateTaskRequest(BaseModel):
    prompt: str
    workflow_name: Optional[str] = None
    session_id: str = "default_session"
    parameters: Dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task_id: str
    prompt: str
    status: str
    workflow_name: str
    session_id: str
    created_at: str
    result: Optional[Dict[str, Any]] = None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(req: CreateTaskRequest) -> TaskResponse:
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    wf_name = req.workflow_name or "bugfix"
    task_data = {
        "task_id": task_id,
        "prompt": req.prompt,
        "status": "CREATED",
        "workflow_name": wf_name,
        "session_id": req.session_id,
        "created_at": "2026-07-23T19:00:00Z",
        "result": None
    }
    IN_MEMORY_TASKS[task_id] = task_data
    return TaskResponse(**task_data)


@router.get("", response_model=List[TaskResponse])
async def list_tasks(session_id: Optional[str] = None) -> List[TaskResponse]:
    if session_id:
        tasks = [t for t in IN_MEMORY_TASKS.values() if t["session_id"] == session_id]
    else:
        tasks = list(IN_MEMORY_TASKS.values())
    return [TaskResponse(**t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    if task_id not in IN_MEMORY_TASKS:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return TaskResponse(**IN_MEMORY_TASKS[task_id])


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str) -> TaskResponse:
    if task_id not in IN_MEMORY_TASKS:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    task = IN_MEMORY_TASKS[task_id]
    task["status"] = "CANCELLED"
    return TaskResponse(**task)
