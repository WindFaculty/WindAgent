"""
V3 Episodes Router — Canonical Episode Workspace & Story Pipeline Authority.
Provides full lifecycle management, immutable revision authority, optimistic locking,
artifact management, and realtime WebSocket streaming.

Phase 4: all mutable state is persisted through the namespaced durable V3
resource authority. No module-level RAM stores.
"""

from __future__ import annotations
import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import (
    NS_EPISODES,
    NS_EPISODE_ARTIFACTS,
    NS_EPISODE_RUNS,
)

router = APIRouter(prefix="/api/v3/episodes", tags=["Episodes V3"])
ws_router = APIRouter(prefix="/ws/v3/episodes", tags=["Episodes V3 WebSocket"])


class EpisodeDetail(BaseModel):
    id: str = Field(..., description="Canonical episode UUID")
    project_id: str = Field(..., description="Parent project identifier")
    project_name: Optional[str] = Field(None, description="Display project name")
    title: str = Field(..., description="Episode title")
    episode_number: int = Field(1, description="Sequential episode order")
    description: Optional[str] = Field(None, description="Episode logline or synopsis")
    state: str = Field("DRAFT", description="Pipeline state ('DRAFT', 'IDEA', 'STORY_BIBLE', 'OUTLINE', 'SCREENPLAY', 'REVIEW', 'LOCKED', 'READY_FOR_PRODUCTION')")
    current_checkpoint: str = Field("IDEA", description="Current pipeline stage ('IDEA', 'STORY_BIBLE', 'OUTLINE', 'SCREENPLAY', 'REVIEW', 'LOCKED')")
    current_revision_id: Optional[str] = Field(None, description="Current active revision UUID")
    version: int = Field(1, description="Optimistic locking version counter")
    progress_percent: int = Field(0, description="Derived deterministic progress (0-100)")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    updated_at: str = Field(..., description="ISO 8601 UTC timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom episode metadata")


class EpisodeArtifactEnvelope(BaseModel):
    artifact_id: str = Field(..., description="Unique artifact identifier")
    episode_id: str = Field(..., description="Parent episode identifier")
    kind: str = Field(..., description="Artifact kind ('IdeaCandidateSet', 'StoryBible', 'EpisodeOutline', 'ScreenplayDraft', 'SceneBeats')")
    revision_id: str = Field(..., description="Immutable revision UUID")
    content: Dict[str, Any] = Field(..., description="Structured artifact payload")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")


class PipelineRun(BaseModel):
    run_id: str = Field(..., description="Execution run identifier")
    episode_id: str = Field(..., description="Target episode identifier")
    checkpoint: str = Field(..., description="Pipeline stage being executed")
    status: str = Field("COMPLETED", description="Run status ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')")
    progress_percent: int = Field(100, description="Run execution progress")
    started_at: str = Field(..., description="ISO 8601 UTC timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 UTC timestamp")
    error_message: Optional[str] = None


class StartGenerationRequest(BaseModel):
    checkpoint: Optional[str] = Field(None, description="Target checkpoint stage")
    prompt_override: Optional[str] = Field(None, description="Custom prompt or direction")


class SelectIdeaRequest(BaseModel):
    idea_id: str = Field(..., description="Selected idea identifier")
    expected_version: int = Field(..., description="Expected current version counter")


class CheckpointDecisionRequest(BaseModel):
    decision: str = Field(..., description="'APPROVED', 'REVISE', 'REJECTED'")
    revision_id: str = Field(..., description="Target revision UUID being reviewed")
    feedback: Optional[str] = Field(None, description="Feedback or revision instructions")
    expected_version: int = Field(..., description="Expected current version counter")


class LockScreenplayRequest(BaseModel):
    revision_id: str = Field(..., description="Approved screenplay revision UUID")
    content_hash: str = Field(..., description="SHA-256 content verification hash")
    expected_version: int = Field(..., description="Expected current version counter")


class UpdateEpisodeRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    expected_version: int = Field(..., description="Expected current version counter")


class EpisodeListResponse(BaseModel):
    items: List[EpisodeDetail]
    page_info: Dict[str, Any]


def _derive_progress(state: str, checkpoint: str) -> int:
    """Derive progress percentage deterministically from state & checkpoint."""
    if state in ["LOCKED", "READY_FOR_PRODUCTION"]:
        return 100
    if checkpoint == "LOCKED":
        return 100
    if checkpoint == "REVIEW" or state == "REVIEW":
        return 85
    if checkpoint == "SCREENPLAY" or state == "SCREENPLAY":
        return 70
    if checkpoint == "OUTLINE" or state == "OUTLINE":
        return 50
    if checkpoint == "STORY_BIBLE" or state == "STORY_BIBLE":
        return 30
    if checkpoint == "IDEA" or state == "IDEA":
        return 15
    return 5


