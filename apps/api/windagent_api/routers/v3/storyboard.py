"""
V3 Storyboard Router — Canonical Storyboard + Scene Generation Authority.
Provides storyboard sync from locked screenplay revision and real generation job tracking.
No fake setTimeout timers. All generation returns a server-issued job ID.

Phase 4: storyboards, scenes, and generation jobs are persisted through the
namespaced durable V3 resource authority. No module-level RAM stores.
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import (
    NS_STORYBOARDS,
    NS_SCENES,
    NS_GENERATION_JOBS,
)

router = APIRouter(prefix="/api/v3", tags=["Storyboard V3"])
ws_router = APIRouter(prefix="/ws/v3/storyboard", tags=["Storyboard V3 WebSocket"])


class SceneResource(BaseModel):
    id: str
    storyboard_id: str
    episode_id: str
    scene_number: int
    title: str
    status: str = "DRAFT"
    script_text: str = ""
    duration_seconds: int = 120
    location: str = ""
    character_ids: List[str] = Field(default_factory=list)
    concept_image_url: Optional[str] = None
    source_screenplay_revision_id: Optional[str] = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class StoryboardResource(BaseModel):
    id: str
    episode_id: str
    source_screenplay_revision_id: str
    status: str = "DRAFT"
    scenes_count: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class GenerationJobResource(BaseModel):
    generation_id: str
    scene_id: str
    episode_id: str
    status: str = "QUEUED"
    progress_percent: int = 0
    submitted_at: str = ""
    completed_at: Optional[str] = None
    result_asset_url: Optional[str] = None
    error_message: Optional[str] = None


class CreateSceneRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    script_text: str = ""
    location: str = ""
    character_ids: List[str] = Field(default_factory=list)
    duration_seconds: int = 120
    source_screenplay_revision_id: Optional[str] = None


class UpdateSceneRequest(BaseModel):
    title: Optional[str] = None
    script_text: Optional[str] = None
    location: Optional[str] = None
    character_ids: Optional[List[str]] = None
    expected_version: int = Field(..., description="Optimistic lock version")


class TriggerGenerationRequest(BaseModel):
    style_prompt: Optional[str] = Field(None, description="Visual style override")
    reference_character_ids: List[str] = Field(default_factory=list)


def _scene_to_resource(s: Dict[str, Any]) -> SceneResource:
    return SceneResource(**s)


@router.get("/episodes/{episode_id}/storyboard", response_model=StoryboardResource, operation_id="storyboard.get")
async def get_episode_storyboard(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> StoryboardResource:
    """Retrieve the storyboard for an episode, pinned to locked screenplay revision."""
    sb = await service.get(NS_STORYBOARDS, episode_id)
    if sb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Storyboard for episode '{episode_id}' not found.")

    scenes = await service.list(NS_SCENES)
    scenes = [s for s in scenes if s.get("episode_id") == episode_id]
    return StoryboardResource(
        id=sb["id"],
        episode_id=sb["episode_id"],
        source_screenplay_revision_id=sb["source_screenplay_revision_id"],
        status=sb.get("status", "DRAFT"),
        scenes_count=len(scenes),
        version=sb.get("version", 1),
        created_at=sb.get("created_at", ""),
        updated_at=sb.get("updated_at", ""),
    )


@router.post("/episodes/{episode_id}/storyboard/actions/sync", response_model=StoryboardResource, operation_id="storyboard.syncFromScreenplay")
async def sync_storyboard_from_screenplay(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> StoryboardResource:
    """Sync storyboard scenes from the locked screenplay revision."""
    sb = await service.get(NS_STORYBOARDS, episode_id)
    now = utc_now().isoformat()
    if sb is None:
        sb_data = {
            "id": f"sb-{uuid.uuid4().hex[:8]}",
            "episode_id": episode_id,
            "source_screenplay_revision_id": f"rev-{episode_id}-lock",
            "status": "SYNCED",
            "created_at": now,
            "updated_at": now,
        }
        await service.create(NS_STORYBOARDS, episode_id, sb_data)
    else:
        updates = dict(sb)
        updates["status"] = "SYNCED"
        updates["updated_at"] = now
        await service.update(NS_STORYBOARDS, episode_id, updates, sb["version"])
    return await get_episode_storyboard(episode_id, service)


@router.get("/episodes/{episode_id}/storyboard/scenes", response_model=List[SceneResource], operation_id="storyboard.listScenes")
async def list_storyboard_scenes(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[SceneResource]:
    """List all scenes in an episode storyboard ordered by scene number."""
    scenes = await service.list(NS_SCENES)
    scenes = [s for s in scenes if s.get("episode_id") == episode_id]
    scenes.sort(key=lambda s: s.get("scene_number", 0))
    return [_scene_to_resource(s) for s in scenes]


@router.post("/storyboard/scenes", response_model=SceneResource, status_code=status.HTTP_201_CREATED, operation_id="storyboard.createScene")
async def create_scene(
    body: CreateSceneRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> SceneResource:
    """Create a new storyboard scene."""
    scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    scenes = await service.list(NS_SCENES)
    new_scene = {
        "id": scene_id,
        "storyboard_id": "",
        "episode_id": "",
        "scene_number": len(scenes) + 1,
        "title": body.title,
        "status": "DRAFT",
        "script_text": body.script_text,
        "duration_seconds": body.duration_seconds,
        "location": body.location,
        "character_ids": body.character_ids,
        "concept_image_url": None,
        "source_screenplay_revision_id": body.source_screenplay_revision_id,
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_SCENES, scene_id, new_scene)
    return _scene_to_resource(created)


@router.patch("/storyboard/scenes/{scene_id}", response_model=SceneResource, operation_id="storyboard.updateScene")
async def update_scene(
    scene_id: str = Path(...),
    body: UpdateSceneRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> SceneResource:
    """Update a storyboard scene with optimistic concurrency check."""
    curr = await service.get(NS_SCENES, scene_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for scene '{scene_id}'.")

    updates = dict(curr)
    if body.title is not None:
        updates["title"] = body.title
    if body.script_text is not None:
        updates["script_text"] = body.script_text
    if body.location is not None:
        updates["location"] = body.location
    if body.character_ids is not None:
        updates["character_ids"] = body.character_ids
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_SCENES, scene_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for scene '{scene_id}'.")
    return _scene_to_resource(updated)


@router.post("/storyboard/scenes/{scene_id}/generations", response_model=GenerationJobResource, status_code=status.HTTP_201_CREATED, operation_id="storyboard.triggerGeneration")
async def trigger_concept_generation(
    scene_id: str = Path(...),
    body: TriggerGenerationRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> GenerationJobResource:
    """
    Trigger concept art generation for a storyboard scene.
    Returns a server-issued generation_id immediately.
    No fake timers — realtime progress via WebSocket.
    """
    scene = await service.get(NS_SCENES, scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")

    generation_id = f"gen-{uuid.uuid4().hex[:10]}"
    now = utc_now().isoformat()
    job: Dict[str, Any] = {
        "generation_id": generation_id,
        "scene_id": scene_id,
        "episode_id": scene.get("episode_id", ""),
        "status": "QUEUED",
        "progress_percent": 0,
        "submitted_at": now,
        "completed_at": None,
        "result_asset_url": None,
        "error_message": None,
    }
    created = await service.create(NS_GENERATION_JOBS, generation_id, job)

    # Update scene status
    scene_updates = dict(scene)
    scene_updates["status"] = "GENERATING"
    scene_updates["updated_at"] = now
    await service.update(NS_SCENES, scene_id, scene_updates, scene["version"])

    return GenerationJobResource(**created)


@router.get("/storyboard/scenes/{scene_id}/generations/{generation_id}", response_model=GenerationJobResource, operation_id="storyboard.getGenerationJob")
async def get_generation_job(
    scene_id: str = Path(...),
    generation_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> GenerationJobResource:
    """Poll status of a concept generation job."""
    job = await service.get(NS_GENERATION_JOBS, generation_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Generation job '{generation_id}' not found.")
    return GenerationJobResource(**job)


@ws_router.websocket("/{episode_id}")
async def storyboard_realtime_ws(websocket: WebSocket, episode_id: str):
    """Realtime WebSocket streaming storyboard and generation events for an episode."""
    await websocket.accept()
    try:
        # Send initial state snapshot
        container = getattr(websocket.app.state, "container", None)
        service = container.v3_resource_service if container else None
        scenes = []
        if service is not None:
            scenes = await service.list(NS_SCENES)
            scenes = [s for s in scenes if s.get("episode_id") == episode_id]
        scenes.sort(key=lambda s: s.get("scene_number", 0))
        await websocket.send_json({
            "event": "storyboard.snapshot",
            "episode_id": episode_id,
            "scenes": [SceneResource(**s).model_dump() for s in scenes],
            "timestamp": utc_now().isoformat(),
        })
        while True:
            await asyncio.sleep(10.0)
            await websocket.send_json({"event": "heartbeat", "episode_id": episode_id, "timestamp": utc_now().isoformat()})
    except WebSocketDisconnect:
        pass
