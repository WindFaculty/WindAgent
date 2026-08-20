"""
V3 Conversations Router — Canonical Conversation Authority (Phase 11).
Serves durable conversation projections, linking PlanVersion, AgentInstance,
Task, and Event projections.

Phase 4 (P4-R4B): conversations, agent instances, and conversation events are
read/written through the composed ``OrchestratorService`` seam onto the
dedicated multi-agent SQL authority. The generic ``v3_resources`` namespaces
``conversations``, ``agent_instances``, and ``conversation_events`` are never
touched by this router. The generic task resource projection remains a distinct
work-management aggregate (``NS_TASKS``).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from windagent_api.dependencies import get_orchestrator_service, get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_TASKS
from windagent_orchestration.orchestrator_service import OrchestratorService
from windagent_api.routers.v3.agent_instances import AgentInstanceResource
from windagent_api.routers.v3.tasks import TaskResource

router = APIRouter(prefix="/api/v3", tags=["Conversations V3"])


class ConversationResource(BaseModel):
    id: str
    title: str = "Multi-Agent Workspace Conversation"
    objective: str = ""
    status: str = "ACTIVE"
    plan_version_id: Optional[str] = None
    orchestrator_instance_id: Optional[str] = None
    version: int = 1
    created_at: str
    updated_at: str


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None
    objective: str = Field(..., min_length=1)


class ConversationDetailResource(BaseModel):
    conversation: ConversationResource
    plan_versions: List[Dict[str, Any]] = Field(default_factory=list)
    agents: List[AgentInstanceResource] = Field(default_factory=list)
    tasks: List[TaskResource] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)


def _conv_to_resource(c: Dict[str, Any]) -> ConversationResource:
    return ConversationResource(
        id=c["id"],
        title=c.get("title", "Multi-Agent Workspace Conversation"),
        objective=c.get("objective", ""),
        status=c.get("status", "ACTIVE"),
        plan_version_id=c.get("plan_version_id"),
        orchestrator_instance_id=c.get("orchestrator_instance_id"),
        version=c.get("version", 1),
        created_at=c.get("created_at", ""),
        updated_at=c.get("updated_at", ""),
    )


def _event_to_api(e: Dict[str, Any]) -> Dict[str, Any]:
    """Map a dedicated event-store row onto the existing V3 event shape."""
    return {
        "event_id": e.get("event_id"),
        "conversation_id": e.get("conversation_id"),
        "event_type": e.get("event_type"),
        "timestamp": e.get("created_at", ""),
        "payload": e.get("data", {}),
    }


@router.get("/conversations", response_model=List[ConversationResource])
async def list_conversations(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> List[ConversationResource]:
    convs = await orchestrator.list_conversations()
    return [_conv_to_resource(c) for c in convs]


@router.post("/conversations", response_model=ConversationResource, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    req: CreateConversationRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> ConversationResource:
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    created = await orchestrator.create_conversation(
        conversation_id=conv_id,
        title=req.title or f"Workspace Session {conv_id[-6:]}",
        objective=req.objective,
    )
    return _conv_to_resource(created)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResource)
async def get_conversation(
    conversation_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ConversationDetailResource:
    conv = await orchestrator.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )

    agents = await orchestrator.list_agent_instances(conversation_id)
    tasks = await service.list(NS_TASKS)
    tasks = [
        TaskResource(**t)
        for t in tasks
        if t.get("conversation_id") == conversation_id
    ]
    events = await orchestrator.conversation_events(conversation_id)

    return ConversationDetailResource(
        conversation=_conv_to_resource(conv),
        plan_versions=[{"plan_version_id": conv.get("plan_version_id", "pv-01"), "version": 1}],
        agents=[AgentInstanceResource(**a) for a in agents],
        tasks=tasks,
        events=[_event_to_api(e) for e in events],
    )


@router.get("/conversations/{conversation_id}/agents", response_model=List[AgentInstanceResource])
async def get_conversation_agents(
    conversation_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> List[AgentInstanceResource]:
    conv = await orchestrator.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    instances = await orchestrator.list_agent_instances(conversation_id)
    return [AgentInstanceResource(**inst) for inst in instances]


@router.get("/conversations/{conversation_id}/tasks", response_model=List[TaskResource])
async def get_conversation_tasks(
    conversation_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[TaskResource]:
    conv = await orchestrator.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    tasks = await service.list(NS_TASKS)
    return [
        TaskResource(**t)
        for t in tasks
        if t.get("conversation_id") == conversation_id
    ]


@router.get("/conversations/{conversation_id}/events", response_model=List[Dict[str, Any]])
async def get_conversation_events(
    conversation_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> List[Dict[str, Any]]:
    conv = await orchestrator.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    events = await orchestrator.conversation_events(conversation_id)
    return [_event_to_api(e) for e in events]


@router.post("/conversations/{conversation_id}/agents/{agent_id}/stop", response_model=AgentInstanceResource)
async def stop_conversation_agent(
    conversation_id: str,
    agent_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> AgentInstanceResource:
    conv = await orchestrator.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    updated = await orchestrator.stop_agent_instance(agent_id, conversation_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{agent_id}' not found",
        )
    return AgentInstanceResource(**updated)