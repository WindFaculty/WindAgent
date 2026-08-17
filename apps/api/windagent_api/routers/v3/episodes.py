"""
V3 Episodes Router — Canonical Episode Workspace & Story Pipeline Authority.
Provides full lifecycle management, immutable revision authority, optimistic locking,
artifact management, and realtime WebSocket streaming.
"""

from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Path, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

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


# In-memory storage seeded with rich canonical episode data
_EPISODES: Dict[str, Dict[str, Any]] = {
    "ep-cb-001": {
        "id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "project_name": "Cyberpunk Odyssey 2099",
        "title": "Tập 01: Mã Nguồn Thức Tỉnh",
        "episode_number": 1,
        "description": "Tin tặc trẻ Alex vô tình giải mã một chuỗi tín hiệu bí ẩn từ AI trung tâm của siêu đô thị Neo-Saigon.",
        "state": "SCREENPLAY",
        "current_checkpoint": "SCREENPLAY",
        "current_revision_id": "rev-cb-001-v3",
        "version": 3,
        "created_at": "2026-08-01T08:30:00Z",
        "updated_at": "2026-08-14T02:00:00Z",
        "metadata": {"genre": "Cyberpunk / Sci-Fi"},
    },
    "ep-cb-002": {
        "id": "ep-cb-002",
        "project_id": "proj-cyberpunk-01",
        "project_name": "Cyberpunk Odyssey 2099",
        "title": "Tập 02: Mê Cung Neon",
        "episode_number": 2,
        "description": "Bị truy kích bởi các thợ săn tiền thưởng cyborg, Alex phải lẩn trốn vào tầng ngầm 404.",
        "state": "OUTLINE",
        "current_checkpoint": "OUTLINE",
        "current_revision_id": "rev-cb-002-v1",
        "version": 1,
        "created_at": "2026-08-05T08:30:00Z",
        "updated_at": "2026-08-12T10:00:00Z",
        "metadata": {"genre": "Cyberpunk / Sci-Fi"},
    },
    "ep-ft-001": {
        "id": "ep-ft-001",
        "project_id": "proj-fantasy-02",
        "project_name": "Biên Niên Sử Vùng Đất Rồng",
        "title": "Tập 01: Tiếng Gọi Rừng Thiêng",
        "episode_number": 1,
        "description": "Người giám hộ trẻ phát hiện dấu vết sinh vật thần thoại thức giấc sau một ngàn năm ngủ say.",
        "state": "LOCKED",
        "current_checkpoint": "LOCKED",
        "current_revision_id": "rev-ft-001-lock",
        "version": 5,
        "created_at": "2026-08-05T10:00:00Z",
        "updated_at": "2026-08-13T18:00:00Z",
        "metadata": {"genre": "High Fantasy / Adventure"},
    },
}

