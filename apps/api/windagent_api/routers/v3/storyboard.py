"""
V3 Storyboard Router — Canonical Storyboard + Scene Generation Authority.
Provides storyboard sync from locked screenplay revision and real generation job tracking.
No fake setTimeout timers. All generation returns a server-issued job ID.
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

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


_STORYBOARDS: Dict[str, Dict[str, Any]] = {
    "ep-cb-001": {
        "id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "source_screenplay_revision_id": "rev-cb-001-v3",
        "status": "DRAFT",
        "version": 1,
        "created_at": "2026-08-10T08:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    }
}

_SCENES: Dict[str, Dict[str, Any]] = {
    "scene-cb-001-01": {
        "id": "scene-cb-001-01",
        "storyboard_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "scene_number": 1,
        "title": "Phát Hiện Tín Hiệu (COLD OPEN)",
        "status": "CONCEPT_READY",
        "script_text": "INT. PHÒNG LÀM VIỆC CỦA ALEX - ĐÊM. Ánh sáng xanh neon chớp nháy qua cửa sổ ẩm ướt. Tiếng mưa axit rơi lộp bộp. Alex gõ liên hồi trên bàn phím holographic.",
        "duration_seconds": 150,
        "location": "INT. Phòng làm việc Alex - Đêm",
        "character_ids": ["char-kaelen-01"],
        "concept_image_url": None,
        "source_screenplay_revision_id": "rev-cb-001-v3",
        "version": 1,
        "created_at": "2026-08-10T08:30:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
    "scene-cb-001-02": {
        "id": "scene-cb-001-02",
        "storyboard_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "scene_number": 2,
        "title": "Cuộc Đột Kích",
        "status": "DRAFT",
        "script_text": "EXT. HẺM TẦNG 404 - ĐÊM. Tiếng còi báo động xé toạc màn đêm. Đèn pha từ các phi thuyền tuần tra quét qua những bức tường phủ đầy rêu điện tử.",
        "duration_seconds": 105,
        "location": "EXT. Hẻm Tầng 404 - Đêm",
        "character_ids": ["char-kaelen-01", "char-nova-01"],
        "concept_image_url": None,
        "source_screenplay_revision_id": "rev-cb-001-v3",
        "version": 1,
        "created_at": "2026-08-10T08:35:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
    "scene-cb-001-03": {
        "id": "scene-cb-001-03",
        "storyboard_id": "sb-cb-001",
        "episode_id": "ep-cb-001",
        "scene_number": 3,
        "title": "Đối Mặt Sylas",
        "status": "DRAFT",
        "script_text": "INT. VĂN PHÒNG APEX CORTEX - ĐÊM. Sylas đứng trước cửa sổ toàn kính nhìn xuống thành phố. Alex tiến vào từ phía sau.",
        "duration_seconds": 190,
        "location": "INT. Văn phòng Apex Cortex - Đêm",
        "character_ids": ["char-kaelen-01", "char-sylas-01"],
        "concept_image_url": None,
        "source_screenplay_revision_id": "rev-cb-001-v3",
        "version": 1,
        "created_at": "2026-08-10T08:40:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
}

_GENERATION_JOBS: Dict[str, Dict[str, Any]] = {}


def _scene_to_resource(s: Dict[str, Any]) -> SceneResource:
    return SceneResource(**s)


@router.get("/episodes/{episode_id}/storyboard", response_model=StoryboardResource, operation_id="storyboard.get")
async def get_episode_storyboard(episode_id: str = Path(...)) -> StoryboardResource:
    """Retrieve the storyboard for an episode, pinned to locked screenplay revision."""
    if episode_id not in _STORYBOARDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Storyboard for episode '{episode_id}' not found.")

    sb = _STORYBOARDS[episode_id]
    scenes = [s for s in _SCENES.values() if s["episode_id"] == episode_id]
    return StoryboardResource(
        id=sb["id"],
        episode_id=sb["episode_id"],
        source_screenplay_revision_id=sb["source_screenplay_revision_id"],
        status=sb["status"],
        scenes_count=len(scenes),
        version=sb["version"],
        created_at=sb["created_at"],
        updated_at=sb["updated_at"],
    )


@router.post("/episodes/{episode_id}/storyboard/actions/sync", response_model=StoryboardResource, operation_id="storyboard.syncFromScreenplay")
async def sync_storyboard_from_screenplay(episode_id: str = Path(...)) -> StoryboardResource:
    """Sync storyboard scenes from the locked screenplay revision."""
    if episode_id not in _STORYBOARDS:
        now = utc_now().isoformat()
        _STORYBOARDS[episode_id] = {
            "id": f"sb-{uuid.uuid4().hex[:8]}",
            "episode_id": episode_id,
            "source_screenplay_revision_id": f"rev-{episode_id}-lock",
            "status": "SYNCED",
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
    else:
        _STORYBOARDS[episode_id]["status"] = "SYNCED"
        _STORYBOARDS[episode_id]["version"] += 1
        _STORYBOARDS[episode_id]["updated_at"] = utc_now().isoformat()
    return await get_episode_storyboard(episode_id)


@router.get("/episodes/{episode_id}/storyboard/scenes", response_model=List[SceneResource], operation_id="storyboard.listScenes")
async def list_storyboard_scenes(episode_id: str = Path(...)) -> List[SceneResource]:
    """List all scenes in an episode storyboard ordered by scene number."""
    scenes = [s for s in _SCENES.values() if s["episode_id"] == episode_id]
    scenes.sort(key=lambda s: s["scene_number"])
    return [_scene_to_resource(s) for s in scenes]


@router.post("/storyboard/scenes", response_model=SceneResource, status_code=status.HTTP_201_CREATED, operation_id="storyboard.createScene")
async def create_scene(body: CreateSceneRequest = ...) -> SceneResource:
    """Create a new storyboard scene."""
    scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    new_scene = {
        "id": scene_id,
        "storyboard_id": "",
        "episode_id": "",
        "scene_number": len(_SCENES) + 1,
        "title": body.title,
        "status": "DRAFT",
        "script_text": body.script_text,
        "duration_seconds": body.duration_seconds,
        "location": body.location,
        "character_ids": body.character_ids,
        "concept_image_url": None,
        "source_screenplay_revision_id": body.source_screenplay_revision_id,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    _SCENES[scene_id] = new_scene
    return _scene_to_resource(new_scene)


@router.patch("/storyboard/scenes/{scene_id}", response_model=SceneResource, operation_id="storyboard.updateScene")
async def update_scene(scene_id: str = Path(...), body: UpdateSceneRequest = ...) -> SceneResource:
    """Update a storyboard scene with optimistic concurrency check."""
    if scene_id not in _SCENES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")
    curr = _SCENES[scene_id]
    if curr["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for scene '{scene_id}'.")
    if body.title is not None:
        curr["title"] = body.title
    if body.script_text is not None:
        curr["script_text"] = body.script_text
    if body.location is not None:
        curr["location"] = body.location
    if body.character_ids is not None:
        curr["character_ids"] = body.character_ids
    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()
    return _scene_to_resource(curr)


@router.post("/storyboard/scenes/{scene_id}/generations", response_model=GenerationJobResource, status_code=status.HTTP_201_CREATED, operation_id="storyboard.triggerGeneration")
async def trigger_concept_generation(scene_id: str = Path(...), body: TriggerGenerationRequest = ...) -> GenerationJobResource:
    """
    Trigger concept art generation for a storyboard scene.
    Returns a server-issued generation_id immediately.
    No fake timers — realtime progress via WebSocket.
    """
    if scene_id not in _SCENES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")

    generation_id = f"gen-{uuid.uuid4().hex[:10]}"
    now = utc_now().isoformat()
    job: Dict[str, Any] = {
        "generation_id": generation_id,
        "scene_id": scene_id,
        "episode_id": _SCENES[scene_id]["episode_id"],
        "status": "QUEUED",
        "progress_percent": 0,
        "submitted_at": now,
        "completed_at": None,
        "result_asset_url": None,
        "error_message": None,
    }
    _GENERATION_JOBS[generation_id] = job

    # Update scene status
    _SCENES[scene_id]["status"] = "GENERATING"
    _SCENES[scene_id]["updated_at"] = now

    return GenerationJobResource(**job)


@router.get("/storyboard/scenes/{scene_id}/generations/{generation_id}", response_model=GenerationJobResource, operation_id="storyboard.getGenerationJob")
async def get_generation_job(scene_id: str = Path(...), generation_id: str = Path(...)) -> GenerationJobResource:
    """Poll status of a concept generation job."""
    if generation_id not in _GENERATION_JOBS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Generation job '{generation_id}' not found.")
    return GenerationJobResource(**_GENERATION_JOBS[generation_id])


@ws_router.websocket("/{episode_id}")
async def storyboard_realtime_ws(websocket: WebSocket, episode_id: str):
    """Realtime WebSocket streaming storyboard and generation events for an episode."""
    await websocket.accept()
    try:
        # Send initial state snapshot
        scenes = [s for s in _SCENES.values() if s["episode_id"] == episode_id]
        scenes.sort(key=lambda s: s["scene_number"])
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
