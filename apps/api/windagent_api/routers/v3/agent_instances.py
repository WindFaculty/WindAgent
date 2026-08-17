"""
V3 Agent Instances Router — Canonical Agent Runtime Authority (Phase 11).
Manages running/idle/stopped agent instances with lifecycle commands (start, stop, restart).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v3", tags=["Agent Instances V3"])


class AgentInstanceResource(BaseModel):
    id: str
    definition_id: str
    conversation_id: Optional[str] = None
    status: str = "IDLE"
    canonical_model_id: Optional[str] = None
    provider_binding_id: Optional[str] = None
    route_lock_id: Optional[str] = None
    assigned_task_id: Optional[str] = None
    current_tool: Optional[str] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    runtime_metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: str
    updated_at: str


class LaunchAgentInstanceRequest(BaseModel):
    definition_id: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    canonical_model_id: Optional[str] = None
    runtime_metadata: Dict[str, Any] = Field(default_factory=dict)


_INSTANCES_STORE: Dict[str, Dict[str, Any]] = {
    "inst-orch-01": {
        "id": "inst-orch-01",
        "definition_id": "def-orchestrator-01",
        "conversation_id": "conv-default-01",
        "status": "RUNNING",
        "canonical_model_id": "gemini-1.5-pro",
        "provider_binding_id": "prov-vertex-01",
        "route_lock_id": "lock-orch-01",
        "assigned_task_id": "task-orch-goal-01",
        "current_tool": "plan_decomposition",
        "started_at": "2026-08-16T09:00:00Z",
        "stopped_at": None,
        "runtime_metadata": {"uptime_seconds": 3600, "active_turns": 12},
        "version": 1,
        "created_at": "2026-08-16T09:00:00Z",
        "updated_at": "2026-08-16T09:00:00Z",
    },
    "inst-coder-01": {
        "id": "inst-coder-01",
        "definition_id": "def-coder-01",
        "conversation_id": "conv-default-01",
        "status": "IDLE",
        "canonical_model_id": "claude-3-5-sonnet",
        "provider_binding_id": "prov-anthropic-01",
        "route_lock_id": "lock-coder-01",
        "assigned_task_id": None,
        "current_tool": None,
        "started_at": "2026-08-16T09:02:00Z",
        "stopped_at": None,
        "runtime_metadata": {"uptime_seconds": 3480, "active_turns": 8},
        "version": 1,
        "created_at": "2026-08-16T09:02:00Z",
        "updated_at": "2026-08-16T09:02:00Z",
    }
}


@router.get("/agent-instances", response_model=List[AgentInstanceResource])
async def list_agent_instances(
    conversation_id: Optional[str] = Query(None),
    definition_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
) -> List[AgentInstanceResource]:
    results = list(_INSTANCES_STORE.values())
    if conversation_id:
        results = [i for i in results if i.get("conversation_id") == conversation_id]
    if definition_id:
        results = [i for i in results if i.get("definition_id") == definition_id]
    if status_filter:
        results = [i for i in results if i.get("status", "").upper() == status_filter.upper()]
    return [AgentInstanceResource(**i) for i in results]


@router.post("/agent-instances", response_model=AgentInstanceResource, status_code=status.HTTP_201_CREATED)
async def launch_agent_instance(req: LaunchAgentInstanceRequest) -> AgentInstanceResource:
    inst_id = f"inst-{uuid.uuid4().hex[:8]}"
    now_iso = utc_now().isoformat()
    instance_data = {
        "id": inst_id,
        "definition_id": req.definition_id,
        "conversation_id": req.conversation_id,
        "status": "RUNNING",
        "canonical_model_id": req.canonical_model_id or "default-model",
        "provider_binding_id": f"binding-{inst_id}",
        "route_lock_id": f"lock-{inst_id}",
        "assigned_task_id": None,
        "current_tool": None,
        "started_at": now_iso,
        "stopped_at": None,
        "runtime_metadata": req.runtime_metadata,
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _INSTANCES_STORE[inst_id] = instance_data
    return AgentInstanceResource(**instance_data)


@router.get("/agent-instances/{instance_id}", response_model=AgentInstanceResource)
async def get_agent_instance(instance_id: str) -> AgentInstanceResource:
    if instance_id not in _INSTANCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    return AgentInstanceResource(**_INSTANCES_STORE[instance_id])


@router.post("/agent-instances/{instance_id}/start", response_model=AgentInstanceResource)
async def start_agent_instance(instance_id: str) -> AgentInstanceResource:
    if instance_id not in _INSTANCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    inst = _INSTANCES_STORE[instance_id]
    inst["status"] = "RUNNING"
    inst["started_at"] = utc_now().isoformat()
    inst["stopped_at"] = None
    inst["version"] += 1
    inst["updated_at"] = utc_now().isoformat()
    _INSTANCES_STORE[instance_id] = inst
    return AgentInstanceResource(**inst)


@router.post("/agent-instances/{instance_id}/stop", response_model=AgentInstanceResource)
async def stop_agent_instance(instance_id: str) -> AgentInstanceResource:
    if instance_id not in _INSTANCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    inst = _INSTANCES_STORE[instance_id]
    inst["status"] = "TERMINATED"
    inst["stopped_at"] = utc_now().isoformat()
    inst["current_tool"] = None
    inst["version"] += 1
    inst["updated_at"] = utc_now().isoformat()
    _INSTANCES_STORE[instance_id] = inst
    return AgentInstanceResource(**inst)


@router.post("/agent-instances/{instance_id}/restart", response_model=AgentInstanceResource)
async def restart_agent_instance(instance_id: str) -> AgentInstanceResource:
    if instance_id not in _INSTANCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    inst = _INSTANCES_STORE[instance_id]
    now_iso = utc_now().isoformat()
    inst["status"] = "RUNNING"
    inst["started_at"] = now_iso
    inst["stopped_at"] = None
    inst["current_tool"] = None
    inst["version"] += 1
    inst["updated_at"] = now_iso
    _INSTANCES_STORE[instance_id] = inst
    return AgentInstanceResource(**inst)