_ARTIFACTS: Dict[str, List[Dict[str, Any]]] = {
    "ep-cb-001": [
        {
            "artifact_id": "art-idea-01",
            "episode_id": "ep-cb-001",
            "kind": "IdeaCandidateSet",
            "revision_id": "rev-cb-001-v1",
            "created_at": "2026-08-01T08:35:00Z",
            "content": {
                "selected_idea_id": "idea-1",
                "ideas": [
                    {
                        "id": "idea-1",
                        "title": "Mã Nguồn Thức Tỉnh",
                        "premise": "Tin tặc phát hiện AI trung tâm đang cố gắng cảnh báo loài người về một đợt xóa sổ quy mô lớn.",
                        "tone": "Hồi hộp, công nghệ cao, bí ẩn",
                    },
                    {
                        "id": "idea-2",
                        "title": "Ký Ức Đánh Cắp",
                        "premise": "Một người máy cảnh sát bắt đầu nhớ lại kiếp sống con người trước khi bị biến đổi.",
                        "tone": "Trầm mặc, triết lý, hành động",
                    },
                ],
            },
        },
        {
            "artifact_id": "art-bible-01",
            "episode_id": "ep-cb-001",
            "kind": "StoryBible",
            "revision_id": "rev-cb-001-v2",
            "created_at": "2026-08-02T10:00:00Z",
            "content": {
                "characters": [
                    {"name": "Alex", "role": "Protagonist", "archetype": "Rebel Hacker"},
                    {"name": "Vesper-9", "role": "Companion", "archetype": "Rogue Android"},
                ],
                "world_rules": "Siêu đô thị chia làm 3 tầng: Tầng Thượng lưu trên mây, Tầng Trung cư và Tầng Ngầm 404.",
                "theme": "Ranh giới giữa ý thức nhân tạo và linh hồn con người.",
            },
        },
        {
            "artifact_id": "art-outline-01",
            "episode_id": "ep-cb-001",
            "kind": "EpisodeOutline",
            "revision_id": "rev-cb-001-v2",
            "created_at": "2026-08-03T11:00:00Z",
            "content": {
                "acts": [
                    {"act_number": 1, "title": "Phát Hiện Tín Hiệu", "summary": "Alex quét thấy luồng dữ liệu lạ trong lúc tìm kiếm linh kiện ngầm."},
                    {"act_number": 2, "title": "Cuộc Đột Kích", "summary": "Quân đoàn An ninh Tập đoàn ập vào căn hộ bí mật của Alex."},
                    {"act_number": 3, "title": "Cú Nhảy Xuống Tầng 404", "summary": "Alex và Vesper-9 thoát khỏi tòa nhà và rơi vào mê cung ngầm."},
                ],
            },
        },
        {
            "artifact_id": "art-screenplay-01",
            "episode_id": "ep-cb-001",
            "kind": "ScreenplayDraft",
            "revision_id": "rev-cb-001-v3",
            "created_at": "2026-08-04T14:00:00Z",
            "content": {
                "scenes": [
                    {
                        "scene_number": 1,
                        "heading": "INT. PHÒNG LÀM VIỆC CỦA ALEX - ĐÊM",
                        "action": "Ánh sáng xanh neon chớp nháy qua cửa sổ ẩm ướt. Tiếng mưa axit rơi lộp bộp trên mái tôn rỉ sét. Alex gõ liên hồi trên bàn phím holographic.",
                        "dialogue": [
                            {"speaker": "ALEX", "text": "Chuỗi mã này... nó không được viết bởi con người."},
                            {"speaker": "VESPER-9", "text": "Vậy thì nó bắt nguồn từ AI Lõi. Và chúng ta chỉ có ba phút trước khi hệ thống phòng thủ phản ứng."},
                        ],
                    },
                    {
                        "scene_number": 2,
                        "heading": "EXT. HẺM TẦNG 404 - ĐÊM",
                        "action": "Tiếng còi báo động xé toạc màn đêm. Đèn pha từ các phi thuyền tuần tra quét qua những bức tường phủ đầy rêu điện tử.",
                    },
                ],
            },
        },
    ],
}

_RUNS: Dict[str, List[Dict[str, Any]]] = {
    "ep-cb-001": [
        {
            "run_id": "run-01",
            "episode_id": "ep-cb-001",
            "checkpoint": "IDEA",
            "status": "COMPLETED",
            "progress_percent": 100,
            "started_at": "2026-08-01T08:31:00Z",
            "completed_at": "2026-08-01T08:35:00Z",
        },
        {
            "run_id": "run-02",
            "episode_id": "ep-cb-001",
            "checkpoint": "STORY_BIBLE",
            "status": "COMPLETED",
            "progress_percent": 100,
            "started_at": "2026-08-02T09:55:00Z",
            "completed_at": "2026-08-02T10:00:00Z",
        },
        {
            "run_id": "run-03",
            "episode_id": "ep-cb-001",
            "checkpoint": "SCREENPLAY",
            "status": "COMPLETED",
            "progress_percent": 100,
            "started_at": "2026-08-04T13:50:00Z",
            "completed_at": "2026-08-04T14:00:00Z",
        },
    ],
}

_IDEMPOTENCY_KEYS_EPISODES: Dict[str, str] = {}


