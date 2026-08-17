"""
V3 Conversations Router — Canonical Conversation Authority (Phase 11).
Serves durable conversation projections, linking PlanVersion, AgentInstance,
Task, and Event projections.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.routers.v3.agent_instances import (
    _INSTANCES_STORE,
    AgentInstanceResource,
)
from windagent_api.routers.v3.tasks import (
    _TASKS_STORE,
    TaskResource,
)

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


_CONVERSATIONS_STORE: Dict[str, Dict[str, Any]] = {
    "conv-default-01": {
        "id": "conv-default-01",
        "title": "Core System Architecture Convergence",
        "objective": "Unify agent workspace, definitions, tasks, and workflows into V3 architecture",
        "status": "ACTIVE",
        "plan_version_id": "pv-01",
        "orchestrator_instance_id": "inst-orch-01",
        "version": 1,
        "created_at": "2026-08-16T09:00:00Z",
        "updated_at": "2026-08-16T09:00:00Z",
    }
}

_CONVERSATION_EVENTS: Dict[str, List[Dict[str, Any]]] = {
    "conv-default-01": [
        {
            "event_id": "evt-01",
            "conversation_id": "conv-default-01",
            "event_type": "conversation.started",
            "timestamp": "2026-08-16T09:00:00Z",
            "payload": {"objective": "Unify agent workspace, definitions, tasks, and workflows"},
        },
        {
            "event_id": "evt-02",
            "conversation_id": "conv-default-01",
            "event_type": "agent.instance.started",
            "timestamp": "2026-08-16T09:00:01Z",
            "payload": {"instance_id": "inst-orch-01", "role": "orchestrator"},
        },
        {
            "event_id": "evt-03",
            "conversation_id": "conv-default-01",
            "event_type": "task.ready",
            "timestamp": "2026-08-16T09:05:00Z",
            "payload": {"task_id": "task-03", "objective": "Run regression test suite"},
        }
    ]
}


@router.get("/conversations", response_model=List[ConversationResource])
async def list_conversations() -> List[ConversationResource]:
    return [ConversationResource(**c) for c in _CONVERSATIONS_STORE.values()]


@router.post("/conversations", response_model=ConversationResource, status_code=status.HTTP_201_CREATED)
async def create_conversation(req: CreateConversationRequest) -> ConversationResource:
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    now_iso = utc_now().isoformat()
    orch_inst_id = f"inst-orch-{uuid.uuid4().hex[:6]}"

    conv_data = {
        "id": conv_id,
        "title": req.title or f"Workspace Session {conv_id[-6:]}",
        "objective": req.objective,
        "status": "ACTIVE",
        "plan_version_id": f"pv-{uuid.uuid4().hex[:6]}",
        "orchestrator_instance_id": orch_inst_id,
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _CONVERSATIONS_STORE[conv_id] = conv_data

    # Create associated orchestrator instance
    _INSTANCES_STORE[orch_inst_id] = {
        "id": orch_inst_id,
        "definition_id": "def-orchestrator-01",
        "conversation_id": conv_id,
        "status": "RUNNING",
        "canonical_model_id": "gemini-1.5-pro",
        "provider_binding_id": f"binding-{orch_inst_id}",
        "route_lock_id": f"lock-{orch_inst_id}",
        "assigned_task_id": None,
        "current_tool": "plan_decomposition",
        "started_at": now_iso,
        "stopped_at": None,
        "runtime_metadata": {},
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    _CONVERSATION_EVENTS[conv_id] = [
        {
            "event_id": f"evt-{uuid.uuid4().hex[:8]}",
            "conversation_id": conv_id,
            "event_type": "conversation.started",
            "timestamp": now_iso,
            "payload": {"objective": req.objective},
        }
    ]

    return ConversationResource(**conv_data)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResource)
async def get_conversation(conversation_id: str) -> ConversationDetailResource:
    if conversation_id not in _CONVERSATIONS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    conv = _CONVERSATIONS_STORE[conversation_id]
    agents = [
        AgentInstanceResource(**inst)
        for inst in _INSTANCES_STORE.values()
        if inst.get("conversation_id") == conversation_id
    ]
    tasks = [
        TaskResource(**t)
        for t in _TASKS_STORE.values()
        if t.get("conversation_id") == conversation_id
    ]
    events = _CONVERSATION_EVENTS.get(conversation_id, [])

    return ConversationDetailResource(
        conversation=ConversationResource(**conv),
        plan_versions=[{"plan_version_id": conv.get("plan_version_id", "pv-01"), "version": 1}],
        agents=agents,
        tasks=tasks,
        events=events,
    )


@router.get("/conversations/{conversation_id}/agents", response_model=List[AgentInstanceResource])
async def get_conversation_agents(conversation_id: str) -> List[AgentInstanceResource]:
    if conversation_id not in _CONVERSATIONS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    return [
        AgentInstanceResource(**inst)
        for inst in _INSTANCES_STORE.values()
        if inst.get("conversation_id") == conversation_id
    ]


@router.get("/conversations/{conversation_id}/tasks", response_model=List[TaskResource])
async def get_conversation_tasks(conversation_id: str) -> List[TaskResource]:
    if conversation_id not in _CONVERSATIONS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    return [
        TaskResource(**t)
        for t in _TASKS_STORE.values()
        if t.get("conversation_id") == conversation_id
    ]


@router.get("/conversations/{conversation_id}/events", response_model=List[Dict[str, Any]])
async def get_conversation_events(conversation_id: str) -> List[Dict[str, Any]]:
    if conversation_id not in _CONVERSATIONS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    return _CONVERSATION_EVENTS.get(conversation_id, [])


@router.post("/conversations/{conversation_id}/agents/{agent_id}/stop", response_model=AgentInstanceResource)
async def stop_conversation_agent(conversation_id: str, agent_id: str) -> AgentInstanceResource:
    if conversation_id not in _CONVERSATIONS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found",
        )
    if agent_id not in _INSTANCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent instance '{agent_id}' not found",
        )
    inst = _INSTANCES_STORE[agent_id]
    inst["status"] = "TERMINATED"
    inst["stopped_at"] = utc_now().isoformat()
    inst["version"] += 1
    inst["updated_at"] = utc_now().isoformat()
    _INSTANCES_STORE[agent_id] = inst
    return AgentInstanceResource(**inst)
