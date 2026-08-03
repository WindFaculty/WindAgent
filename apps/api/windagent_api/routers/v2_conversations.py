"""Canonical conversation API for the multi-agent workspace (Phase 2)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from windagent_api.dependencies import get_orchestrator_service
from windagent_orchestration.orchestrator_service import (
    OrchestratorService,
    PlanRevisionConflict,
    Subtask,
)
from windagent_orchestration.release.rollout import ReleaseNotActive
from windagent_providers.base.errors import ProviderFailure, SameModelEndpointExhausted


router = APIRouter(prefix="/api/v2/conversations", tags=["Conversations V2"])


class SubtaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    node_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    concurrency_group: str | None = None


class SubmitGoalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=255)
    subtasks: list[SubtaskRequest] = Field(default_factory=list)


class AgentLaunchResponse(BaseModel):
    agent_instance_id: str
    agent_session_id: str
    agent_run_id: str
    node_id: str
    agent_type: str
    runtime_run_id: str | None = None
    status: str


class SubmitGoalResponse(BaseModel):
    conversation_id: str
    orchestrator_instance_id: str
    orchestrator_session_id: str
    parent_task_id: str
    plan_version_id: str
    agents: list[AgentLaunchResponse]


class PlanRevisionRequest(BaseModel):
    """A complete replacement DAG, guarded by the editor's base snapshot."""

    model_config = ConfigDict(extra="forbid")

    base_plan_version_id: str = Field(min_length=1, max_length=64)
    subtasks: list[SubtaskRequest] = Field(min_length=1)


class PlanRevisionResponse(BaseModel):
    conversation_id: str
    parent_task_id: str
    base_plan_version_id: str
    plan_version_id: str
    version: int


class ExecuteTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    max_output_tokens: int | None = Field(default=None, gt=0, le=128000)


class AgentTurnResponse(BaseModel):
    turn_id: str
    agent_instance_id: str
    agent_session_id: str
    agent_run_id: str
    canonical_model_id: str
    route_lock_id: str
    routing_snapshot: dict[str, Any]
    text: str | None = None
    finish_reason: str


class CompleteAgentNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    succeeded: bool = True
    fencing_token: str = Field(min_length=1, max_length=192)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=2048)


class CompleteAgentNodeResponse(BaseModel):
    applied: bool
    state: str | None = None
    next_retry_at: str | None = None
    dispatched_agent_run_ids: list[str] = Field(default_factory=list)