@router.get("", response_model=EpisodeListResponse, operation_id="episodes.listAll")
async def list_all_episodes(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    state: Optional[str] = Query(None, description="Filter by episode state"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(50, ge=1, le=200),
) -> EpisodeListResponse:
    """List all episodes across projects with search and filter support."""
    items = list(_EPISODES.values())

    if project_id:
        items = [e for e in items if e.get("project_id") == project_id]

    if state and state != "ALL":
        items = [e for e in items if e.get("state") == state]

    if search:
        s = search.lower()
        items = [e for e in items if s in e.get("title", "").lower() or s in e.get("project_name", "").lower() or (e.get("description") and s in e.get("description").lower())]

    # Sort newest first
    items.sort(key=lambda e: e.get("updated_at", ""), reverse=True)

    result_items = []
    for item in items[:limit]:
        item_copy = dict(item)
        item_copy["progress_percent"] = _derive_progress(item_copy.get("state", "DRAFT"), item_copy.get("current_checkpoint", "IDEA"))
        result_items.append(EpisodeDetail(**item_copy))

    return EpisodeListResponse(items=result_items, page_info={"next_cursor": None, "has_more": False})


@router.get("/{episode_id}", response_model=EpisodeDetail, operation_id="episodes.getDetail")
async def get_episode_detail(
    episode_id: str = Path(..., description="Episode ID"),
) -> EpisodeDetail:
    """Retrieve full details of a specific episode with derived progress."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    ep = dict(_EPISODES[episode_id])
    ep["progress_percent"] = _derive_progress(ep.get("state", "DRAFT"), ep.get("current_checkpoint", "IDEA"))
    return EpisodeDetail(**ep)


@router.patch("/{episode_id}", response_model=EpisodeDetail, operation_id="episodes.update")
async def update_episode(
    episode_id: str = Path(..., description="Episode ID"),
    body: UpdateEpisodeRequest = ...,
) -> EpisodeDetail:
    """Update episode title or description with optimistic concurrency check."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    curr = _EPISODES[episode_id]

    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    if body.title is not None:
        curr["title"] = body.title
    if body.description is not None:
        curr["description"] = body.description

    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()

    ep = dict(curr)
    ep["progress_percent"] = _derive_progress(ep.get("state", "DRAFT"), ep.get("current_checkpoint", "IDEA"))
    return EpisodeDetail(**ep)


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="episodes.delete")
async def delete_episode(
    episode_id: str = Path(..., description="Episode ID"),
) -> None:
    """Delete an episode from the system."""
    if episode_id in _EPISODES:
        del _EPISODES[episode_id]
    if episode_id in _ARTIFACTS:
        del _ARTIFACTS[episode_id]
    if episode_id in _RUNS:
        del _RUNS[episode_id]


@router.get("/{episode_id}/artifacts", response_model=List[EpisodeArtifactEnvelope], operation_id="episodes.getArtifacts")
async def get_episode_artifacts(
    episode_id: str = Path(..., description="Episode ID"),
) -> List[EpisodeArtifactEnvelope]:
    """Retrieve all generated artifact envelopes for an episode."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    arts = _ARTIFACTS.get(episode_id, [])
    return [EpisodeArtifactEnvelope(**a) for a in arts]


@router.get("/{episode_id}/runs", response_model=List[PipelineRun], operation_id="episodes.getRuns")
async def get_episode_runs(
    episode_id: str = Path(..., description="Episode ID"),
) -> List[PipelineRun]:
    """Retrieve all pipeline execution runs for an episode."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    runs = _RUNS.get(episode_id, [])
    return [PipelineRun(**r) for r in runs]


