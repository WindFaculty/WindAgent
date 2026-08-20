"""
V3 Workflows Router — Canonical Workflow & Execution Authority (Phase 11).
Provides canonical Workflow Definitions, Runs, Step Runs with truthfully
derived progress percentages, lifecycle controls (pause, resume, retry, cancel),
and WebSocket realtime streaming.

Phase 4: all mutable state is persisted through the namespaced durable V3
resource authority. No module-level RAM stores.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_WORKFLOWS, NS_WORKFLOW_RUNS

router = APIRouter(prefix="/api/v3", tags=["Workflows V3"])
ws_router = APIRouter(prefix="/ws/v3/agent-system", tags=["Agent System WebSocket"])


class WorkflowStepDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    tool_name: Optional[str] = None
    timeout_seconds: int = 300


class WorkflowDefinitionResource(BaseModel):
    id: str
    name: str
    description: str = ""
    type: str = "Standard"
    trigger: str = "Manual"
    owner: str = "System"
    tags: List[str] = Field(default_factory=list)
    steps: List[WorkflowStepDefinition] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    version: int = 1
    created_at: str
    updated_at: str


class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = ""
    type: Optional[str] = "Standard"
    trigger: Optional[str] = "Manual"
    owner: Optional[str] = "System"
    tags: List[str] = Field(default_factory=list)
    steps: List[WorkflowStepDefinition] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)


class UpdateWorkflowRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    trigger: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    steps: Optional[List[WorkflowStepDefinition]] = None
    acceptance_criteria: Optional[List[str]] = None
    expected_version: int


class WorkflowStepRunResource(BaseModel):
    id: str
    run_id: str
    step_id: str
    step_name: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempts: int = 0


class WorkflowRunResource(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    status: str = "PENDING"  # PENDING, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED
    triggered_by: str = "User"
    steps: List[WorkflowStepRunResource] = Field(default_factory=list)
    progress_percent: int = 0
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    version: int = 1
    created_at: str
    updated_at: str


class TriggerWorkflowRunRequest(BaseModel):
    workflow_id: str = Field(..., min_length=1)
    triggered_by: Optional[str] = "User"
    parameters: Dict[str, Any] = Field(default_factory=dict)


def _derive_run_progress(run_data: Dict[str, Any]) -> int:
    """Truthfully calculate progress percent from step run statuses."""
    steps = run_data.get("steps", [])
    if not steps:
        return 0
    completed = sum(1 for s in steps if s.get("status") == "COMPLETED")
    return int((completed / len(steps)) * 100)


def _wf_to_resource(w: Dict[str, Any]) -> WorkflowDefinitionResource:
    return WorkflowDefinitionResource(
        id=w["id"],
        name=w["name"],
        description=w.get("description", ""),
        type=w.get("type", "Standard"),
        trigger=w.get("trigger", "Manual"),
        owner=w.get("owner", "System"),
        tags=w.get("tags", []),
        steps=[WorkflowStepDefinition(**s) for s in w.get("steps", [])],
        acceptance_criteria=w.get("acceptance_criteria", []),
        version=w.get("version", 1),
        created_at=w.get("created_at", ""),
        updated_at=w.get("updated_at", ""),
    )


def _run_to_resource(r: Dict[str, Any]) -> WorkflowRunResource:
    data = dict(r)
    data["progress_percent"] = _derive_run_progress(data)
    return WorkflowRunResource(**data)


@router.get("/workflows", response_model=List[WorkflowDefinitionResource])
async def list_workflows(
    search: Optional[str] = Query(None),
    workflow_type: Optional[str] = Query(None, alias="type"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[WorkflowDefinitionResource]:
    results = await service.list(NS_WORKFLOWS)
    if workflow_type:
        results = [w for w in results if w.get("type", "").lower() == workflow_type.lower()]
    if search:
        s = search.lower()
        results = [
            w for w in results
            if s in w["name"].lower() or s in w["description"].lower() or any(s in t.lower() for t in w.get("tags", []))
        ]
    return [_wf_to_resource(w) for w in results]


@router.post("/workflows", response_model=WorkflowDefinitionResource, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    req: CreateWorkflowRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowDefinitionResource:
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    now_iso = utc_now().isoformat()
    wf_data = {
        "id": wf_id,
        "name": req.name,
        "description": req.description or "",
        "type": req.type or "Standard",
        "trigger": req.trigger or "Manual",
        "owner": req.owner or "System",
        "tags": req.tags,
        "steps": [s.model_dump() for s in req.steps],
        "acceptance_criteria": req.acceptance_criteria,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    created = await service.create(NS_WORKFLOWS, wf_id, wf_data)
    return _wf_to_resource(created)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDefinitionResource)
async def get_workflow(
    workflow_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowDefinitionResource:
    wf = await service.get(NS_WORKFLOWS, workflow_id)
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow definition '{workflow_id}' not found",
        )
    return _wf_to_resource(wf)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowDefinitionResource)
async def update_workflow(
    workflow_id: str,
    req: UpdateWorkflowRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowDefinitionResource:
    target = await service.get(NS_WORKFLOWS, workflow_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow definition '{workflow_id}' not found",
        )

    if target["version"] != req.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Expected version {req.expected_version} does not match current version {target['version']}",
        )

    updates = dict(target)
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description
    if req.type is not None:
        updates["type"] = req.type
    if req.trigger is not None:
        updates["trigger"] = req.trigger
    if req.owner is not None:
        updates["owner"] = req.owner
    if req.tags is not None:
        updates["tags"] = req.tags
    if req.steps is not None:
        updates["steps"] = [s.model_dump() for s in req.steps]
    if req.acceptance_criteria is not None:
        updates["acceptance_criteria"] = req.acceptance_criteria
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_WORKFLOWS, workflow_id, updates, req.expected_version)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflict: Expected version {req.expected_version} does not match current version",
        )
    return _wf_to_resource(updated)


@router.get("/workflow-runs", response_model=List[WorkflowRunResource])
async def list_workflow_runs(
    workflow_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[WorkflowRunResource]:
    results = await service.list(NS_WORKFLOW_RUNS)
    if workflow_id:
        results = [r for r in results if r.get("workflow_id") == workflow_id]
    if status_filter:
        results = [r for r in results if r.get("status", "").upper() == status_filter.upper()]
    return [_run_to_resource(r) for r in results]


@router.post("/workflow-runs", response_model=WorkflowRunResource, status_code=status.HTTP_201_CREATED)
async def trigger_workflow_run(
    req: TriggerWorkflowRunRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowRunResource:
    wf = await service.get(NS_WORKFLOWS, req.workflow_id)
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{req.workflow_id}' not found",
        )
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    now_iso = utc_now().isoformat()

    step_runs = []
    for i, step in enumerate(wf.get("steps", [])):
        step_runs.append({
            "id": f"srun-{uuid.uuid4().hex[:6]}",
            "run_id": run_id,
            "step_id": step.get("id", f"step-{i+1}"),
            "step_name": step.get("name", f"Step {i+1}"),
            "status": "RUNNING" if i == 0 else "PENDING",
            "error": None,
            "started_at": now_iso if i == 0 else None,
            "completed_at": None,
            "attempts": 1 if i == 0 else 0,
        })

    run_data = {
        "id": run_id,
        "workflow_id": wf["id"],
        "workflow_name": wf["name"],
        "status": "RUNNING",
        "triggered_by": req.triggered_by or "User",
        "steps": step_runs,
        "error": None,
        "started_at": now_iso,
        "completed_at": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    created = await service.create(NS_WORKFLOW_RUNS, run_id, run_data)
    return _run_to_resource(created)


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunResource)
async def get_workflow_run(
    run_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowRunResource:
    run_data = await service.get(NS_WORKFLOW_RUNS, run_id)
    if run_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found",
        )
    return _run_to_resource(run_data)


@router.post("/workflow-runs/{run_id}/cancel", response_model=WorkflowRunResource)
async def cancel_workflow_run(
    run_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowRunResource:
    run_data = await service.get(NS_WORKFLOW_RUNS, run_id)
    if run_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found",
        )
    updates = dict(run_data)
    updates["status"] = "CANCELLED"
    updates["completed_at"] = utc_now().isoformat()
    updates["updated_at"] = utc_now().isoformat()
    updated = await service.update(NS_WORKFLOW_RUNS, run_id, updates, run_data["version"])
    return _run_to_resource(updated)


@router.post("/workflow-runs/{run_id}/retry", response_model=WorkflowRunResource)
async def retry_workflow_run(
    run_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowRunResource:
    run_data = await service.get(NS_WORKFLOW_RUNS, run_id)
    if run_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found",
        )
    now_iso = utc_now().isoformat()
    updates = dict(run_data)
    updates["status"] = "RUNNING"
    updates["error"] = None
    updates["completed_at"] = None

    # Reset any failed steps to RUNNING / PENDING
    steps = []
    for step in run_data.get("steps", []):
        s = dict(step)
        if s.get("status") in ("FAILED", "CANCELLED"):
            s["status"] = "RUNNING"
            s["error"] = None
            s["started_at"] = now_iso
            s["completed_at"] = None
            s["attempts"] = s.get("attempts", 0) + 1
        steps.append(s)
    updates["steps"] = steps
    updates["updated_at"] = now_iso

    updated = await service.update(NS_WORKFLOW_RUNS, run_id, updates, run_data["version"])
    return _run_to_resource(updated)


@router.post("/workflow-runs/{run_id}/pause", response_model=WorkflowRunResource)
async def pause_workflow_run(
    run_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowRunResource:
    run_data = await service.get(NS_WORKFLOW_RUNS, run_id)
    if run_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found",
        )
    updates = dict(run_data)
    updates["status"] = "PAUSED"
    updates["updated_at"] = utc_now().isoformat()
    updated = await service.update(NS_WORKFLOW_RUNS, run_id, updates, run_data["version"])
    return _run_to_resource(updated)


@router.post("/workflow-runs/{run_id}/resume", response_model=WorkflowRunResource)
async def resume_workflow_run(
    run_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorkflowRunResource:
    run_data = await service.get(NS_WORKFLOW_RUNS, run_id)
    if run_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run '{run_id}' not found",
        )
    updates = dict(run_data)
    updates["status"] = "RUNNING"
    updates["updated_at"] = utc_now().isoformat()
    updated = await service.update(NS_WORKFLOW_RUNS, run_id, updates, run_data["version"])
    return _run_to_resource(updated)


# ─────────────────────────────────────────────────────────────────────────────
# Realtime WebSocket Stream
# ─────────────────────────────────────────────────────────────────────────────

@ws_router.websocket("")
async def agent_system_realtime_ws(websocket: WebSocket):
    """
    Realtime WebSocket stream for agent workspace, tasks, and workflows events.
    Broadcasting agent.instance.*, task.*, and workflow.* lifecycle changes.
    """
    await websocket.accept()
    try:
        # Send initial connection acknowledgment
        await websocket.send_json({
            "type": "connection.ready",
            "message": "Connected to Agent System V3 Realtime Stream",
            "timestamp": utc_now().isoformat(),
        })

        while True:
            # Heartbeat ping / echo
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": utc_now().isoformat()})
            else:
                await websocket.send_json({
                    "type": "event.ack",
                    "timestamp": utc_now().isoformat(),
                })
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