@router.post(
    "/{conversation_id}/goals",
    response_model=SubmitGoalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_goal(
    conversation_id: str,
    body: SubmitGoalRequest,
    request: Request,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> SubmitGoalResponse:
    """Start a goal through the sole conversation-to-runtime production path.

    The payload intentionally has no ``agent_type`` field.  Runtime roles are
    derived inside :class:`OrchestratorService`, preventing a frontend from
    creating arbitrary privileged sessions.
    """
    try:
        result = await orchestrator.submit_goal(
            conversation_id=conversation_id,
            objective=body.objective,
            title=body.title,
            subtasks=tuple(
                Subtask(
                    objective=item.objective,
                    node_id=item.node_id,
                    depends_on=tuple(item.depends_on),
                    concurrency_group=item.concurrency_group,
                )
                for item in body.subtasks
            ),
            # The authenticated gateway may set this server-side request state.
            # A client header is deliberately not used as an internal-user proof.
            release_actor_id=getattr(request.state, "release_actor_id", None),
        )
    except ReleaseNotActive as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SubmitGoalResponse(
        conversation_id=result.conversation_id,
        orchestrator_instance_id=result.orchestrator_instance_id,
        orchestrator_session_id=result.orchestrator_session_id,
        parent_task_id=result.parent_task_id,
        plan_version_id=result.plan_version_id,
        agents=[AgentLaunchResponse(**agent.__dict__) for agent in result.agents],
    )


@router.post(
    "/{conversation_id}/parent-tasks/{parent_task_id}/plan-revisions",
    response_model=PlanRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def revise_plan(
    conversation_id: str,
    parent_task_id: str,
    body: PlanRevisionRequest,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> PlanRevisionResponse:
    """Append an immutable plan snapshot without retargeting live agents."""
    try:
        result = await orchestrator.revise_plan(
            conversation_id=conversation_id,
            parent_task_id=parent_task_id,
            base_plan_version_id=body.base_plan_version_id,
            subtasks=tuple(
                Subtask(
                    objective=item.objective,
                    node_id=item.node_id,
                    depends_on=tuple(item.depends_on),
                    concurrency_group=item.concurrency_group,
                )
                for item in body.subtasks
            ),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlanRevisionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlanRevisionResponse(**result.__dict__)


@router.get("/{conversation_id}/parent-tasks/{parent_task_id}/plan-versions")
async def list_plan_versions(
    conversation_id: str,
    parent_task_id: str,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> list[dict[str, object]]:
    """Retrieve both the active plan and every older immutable snapshot."""
    return await orchestrator.list_plan_versions(
        conversation_id=conversation_id,
        parent_task_id=parent_task_id,
    )


@router.post("/{conversation_id}/agents/{agent_instance_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_agent(
    conversation_id: str,
    agent_instance_id: str,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> dict[str, str]:
    # ``conversation_id`` is part of the canonical route contract.  Ownership
    # is verified by the service's durable run lookup; an unknown/terminal agent
    # is intentionally reported as 404 rather than applying a broad session stop.
    stopped = await orchestrator.stop_agent(agent_instance_id, conversation_id=conversation_id)
    if not stopped:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="active agent not found")
    return {"conversation_id": conversation_id, "agent_instance_id": agent_instance_id, "status": "cancelled"}


@router.post(
    "/{conversation_id}/agents/{agent_instance_id}/turns",
    response_model=AgentTurnResponse,
)
async def execute_agent_turn(
    conversation_id: str,
    agent_instance_id: str,
    body: ExecuteTurnRequest,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> AgentTurnResponse:
    """Execute one provider turn through the agent session's durable route lock."""
    try:
        result = await orchestrator.execute_provider_turn(
            conversation_id=conversation_id,
            agent_instance_id=agent_instance_id,
            prompt=body.prompt,
            messages=body.messages,
            max_output_tokens=body.max_output_tokens,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SameModelEndpointExhausted as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="all exact-equivalent endpoints for the locked model are unavailable",
        ) from exc
    except ProviderFailure as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="provider turn failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AgentTurnResponse(
        turn_id=result.turn_id,
        agent_instance_id=result.agent_instance_id,
        agent_session_id=result.agent_session_id,
        agent_run_id=result.agent_run_id,
        canonical_model_id=result.canonical_model_id,
        route_lock_id=result.route_lock_id,
        routing_snapshot=dict(result.routing_snapshot),
        text=result.text,
        finish_reason=result.finish_reason,
    )


@router.post(
    "/{conversation_id}/agents/{agent_instance_id}/node-completion",
    response_model=CompleteAgentNodeResponse,
)
async def complete_agent_node(
    conversation_id: str,
    agent_instance_id: str,
    body: CompleteAgentNodeRequest,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> CompleteAgentNodeResponse:
    """Runtime completion ingress guarded by the node's durable CAS version."""
    result = await orchestrator.complete_agent_node(
        conversation_id=conversation_id,
        agent_instance_id=agent_instance_id,
        succeeded=body.succeeded,
        result=body.result,
        error=body.error,
        fencing_token=body.fencing_token,
    )
    return CompleteAgentNodeResponse(
        applied=result.applied,
        state=result.state,
        next_retry_at=result.next_retry_at,
        dispatched_agent_run_ids=list(result.dispatched_agent_run_ids),
    )


@router.get("/{conversation_id}/agents")
async def list_agents(
    conversation_id: str,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> list[dict[str, object]]:
    return await orchestrator.list_agents(conversation_id)


@router.get("/{conversation_id}/task-graphs")
async def list_task_graphs(
    conversation_id: str,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> list[dict[str, object]]:
    """Return only durable plan/node state; this workspace has no mock DAG."""
    return await orchestrator.list_task_graphs(conversation_id)


@router.get("/{conversation_id}/routing/turns")
async def list_routing_turns(
    conversation_id: str,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> list[dict[str, Any]]:
    """Read-only audit feed of route locks and per-turn routing snapshots."""
    return await orchestrator.list_routing_turns(conversation_id)


@router.get("/{conversation_id}/routing/turns/{turn_id}")
async def routing_turn_detail(
    conversation_id: str,
    turn_id: str,
    orchestrator: Annotated[OrchestratorService, Depends(get_orchestrator_service)],
) -> dict[str, Any]:
    """Read-only lock snapshot and RouteAttempts for a single provider turn."""
    detail = await orchestrator.routing_turn_detail(conversation_id, turn_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="routing turn not found")
    return detail