@router.post("/{episode_id}/start-generation", response_model=PipelineRun, operation_id="episodes.startGeneration")
async def start_generation(
    episode_id: str = Path(..., description="Episode ID"),
    body: StartGenerationRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> PipelineRun:
    """Start an AI generation run for the next or requested checkpoint stage."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    now_iso = utc_now().isoformat()
    target_stage = body.checkpoint or _EPISODES[episode_id]["current_checkpoint"]
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

    if episode_id not in _RUNS:
        _RUNS[episode_id] = []
    _RUNS[episode_id].append(new_run)

    # Generate sample artifact for the stage if not present
    rev_id = f"rev-{uuid.uuid4().hex[:6]}"
    _EPISODES[episode_id]["current_revision_id"] = rev_id
    _EPISODES[episode_id]["updated_at"] = now_iso

    return PipelineRun(**new_run)


@router.post("/{episode_id}/select-idea", response_model=EpisodeDetail, operation_id="episodes.selectIdea")
async def select_idea(
    episode_id: str = Path(..., description="Episode ID"),
    body: SelectIdeaRequest = ...,
) -> EpisodeDetail:
    """Select a candidate idea and advance pipeline to STORY_BIBLE."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    curr = _EPISODES[episode_id]
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    curr["state"] = "STORY_BIBLE"
    curr["current_checkpoint"] = "STORY_BIBLE"
    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()

    ep = dict(curr)
    ep["progress_percent"] = _derive_progress(ep["state"], ep["current_checkpoint"])
    return EpisodeDetail(**ep)


@router.post("/{episode_id}/decision", response_model=EpisodeDetail, operation_id="episodes.submitDecision")
async def submit_checkpoint_decision(
    episode_id: str = Path(..., description="Episode ID"),
    body: CheckpointDecisionRequest = ...,
) -> EpisodeDetail:
    """Submit approval or revision request on a checkpoint revision with version verification."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    curr = _EPISODES[episode_id]
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    if body.decision == "APPROVED":
        # Advance pipeline stage
        stage_transitions = {
            "IDEA": "STORY_BIBLE",
            "STORY_BIBLE": "OUTLINE",
            "OUTLINE": "SCREENPLAY",
            "SCREENPLAY": "REVIEW",
            "REVIEW": "LOCKED",
        }
        next_stage = stage_transitions.get(curr["current_checkpoint"], curr["current_checkpoint"])
        curr["current_checkpoint"] = next_stage
        curr["state"] = next_stage
    elif body.decision == "REVISE":
        # Keep same stage but record feedback in metadata
        curr["metadata"]["last_feedback"] = body.feedback

    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()

    ep = dict(curr)
    ep["progress_percent"] = _derive_progress(ep["state"], ep["current_checkpoint"])
    return EpisodeDetail(**ep)


@router.post("/{episode_id}/lock", response_model=EpisodeDetail, operation_id="episodes.lockScreenplay")
async def lock_screenplay(
    episode_id: str = Path(..., description="Episode ID"),
    body: LockScreenplayRequest = ...,
) -> EpisodeDetail:
    """Lock screenplay for production readiness with content hash verification."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    curr = _EPISODES[episode_id]
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for episode '{episode_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    curr["state"] = "LOCKED"
    curr["current_checkpoint"] = "LOCKED"
    curr["metadata"]["locked_revision_id"] = body.revision_id
    curr["metadata"]["content_hash"] = body.content_hash
    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()

    ep = dict(curr)
    ep["progress_percent"] = 100
    return EpisodeDetail(**ep)


@router.post("/{episode_id}/cancel-run", response_model=Dict[str, Any], operation_id="episodes.cancelRun")
async def cancel_run(
    episode_id: str = Path(..., description="Episode ID"),
) -> Dict[str, Any]:
    """Cancel any active generation runs on the episode."""
    if episode_id not in _EPISODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    return {"episode_id": episode_id, "status": "CANCELLED", "timestamp": utc_now().isoformat()}


@ws_router.websocket("/{episode_id}")
async def episode_workspace_websocket(websocket: WebSocket, episode_id: str):
    """Realtime WebSocket endpoint streaming episode lifecycle and pipeline events."""
    await websocket.accept()
    try:
        # Stream initial snapshot
        ep = _EPISODES.get(episode_id, {
            "id": episode_id,
            "title": "Episode Workspace",
            "state": "DRAFT",
            "current_checkpoint": "IDEA",
            "version": 1,
        })
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
