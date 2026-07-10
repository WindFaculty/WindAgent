"""Agents router — registration, routing, state, and list actions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request, status
from pydantic import BaseModel

from services.agent_registry_service import AgentRegistryService

router = APIRouter(prefix="/agents", tags=["agents"])


def _service(request: Request) -> AgentRegistryService:
    return request.app.state.agent_registry_service


class AgentCreatePayload(BaseModel):
    id: str
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    runtime_type: str = "hermes"
    hermes_profile: str = "default"
    router_role: Optional[str] = None
    status: str = "offline"
    workspace_root: Optional[str] = None
    system_prompt: Optional[str] = None
    toolsets: List[str] = []
    skills: List[str] = []
    memory_enabled: bool = False
    max_concurrent_sessions: int = 5
    auto_start: bool = False


class AgentUpdatePayload(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    runtime_type: Optional[str] = None
    hermes_profile: Optional[str] = None
    router_role: Optional[str] = None
    status: Optional[str] = None
    workspace_root: Optional[str] = None
    system_prompt: Optional[str] = None
    toolsets: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    memory_enabled: Optional[bool] = None
    max_concurrent_sessions: Optional[int] = None
    auto_start: Optional[bool] = None


@router.get("", response_model=List[Dict[str, Any]])
async def list_agents(request: Request) -> List[Dict[str, Any]]:
    """List all registered agents."""
    svc = _service(request)
    return await svc.list_agents()


@router.get("/summary", response_model=Dict[str, Any])
async def get_summary(request: Request) -> Dict[str, Any]:
    """Retrieve summarized operational metrics for the agents registry."""
    svc = _service(request)
    return await svc.get_summary_metrics()


@router.get("/{agent_id}", response_model=Dict[str, Any])
async def get_agent(agent_id: str, request: Request) -> Dict[str, Any]:
    """Fetch details of a single agent."""
    svc = _service(request)
    agent = await svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent


@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreatePayload, request: Request) -> Dict[str, Any]:
    """Register a new agent configuration in the directory."""
    svc = _service(request)
    existing = await svc.get_agent(payload.id)
    if existing:
        raise HTTPException(status_code=400, detail=f"Agent with ID '{payload.id}' already exists")
    return await svc.create_agent(payload.model_dump())


@router.patch("/{agent_id}", response_model=Dict[str, Any])
async def update_agent(agent_id: str, payload: AgentUpdatePayload, request: Request) -> Dict[str, Any]:
    """Update details of an agent configuration."""
    svc = _service(request)
    # Filter out None values to avoid overwriting existing properties with None
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    agent = await svc.update_agent(agent_id, data)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, request: Request) -> Dict[str, Any]:
    """Remove an agent configuration from the registry."""
    svc = _service(request)
    deleted = await svc.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"status": "success", "message": f"Agent '{agent_id}' deleted successfully."}


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str, request: Request) -> Dict[str, Any]:
    """Change agent status to Idle/Running."""
    svc = _service(request)
    agent = await svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    await svc.update_status(agent_id, "Idle")
    return {"status": "success", "agent_id": agent_id, "state": "Idle"}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str, request: Request) -> Dict[str, Any]:
    """Stop agent execution, changing status to Offline."""
    svc = _service(request)
    agent = await svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    await svc.update_status(agent_id, "Offline")
    return {"status": "success", "agent_id": agent_id, "state": "Offline"}


@router.post("/{agent_id}/restart")
async def restart_agent(agent_id: str, request: Request) -> Dict[str, Any]:
    """Restart agent execution context, resetting status to Idle."""
    svc = _service(request)
    agent = await svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    await svc.update_status(agent_id, "Idle")
    return {"status": "success", "agent_id": agent_id, "state": "Idle"}


@router.get("/{agent_id}/sessions", response_model=List[Dict[str, Any]])
async def get_agent_sessions(agent_id: str, request: Request) -> List[Dict[str, Any]]:
    """List session histories belonging to this agent."""
    svc = _service(request)
    return await svc.list_agent_sessions(agent_id)


@router.get("/{agent_id}/activity", response_model=List[Dict[str, Any]])
async def get_agent_activity(agent_id: str, request: Request) -> List[Dict[str, Any]]:
    """Fetch recent activity timeline log of this agent."""
    # We can mock this by returning recent action summaries from sessions,
    # or simple timestamps.
    svc = _service(request)
    agent = await svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    
    sessions = await svc.list_agent_sessions(agent_id)
    activities = []
    for s in sessions[:5]: # Take last 5 sessions
        activities.append({
            "time": s["started_at"],
            "message": f"Started session {s['id'][:8]} in workspace {s['workspace_root'] or 'default'}",
        })
        if s["finished_at"]:
            activities.append({
                "time": s["finished_at"],
                "message": f"Finished session {s['id'][:8]} with status {s['status']}",
            })
            
    # Default fallback if no runs yet
    if not activities:
        activities = [
            {"time": agent["created_at"], "message": f"Agent registered in registry"}
        ]
    return activities