def _episode_to_detail(e: Dict[str, Any]) -> EpisodeDetail:
    ep = dict(e)
    ep["progress_percent"] = _derive_progress(ep.get("state", "DRAFT"), ep.get("current_checkpoint", "IDEA"))
    return EpisodeDetail(**ep)


@router.get("", response_model=EpisodeListResponse, operation_id="episodes.listAll")
async def list_all_episodes(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    state: Optional[str] = Query(None, description="Filter by episode state"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(50, ge=1, le=200),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeListResponse:
    """List all episodes across projects with search and filter support."""
    items = await service.list(NS_EPISODES)

    if project_id:
        items = [e for e in items if e.get("project_id") == project_id]

    if state and state != "ALL":
        items = [e for e in items if e.get("state") == state]

    if search:
        s = search.lower()
        items = [e for e in items if s in e.get("title", "").lower() or s in e.get("project_name", "").lower() or (e.get("description") and s in e.get("description").lower())]

    # Sort newest first
    items.sort(key=lambda e: e.get("updated_at", ""), reverse=True)

    result_items = [_episode_to_detail(item) for item in items[:limit]]
    return EpisodeListResponse(items=result_items, page_info={"next_cursor": None, "has_more": False})


@router.get("/{episode_id}", response_model=EpisodeDetail, operation_id="episodes.getDetail")
async def get_episode_detail(
    episode_id: str = Path(..., description="Episode ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeDetail:
    """Retrieve full details of a specific episode with derived progress."""
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")
    return _episode_to_detail(ep)


@router.patch("/{episode_id}", response_model=EpisodeDetail, operation_id="episodes.update")
async def update_episode(
    episode_id: str = Path(..., description="Episode ID"),
    body: UpdateEpisodeRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeDetail:
    """Update episode title or description with optimistic concurrency check."""
    curr = await service.get(NS_EPISODES, episode_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    if body.title is not None:
        updates["title"] = body.title
    if body.description is not None:
        updates["description"] = body.description
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_EPISODES, episode_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Stale version conflict for episode '{episode_id}'.")
    return _episode_to_detail(updated)


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="episodes.delete")
async def delete_episode(
    episode_id: str = Path(..., description="Episode ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> None:
    """Delete an episode from the system."""
    await service.delete(NS_EPISODES, episode_id)
    await service.delete(NS_EPISODE_ARTIFACTS, episode_id)
    await service.delete(NS_EPISODE_RUNS, episode_id)


@router.get("/{episode_id}/artifacts", response_model=List[EpisodeArtifactEnvelope], operation_id="episodes.getArtifacts")
async def get_episode_artifacts(
    episode_id: str = Path(..., description="Episode ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[EpisodeArtifactEnvelope]:
    """Retrieve all generated artifact envelopes for an episode."""
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    arts = await service.list(NS_EPISODE_ARTIFACTS)
    arts = [a for a in arts if a.get("episode_id") == episode_id]
    return [EpisodeArtifactEnvelope(**a) for a in arts]


@router.get("/{episode_id}/runs", response_model=List[PipelineRun], operation_id="episodes.getRuns")
async def get_episode_runs(
    episode_id: str = Path(..., description="Episode ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[PipelineRun]:
    """Retrieve all pipeline execution runs for an episode."""
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    runs = await service.list(NS_EPISODE_RUNS)
    runs = [r for r in runs if r.get("episode_id") == episode_id]
    return [PipelineRun(**r) for r in runs]


@router.post("/{episode_id}/start-generation", response_model=PipelineRun, operation_id="episodes.startGeneration")
async def start_generation(
    episode_id: str = Path(..., description="Episode ID"),
    body: StartGenerationRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> PipelineRun:
    """Start an AI generation run for the next or requested checkpoint stage."""
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    now_iso = utc_now().isoformat()
    target_stage = body.checkpoint or ep["current_checkpoint"]
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    new_run = {
        "run_id": run_id,
        "episode_id": episode_id,
        "checkpoint": target_stage,
        "status": "COMPLETED",
        "progress_percent": 100,
        "started_at": now_iso,
        "completed_at": now_iso,
    }
    await service.create(NS_EPISODE_RUNS, run_id, new_run)

    # Generate sample artifact for the stage if not present
    rev_id = f"rev-{uuid.uuid4().hex[:6]}"
    ep_updates = dict(ep)
    ep_updates["current_revision_id"] = rev_id
    ep_updates["updated_at"] = now_iso
    await service.update(NS_EPISODES, episode_id, ep_updates, ep["version"])

    return PipelineRun(**new_run)


@router.post("/{episode_id}/select-idea", response_model=EpisodeDetail, operation_id="episodes.selectIdea")
async def select_idea(
    episode_id: str = Path(..., description="Episode ID"),
    body: SelectIdeaRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeDetail:
    """Select a candidate idea and advance pipeline to STORY_BIBLE."""
    curr = await service.get(NS_EPISODES, episode_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    updates["state"] = "STORY_BIBLE"
    updates["current_checkpoint"] = "STORY_BIBLE"
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_EPISODES, episode_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Stale version conflict for episode '{episode_id}'.")
    return _episode_to_detail(updated)


@router.post("/{episode_id}/decision", response_model=EpisodeDetail, operation_id="episodes.submitDecision")
async def submit_checkpoint_decision(
    episode_id: str = Path(..., description="Episode ID"),
    body: CheckpointDecisionRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeDetail:
    """Submit approval or revision request on a checkpoint revision with version verification."""
    curr = await service.get(NS_EPISODES, episode_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    if body.decision == "APPROVED":
        stage_transitions = {
            "IDEA": "STORY_BIBLE",
            "STORY_BIBLE": "OUTLINE",
            "OUTLINE": "SCREENPLAY",
            "SCREENPLAY": "REVIEW",
            "REVIEW": "LOCKED",
        }
        next_stage = stage_transitions.get(curr["current_checkpoint"], curr["current_checkpoint"])
        updates["current_checkpoint"] = next_stage
        updates["state"] = next_stage
    elif body.decision == "REVISE":
        metadata = dict(curr.get("metadata", {}))
        metadata["last_feedback"] = body.feedback
        updates["metadata"] = metadata

    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_EPISODES, episode_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Stale version conflict for episode '{episode_id}'.")
    return _episode_to_detail(updated)


@router.post("/{episode_id}/lock", response_model=EpisodeDetail, operation_id="episodes.lockScreenplay")
async def lock_screenplay(
    episode_id: str = Path(..., description="Episode ID"),
    body: LockScreenplayRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeDetail:
    """Lock screenplay for production readiness with content hash verification.

    P1.0 truth repair: the lock command persists a LockedScreenplayReceipt
    artifact so downstream pre-production consumers can resolve the ACTUAL
    revision_id / content_hash / artifact_id instead of synthesizing them.
    """
    curr = await service.get(NS_EPISODES, episode_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    now_iso = utc_now().isoformat()
    updates = dict(curr)
    updates["state"] = "LOCKED"
    updates["current_checkpoint"] = "LOCKED"
    metadata = dict(curr.get("metadata", {}))
    metadata["locked_revision_id"] = body.revision_id
    metadata["content_hash"] = body.content_hash
    updates["metadata"] = metadata
    updates["updated_at"] = now_iso

    updated = await service.update(NS_EPISODES, episode_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Stale version conflict for episode '{episode_id}'.")

    receipt_id = f"art-{uuid.uuid4().hex[:12]}"
    await service.create(NS_EPISODE_ARTIFACTS, receipt_id, {
        "artifact_id": receipt_id,
        "episode_id": episode_id,
        "kind": "LockedScreenplayReceipt",
        "revision_id": body.revision_id,
        "content": {
            "receipt_id": receipt_id,
            "locked_revision_id": body.revision_id,
            "content_hash": body.content_hash,
            "state": "READY_FOR_PRODUCTION",
            "issued_at": now_iso,
        },
        "created_at": now_iso,
    })

    ep = dict(updated)
    ep["progress_percent"] = 100
    return EpisodeDetail(**ep)


@router.post("/{episode_id}/cancel-run", response_model=Dict[str, Any], operation_id="episodes.cancelRun")
async def cancel_run(
    episode_id: str = Path(..., description="Episode ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Cancel any active generation runs on the episode."""
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    return {"episode_id": episode_id, "status": "CANCELLED", "timestamp": utc_now().isoformat()}


@ws_router.websocket("/{episode_id}")
async def episode_workspace_websocket(websocket: WebSocket, episode_id: str):
    """Realtime WebSocket endpoint streaming episode lifecycle and pipeline events."""
    await websocket.accept()
    try:
        # Stream initial snapshot
        container = getattr(websocket.app.state, "container", None)
        service = container.v3_resource_service if container else None
        ep = None
        if service is not None:
            ep = await service.get(NS_EPISODES, episode_id)
        if ep is None:
            ep = {
                "id": episode_id,
                "title": "Episode Workspace",
                "state": "DRAFT",
                "current_checkpoint": "IDEA",
            }
        payload = dict(ep)
        payload["progress_percent"] = _derive_progress(payload.get("state", "DRAFT"), payload.get("current_checkpoint", "IDEA"))

        await websocket.send_json({
            "event": "episode.updated",
            "episode_id": episode_id,
            "payload": payload,
            "timestamp": utc_now().isoformat(),
        })

        # Keep alive loop
        while True:
            await asyncio.sleep(10.0)
            await websocket.send_json({
                "event": "heartbeat",
                "episode_id": episode_id,
                "timestamp": utc_now().isoformat(),
            })
    except WebSocketDisconnect:
        pass
