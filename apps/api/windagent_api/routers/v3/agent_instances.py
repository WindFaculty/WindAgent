"""
V3 Agent Instances Router — Canonical Agent Runtime Authority (Phase 11).
Manages running/idle/stopped agent instances with lifecycle commands (start, stop, restart).

Phase 4 (P4-R4B): agent instances are persisted through the composed
``OrchestratorService`` seam onto the dedicated multi-agent SQL authority. The
generic ``v3_resources:agent_instances`` namespace is never touched. The
referenced generic agent definition is validated in the router; the actual
instance plus session is persisted through the orchestrator seam.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_api.dependencies import get_orchestrator_service, get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_AGENT_DEFINITIONS
from windagent_core.errors.exceptions import NotFoundError
from windagent_orchestration.orchestrator_service import OrchestratorService

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


def _inst_to_resource(i: Dict[str, Any]) -> AgentInstanceResource:
    return AgentInstanceResource(
        id=i["id"],
        definition_id=i["definition_id"],
        conversation_id=i.get("conversation_id"),
        status=i.get("status", "IDLE"),
        canonical_model_id=i.get("canonical_model_id"),
        provider_binding_id=i.get("provider_binding_id"),
        route_lock_id=i.get("route_lock_id"),
        assigned_task_id=i.get("assigned_task_id"),
        current_tool=i.get("current_tool"),
        started_at=i.get("started_at"),
        stopped_at=i.get("stopped_at"),
        runtime_metadata=i.get("runtime_metadata", {}),
        version=i.get("version", 1),
        created_at=i.get("created_at", ""),
        updated_at=i.get("updated_at", ""),
    )


async def _require_definition(
    service: V3ResourceService, definition_id: str
) -> Dict[str, Any]:
    """Validate the referenced generic agent definition before launch.

    Returns the definition record so the caller can persist its actual
    ``role`` as the canonical ``agent_type`` instead of discarding it.
    """
    definitions = await service.list(NS_AGENT_DEFINITIONS)
    for d in definitions:
        if d["id"] == definition_id or d.get("slug") == definition_id:
            return d
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Agent definition '{definition_id}' not found",
    )


async def _require_conversation(
    orchestrator: OrchestratorService, conversation_id: Optional[str]
) -> None:
    """Validate the canonical conversation identity before launch.

    A missing conversation is a client error (HTTP 400); an unknown
    conversation is a not-found error (HTTP 404). Neither may surface as an
    unhandled integrity error / internal 500.
    """
    if not conversation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation_id is required to launch an agent instance",
        )
    conv = await orchestrator.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )


@router.get("/agent-instances", response_model=List[AgentInstanceResource])
async def list_agent_instances(
    conversation_id: Optional[str] = Query(None),
    definition_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> List[AgentInstanceResource]:
    results = await orchestrator.list_agent_instances(conversation_id)
    if definition_id:
        results = [i for i in results if i.get("definition_id") == definition_id]
    if status_filter:
        results = [i for i in results if i.get("status", "").upper() == status_filter.upper()]
    return [_inst_to_resource(i) for i in results]


@router.post("/agent-instances", response_model=AgentInstanceResource, status_code=status.HTTP_201_CREATED)
async def launch_agent_instance(
    req: LaunchAgentInstanceRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AgentInstanceResource:
    definition = await _require_definition(service, req.definition_id)
    await _require_conversation(orchestrator, req.conversation_id)
    inst_id = f"inst-{uuid.uuid4().hex[:8]}"
    try:
        created = await orchestrator.launch_agent(
            agent_instance_id=inst_id,
            conversation_id=req.conversation_id,
            definition_id=req.definition_id,
            agent_type=definition.get("role") or "generalist",
            canonical_model_id=req.canonical_model_id,
            runtime_metadata=req.runtime_metadata,
        )
    except NotFoundError as exc:
        # The transaction-local conversation check in ``launch_agent`` is
        # authoritative. Even if the preflight above passed, an unknown
        # conversation surfaced inside the launch transaction must map to the
        # existing HTTP 404 contract, never an unhandled integrity 500.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
    return _inst_to_resource(created)


@router.get("/agent-instances/{instance_id}", response_model=AgentInstanceResource)
async def get_agent_instance(
    instance_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> AgentInstanceResource:
    inst = await orchestrator.get_agent_instance(instance_id)
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    return _inst_to_resource(inst)


@router.post("/agent-instances/{instance_id}/start", response_model=AgentInstanceResource)
async def start_agent_instance(
    instance_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> AgentInstanceResource:
    try:
        updated = await orchestrator.start_agent(instance_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    return _inst_to_resource(updated)


@router.post("/agent-instances/{instance_id}/stop", response_model=AgentInstanceResource)
async def stop_agent_instance(
    instance_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> AgentInstanceResource:
    updated = await orchestrator.stop_agent_instance(instance_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    return _inst_to_resource(updated)


@router.post("/agent-instances/{instance_id}/restart", response_model=AgentInstanceResource)
async def restart_agent_instance(
    instance_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> AgentInstanceResource:
    try:
        updated = await orchestrator.restart_agent(instance_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{instance_id}' not found",
        )
    return _inst_to_resource(updated)