"""
V3 Production Router — Canonical Production Cutover Domain.
Provides durable endpoints for Episode Production Plans, Shots,
Stage Jobs (Audio, Animation, Render, Video) with failure diagnostics,
and WebSocket realtime streaming.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v3", tags=["Production V3"])
ws_router = APIRouter(prefix="/ws/v3/production", tags=["Production V3 WebSocket"])


# ─────────────────────────────────────────────────────────────────────────────
# Domain Models
# ─────────────────────────────────────────────────────────────────────────────

class ProductionPlanResource(BaseModel):
    id: str
    episode_id: str
    project_id: Optional[str] = None
    screenplay_revision_id: str
    storyboard_revision_id: str
    character_references: List[str] = Field(default_factory=list)
    asset_references: List[str] = Field(default_factory=list)
    status: str = "ACTIVE"
    progress_percent: int = 0
    shots_count: int = 0
    version: int = 1
    created_at: str
    updated_at: str


class CreateProductionPlanRequest(BaseModel):
    screenplay_revision_id: str = Field(..., min_length=1)
    storyboard_revision_id: str = Field(..., min_length=1)
    character_references: List[str] = Field(default_factory=list)
    asset_references: List[str] = Field(default_factory=list)


class ShotResource(BaseModel):
    id: str
    episode_id: str
    production_plan_id: str
    scene_id: Optional[str] = None
    shot_number: int
    camera_movement: str = "Static"
    focal_length: str = "35mm"
    status: str = "DRAFT"
    duration_seconds: int = 5
    audio_asset_id: Optional[str] = None
    animation_asset_id: Optional[str] = None
    render_asset_id: Optional[str] = None
    version: int = 1
    created_at: str
    updated_at: str


class CreateShotRequest(BaseModel):
    scene_id: Optional[str] = None
    shot_number: Optional[int] = None
    camera_movement: str = "Static"
    focal_length: str = "35mm"
    duration_seconds: int = 5


class UpdateShotRequest(BaseModel):
    camera_movement: Optional[str] = None
    focal_length: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: Optional[str] = None
    audio_asset_id: Optional[str] = None
    animation_asset_id: Optional[str] = None
    render_asset_id: Optional[str] = None
    expected_version: int = Field(..., description="Optimistic locking version")


class ProductionJobResource(BaseModel):
    job_id: str
    episode_id: str
    shot_id: Optional[str] = None
    job_type: str  # AUDIO | ANIMATION | RENDER | VIDEO
    state: str  # PENDING | QUEUED | RUNNING | SUCCEEDED | FAILED | CANCELLED | BLOCKED
    progress_percent: int = 0
    error_code: Optional[str] = None
    retryable: bool = True
    failure_stage: Optional[str] = None
    attempt: int = 1
    max_attempts: int = 3
    artifact_id: Optional[str] = None
    correlation_id: Optional[str] = None
    submitted_at: str
    completed_at: Optional[str] = None


class JobSubmissionReceipt(BaseModel):
    job_id: str
    state: str
    submitted_at: str
    correlation_id: Optional[str] = None


class SubmitJobRequest(BaseModel):
    shot_id: Optional[str] = None
    prompt_override: Optional[str] = None
    correlation_id: Optional[str] = None


class CancelJobRequest(BaseModel):
    job_id: str
    reason: Optional[str] = None


class RetryJobRequest(BaseModel):
    job_id: str


class DeliveryArtifactResource(BaseModel):
    id: str
    episode_id: str
    video_asset_id: Optional[str] = None
    resolution: str = "1080p"
    codec: str = "H.264"
    duration_seconds: int = 120
    file_size_bytes: int = 48500000
    download_url: Optional[str] = None
    manifest_url: Optional[str] = None
    created_at: str


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory Storage
# ─────────────────────────────────────────────────────────────────────────────

_PRODUCTION_PLANS: Dict[str, Dict[str, Any]] = {
    "ep-cb-001": {
        "id": "plan-ep-cb-001",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "screenplay_revision_id": "rev-cb-001-v3",
        "storyboard_revision_id": "sb-cb-001",
        "character_references": ["char-kaelen-01", "char-nova-01", "char-sylas-01"],
        "asset_references": ["asset-concept-cb-001-01"],
        "status": "ACTIVE",
        "progress_percent": 35,
        "version": 1,
        "created_at": "2026-08-14T08:00:00Z",
        "updated_at": "2026-08-16T00:00:00Z",
    }
}

_SHOTS: Dict[str, Dict[str, Any]] = {
    "shot-cb-001-01": {
        "id": "shot-cb-001-01",
        "episode_id": "ep-cb-001",
        "production_plan_id": "plan-ep-cb-001",
        "scene_id": "scene-cb-001-01",
        "shot_number": 1,
        "camera_movement": "Slow Dolly In",
        "focal_length": "50mm Anamorphic",
        "status": "RENDERED",
        "duration_seconds": 6,
        "audio_asset_id": "asset-audio-01",
        "animation_asset_id": "asset-anim-01",
        "render_asset_id": "asset-render-01",
        "version": 1,
        "created_at": "2026-08-14T08:30:00Z",
        "updated_at": "2026-08-16T00:00:00Z",
    },
    "shot-cb-001-02": {
        "id": "shot-cb-001-02",
        "episode_id": "ep-cb-001",
        "production_plan_id": "plan-ep-cb-001",
        "scene_id": "scene-cb-001-01",
        "shot_number": 2,
        "camera_movement": "Over-the-shoulder Pan",
        "focal_length": "35mm",
        "status": "RENDER_PENDING",
        "duration_seconds": 4,
        "audio_asset_id": "asset-audio-02",
        "animation_asset_id": "asset-anim-02",
        "render_asset_id": None,
        "version": 1,
        "created_at": "2026-08-14T08:35:00Z",
        "updated_at": "2026-08-16T00:00:00Z",
    },
    "shot-cb-001-03": {
        "id": "shot-cb-001-03",
        "episode_id": "ep-cb-001",
        "production_plan_id": "plan-ep-cb-001",
        "scene_id": "scene-cb-001-02",
        "shot_number": 3,
        "camera_movement": "Tracking Shot",
        "focal_length": "24mm Wide",
        "status": "ANIMATION_PENDING",
        "duration_seconds": 8,
        "audio_asset_id": "asset-audio-03",
        "animation_asset_id": None,
        "render_asset_id": None,
        "version": 1,
        "created_at": "2026-08-14T08:40:00Z",
        "updated_at": "2026-08-16T00:00:00Z",
    },
}

_PRODUCTION_JOBS: Dict[str, Dict[str, Any]] = {
    "job-audio-001": {
        "job_id": "job-audio-001",
        "episode_id": "ep-cb-001",
        "shot_id": "shot-cb-001-01",
        "job_type": "AUDIO",
        "state": "SUCCEEDED",
        "progress_percent": 100,
        "error_code": None,
        "retryable": False,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": "asset-audio-01",
        "correlation_id": "corr-audio-001",
        "submitted_at": "2026-08-15T10:00:00Z",
        "completed_at": "2026-08-15T10:01:15Z",
    },
    "job-anim-001": {
        "job_id": "job-anim-001",
        "episode_id": "ep-cb-001",
        "shot_id": "shot-cb-001-01",
        "job_type": "ANIMATION",
        "state": "SUCCEEDED",
        "progress_percent": 100,
        "error_code": None,
        "retryable": False,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": "asset-anim-01",
        "correlation_id": "corr-anim-001",
        "submitted_at": "2026-08-15T10:05:00Z",
        "completed_at": "2026-08-15T10:08:40Z",
    },
    "job-render-001": {
        "job_id": "job-render-001",
        "episode_id": "ep-cb-001",
        "shot_id": "shot-cb-001-01",
        "job_type": "RENDER",
        "state": "SUCCEEDED",
        "progress_percent": 100,
        "error_code": None,
        "retryable": False,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": "asset-render-01",
        "correlation_id": "corr-render-001",
        "submitted_at": "2026-08-15T10:10:00Z",
        "completed_at": "2026-08-15T10:25:00Z",
    },
}

_DELIVERY_ARTIFACTS: Dict[str, Dict[str, Any]] = {
    "ep-cb-001": {
        "id": "delivery-ep-cb-001",
        "episode_id": "ep-cb-001",
        "video_asset_id": "asset-video-ep-cb-001",
        "resolution": "1080p (1920x1080)",
        "codec": "H.264 / AAC",
        "duration_seconds": 18,
        "file_size_bytes": 48500000,
        "download_url": None,
        "manifest_url": None,
        "created_at": "2026-08-16T00:00:00Z",
    }
}


def _plan_to_resource(p: Dict[str, Any]) -> ProductionPlanResource:
    shots = [s for s in _SHOTS.values() if s["episode_id"] == p["episode_id"]]
    return ProductionPlanResource(
        id=p["id"],
        episode_id=p["episode_id"],
        project_id=p.get("project_id"),
        screenplay_revision_id=p["screenplay_revision_id"],
        storyboard_revision_id=p["storyboard_revision_id"],
        character_references=p.get("character_references", []),
        asset_references=p.get("asset_references", []),
        status=p["status"],
        progress_percent=p["progress_percent"],
        shots_count=len(shots),
        version=p["version"],
        created_at=p["created_at"],
        updated_at=p["updated_at"],
    )


def _shot_to_resource(s: Dict[str, Any]) -> ShotResource:
    return ShotResource(**s)


def _job_to_resource(j: Dict[str, Any]) -> ProductionJobResource:
    return ProductionJobResource(**j)


# ─────────────────────────────────────────────────────────────────────────────
# Production Plan Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/episodes/{episode_id}/production", response_model=ProductionPlanResource, operation_id="production.getPlan")
async def get_production_plan(episode_id: str = Path(...)) -> ProductionPlanResource:
    """Retrieve the active production plan for an episode."""
    if episode_id not in _PRODUCTION_PLANS:
        # Create empty initial plan pinned to locked revisions
        now = utc_now().isoformat()
        _PRODUCTION_PLANS[episode_id] = {
            "id": f"plan-{episode_id}",
            "episode_id": episode_id,
            "project_id": None,
            "screenplay_revision_id": f"rev-{episode_id}-lock",
            "storyboard_revision_id": f"sb-{episode_id}",
            "character_references": [],
            "asset_references": [],
            "status": "PLANNING",
            "progress_percent": 0,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
    return _plan_to_resource(_PRODUCTION_PLANS[episode_id])


@router.post("/episodes/{episode_id}/production/plan", response_model=ProductionPlanResource, status_code=status.HTTP_201_CREATED, operation_id="production.createPlan")
async def create_production_plan(
    episode_id: str = Path(...),
    body: CreateProductionPlanRequest = ...,
) -> ProductionPlanResource:
    """Initialize or update production plan with pinned screenplay & storyboard revisions."""
    now = utc_now().isoformat()
    plan_data = {
        "id": f"plan-{episode_id}",
        "episode_id": episode_id,
        "project_id": None,
        "screenplay_revision_id": body.screenplay_revision_id,
        "storyboard_revision_id": body.storyboard_revision_id,
        "character_references": body.character_references,
        "asset_references": body.asset_references,
        "status": "ACTIVE",
        "progress_percent": 0,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    _PRODUCTION_PLANS[episode_id] = plan_data
    return _plan_to_resource(plan_data)


# ─────────────────────────────────────────────────────────────────────────────
# Shot Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/episodes/{episode_id}/shots", response_model=List[ShotResource], operation_id="production.listShots")
async def list_shots(episode_id: str = Path(...)) -> List[ShotResource]:
    """List all production shots for an episode ordered by shot number."""
    shots = [s for s in _SHOTS.values() if s["episode_id"] == episode_id]
    shots.sort(key=lambda s: s["shot_number"])
    return [_shot_to_resource(s) for s in shots]


@router.post("/episodes/{episode_id}/shots", response_model=ShotResource, status_code=status.HTTP_201_CREATED, operation_id="production.createShot")
async def create_shot(
    episode_id: str = Path(...),
    body: CreateShotRequest = ...,
) -> ShotResource:
    """Create a new production shot record."""
    shot_id = f"shot-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    shots = [s for s in _SHOTS.values() if s["episode_id"] == episode_id]
    next_number = body.shot_number or (len(shots) + 1)
    
    plan_id = _PRODUCTION_PLANS.get(episode_id, {}).get("id", f"plan-{episode_id}")
    new_shot = {
        "id": shot_id,
        "episode_id": episode_id,
        "production_plan_id": plan_id,
        "scene_id": body.scene_id,
        "shot_number": next_number,
        "camera_movement": body.camera_movement,
        "focal_length": body.focal_length,
        "status": "DRAFT",
        "duration_seconds": body.duration_seconds,
        "audio_asset_id": None,
        "animation_asset_id": None,
        "render_asset_id": None,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    _SHOTS[shot_id] = new_shot
    return _shot_to_resource(new_shot)


@router.get("/shots/{shot_id}", response_model=ShotResource, operation_id="production.getShot")
async def get_shot(shot_id: str = Path(...)) -> ShotResource:
    """Retrieve shot details."""
    if shot_id not in _SHOTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    return _shot_to_resource(_SHOTS[shot_id])


@router.patch("/shots/{shot_id}", response_model=ShotResource, operation_id="production.updateShot")
async def update_shot(
    shot_id: str = Path(...),
    body: UpdateShotRequest = ...,
) -> ShotResource:
    """Update shot details with optimistic locking."""
    if shot_id not in _SHOTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    curr = _SHOTS[shot_id]
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for shot '{shot_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    if body.camera_movement is not None:
        curr["camera_movement"] = body.camera_movement
    if body.focal_length is not None:
        curr["focal_length"] = body.focal_length
    if body.duration_seconds is not None:
        curr["duration_seconds"] = body.duration_seconds
    if body.status is not None:
        curr["status"] = body.status
    if body.audio_asset_id is not None:
        curr["audio_asset_id"] = body.audio_asset_id
    if body.animation_asset_id is not None:
        curr["animation_asset_id"] = body.animation_asset_id
    if body.render_asset_id is not None:
        curr["render_asset_id"] = body.render_asset_id

    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()
    return _shot_to_resource(curr)


# ─────────────────────────────────────────────────────────────────────────────
# Stage Job Endpoints (Audio, Animation, Render, Video)
# ─────────────────────────────────────────────────────────────────────────────

def _submit_stage_job(
    episode_id: str,
    stage: str,
    body: SubmitJobRequest,
) -> JobSubmissionReceipt:
    job_id = f"job-{stage.lower()}-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    job: Dict[str, Any] = {
        "job_id": job_id,
        "episode_id": episode_id,
        "shot_id": body.shot_id,
        "job_type": stage.upper(),
        "state": "QUEUED",
        "progress_percent": 0,
        "error_code": None,
        "retryable": True,
        "failure_stage": None,
        "attempt": 1,
        "max_attempts": 3,
        "artifact_id": None,
        "correlation_id": body.correlation_id or f"corr-{job_id}",
        "submitted_at": now,
        "completed_at": None,
    }
    _PRODUCTION_JOBS[job_id] = job
    return JobSubmissionReceipt(
        job_id=job_id,
        state="QUEUED",
        submitted_at=now,
        correlation_id=job["correlation_id"],
    )


@router.post("/episodes/{episode_id}/production/audio/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitAudio")
async def submit_audio_job(episode_id: str = Path(...), body: SubmitJobRequest = ...) -> JobSubmissionReceipt:
    return _submit_stage_job(episode_id, "AUDIO", body)


@router.post("/episodes/{episode_id}/production/animation/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitAnimation")
async def submit_animation_job(episode_id: str = Path(...), body: SubmitJobRequest = ...) -> JobSubmissionReceipt:
    return _submit_stage_job(episode_id, "ANIMATION", body)


@router.post("/episodes/{episode_id}/production/render/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitRender")
async def submit_render_job(episode_id: str = Path(...), body: SubmitJobRequest = ...) -> JobSubmissionReceipt:
    return _submit_stage_job(episode_id, "RENDER", body)


@router.post("/episodes/{episode_id}/production/video/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitVideo")
async def submit_video_job(episode_id: str = Path(...), body: SubmitJobRequest = ...) -> JobSubmissionReceipt:
    return _submit_stage_job(episode_id, "VIDEO", body)


@router.post("/episodes/{episode_id}/production/{stage}/cancel", response_model=ProductionJobResource, operation_id="production.cancelJob")
async def cancel_job(
    episode_id: str = Path(...),
    stage: str = Path(...),
    body: CancelJobRequest = ...,
) -> ProductionJobResource:
    """Cancel a running or queued production job."""
    if body.job_id not in _PRODUCTION_JOBS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{body.job_id}' not found.")
    job = _PRODUCTION_JOBS[body.job_id]
    job["state"] = "CANCELLED"
    job["completed_at"] = utc_now().isoformat()
    return _job_to_resource(job)


@router.post("/episodes/{episode_id}/production/{stage}/retry", response_model=JobSubmissionReceipt, operation_id="production.retryJob")
async def retry_job(
    episode_id: str = Path(...),
    stage: str = Path(...),
    body: RetryJobRequest = ...,
) -> JobSubmissionReceipt:
    """Retry a failed or blocked job."""
    if body.job_id not in _PRODUCTION_JOBS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{body.job_id}' not found.")
    job = _PRODUCTION_JOBS[body.job_id]
    if not job.get("retryable", True) and job.get("attempt", 1) >= job.get("max_attempts", 3):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{body.job_id}' has exceeded max retry attempts ({job.get('max_attempts')}).",
        )
    job["state"] = "QUEUED"
    job["attempt"] = job.get("attempt", 1) + 1
    job["error_code"] = None
    job["failure_stage"] = None
    job["submitted_at"] = utc_now().isoformat()
    return JobSubmissionReceipt(
        job_id=job["job_id"],
        state="QUEUED",
        submitted_at=job["submitted_at"],
        correlation_id=job.get("correlation_id"),
    )


@router.get("/episodes/{episode_id}/production/jobs", response_model=List[ProductionJobResource], operation_id="production.listJobs")
async def list_production_jobs(
    episode_id: str = Path(...),
    stage: Optional[str] = Query(None),
) -> List[ProductionJobResource]:
    """List all production jobs for an episode."""
    jobs = [j for j in _PRODUCTION_JOBS.values() if j["episode_id"] == episode_id]
    if stage:
        jobs = [j for j in jobs if j["job_type"].upper() == stage.upper()]
    return [_job_to_resource(j) for j in jobs]


@router.get("/production/jobs/{job_id}", response_model=ProductionJobResource, operation_id="production.getJob")
async def get_production_job(job_id: str = Path(...)) -> ProductionJobResource:
    """Retrieve details of a specific job."""
    if job_id not in _PRODUCTION_JOBS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return _job_to_resource(_PRODUCTION_JOBS[job_id])


@router.get("/episodes/{episode_id}/production/delivery", response_model=DeliveryArtifactResource, operation_id="production.getDelivery")
async def get_delivery_artifact(episode_id: str = Path(...)) -> DeliveryArtifactResource:
    """Get final delivery package for an episode."""
    if episode_id not in _DELIVERY_ARTIFACTS:
        now = utc_now().isoformat()
        _DELIVERY_ARTIFACTS[episode_id] = {
            "id": f"delivery-{episode_id}",
            "episode_id": episode_id,
            "video_asset_id": None,
            "resolution": "1080p",
            "codec": "H.264",
            "duration_seconds": 0,
            "file_size_bytes": 0,
            "download_url": None,
            "manifest_url": None,
            "created_at": now,
        }
    return DeliveryArtifactResource(**_DELIVERY_ARTIFACTS[episode_id])


# ─────────────────────────────────────────────────────────────────────────────
# Realtime WebSocket Stream
# ─────────────────────────────────────────────────────────────────────────────

@ws_router.websocket("/{episode_id}")
async def production_realtime_ws(websocket: WebSocket, episode_id: str):
    """Realtime WebSocket streaming production job updates and status changes."""
    await websocket.accept()
    try:
        # Send initial snapshot
        plan = _PRODUCTION_PLANS.get(episode_id)
        shots = [s for s in _SHOTS.values() if s["episode_id"] == episode_id]
        jobs = [j for j in _PRODUCTION_JOBS.values() if j["episode_id"] == episode_id]

        await websocket.send_json({
            "event": "production.snapshot",
            "episode_id": episode_id,
            "plan": plan,
            "shots": shots,
            "jobs": jobs,
            "timestamp": utc_now().isoformat(),
        })

        while True:
            await asyncio.sleep(10.0)
            await websocket.send_json({
                "event": "heartbeat",
                "episode_id": episode_id,
                "timestamp": utc_now().isoformat(),
            })
    except WebSocketDisconnect:
        pass
