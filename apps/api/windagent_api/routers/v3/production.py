"""
V3 Production Router — Canonical Production Cutover Domain.
Provides durable endpoints for Episode Production Plans, Shots,
Stage Jobs (Audio, Animation, Render, Video) with failure diagnostics,
and WebSocket realtime streaming.

Phase 4: production plans, shots, jobs, and delivery artifacts are persisted
through the namespaced durable V3 resource authority. No module-level RAM stores.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import (
    NS_PRODUCTION_PLANS,
    NS_SHOTS,
    NS_PRODUCTION_JOBS,
    NS_DELIVERY_ARTIFACTS,
)

router = APIRouter(prefix="/api/v3", tags=["Production V3"])
ws_router = APIRouter(prefix="/ws/v3/production", tags=["Production V3 WebSocket"])


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


def _plan_to_resource(p: Dict[str, Any], shots_count: int) -> ProductionPlanResource:
    return ProductionPlanResource(
        id=p["id"],
        episode_id=p["episode_id"],
        project_id=p.get("project_id"),
        screenplay_revision_id=p["screenplay_revision_id"],
        storyboard_revision_id=p["storyboard_revision_id"],
        character_references=p.get("character_references", []),
        asset_references=p.get("asset_references", []),
        status=p.get("status", "ACTIVE"),
        progress_percent=p.get("progress_percent", 0),
        shots_count=shots_count,
        version=p.get("version", 1),
        created_at=p.get("created_at", ""),
        updated_at=p.get("updated_at", ""),
    )


def _shot_to_resource(s: Dict[str, Any]) -> ShotResource:
    return ShotResource(**s)


def _job_to_resource(j: Dict[str, Any]) -> ProductionJobResource:
    return ProductionJobResource(**j)


@router.get("/episodes/{episode_id}/production", response_model=ProductionPlanResource, operation_id="production.getPlan")
async def get_production_plan(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProductionPlanResource:
    """Retrieve the active production plan for an episode.

    P1.0 truth repair: GET is read-only. When no plan exists the API returns
    404 PRODUCTION_PLAN_NOT_CREATED; it never fabricates a plan (or synthetic
    revision pins) as a side effect of a read.
    """
    plan = await service.get(NS_PRODUCTION_PLANS, episode_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PRODUCTION_PLAN_NOT_CREATED",
                "message": (
                    f"No production plan initialized for episode '{episode_id}'. "
                    "Create one explicitly via POST /episodes/{episode_id}/production/plan."
                ),
            },
        )

    shots = await service.list(NS_SHOTS)
    shots = [s for s in shots if s.get("episode_id") == episode_id]
    return _plan_to_resource(plan, len(shots))


@router.post("/episodes/{episode_id}/production/plan", response_model=ProductionPlanResource, status_code=status.HTTP_201_CREATED, operation_id="production.createPlan")
async def create_production_plan(
    episode_id: str = Path(...),
    body: CreateProductionPlanRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
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
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_PRODUCTION_PLANS, episode_id, plan_data)
    shots = await service.list(NS_SHOTS)
    shots = [s for s in shots if s.get("episode_id") == episode_id]
    return _plan_to_resource(created, len(shots))


@router.get("/episodes/{episode_id}/shots", response_model=List[ShotResource], operation_id="production.listShots")
async def list_shots(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[ShotResource]:
    """List all production shots for an episode ordered by shot number."""
    shots = await service.list(NS_SHOTS)
    shots = [s for s in shots if s.get("episode_id") == episode_id]
    shots.sort(key=lambda s: s.get("shot_number", 0))
    return [_shot_to_resource(s) for s in shots]


@router.post("/episodes/{episode_id}/shots", response_model=ShotResource, status_code=status.HTTP_201_CREATED, operation_id="production.createShot")
async def create_shot(
    episode_id: str = Path(...),
    body: CreateShotRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ShotResource:
    """Create a new production shot record."""
    shot_id = f"shot-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    shots = await service.list(NS_SHOTS)
    shots = [s for s in shots if s.get("episode_id") == episode_id]
    next_number = body.shot_number or (len(shots) + 1)

    plan = await service.get(NS_PRODUCTION_PLANS, episode_id)
    plan_id = plan.get("id", f"plan-{episode_id}") if plan else f"plan-{episode_id}"
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
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_SHOTS, shot_id, new_shot)
    return _shot_to_resource(created)


@router.get("/shots/{shot_id}", response_model=ShotResource, operation_id="production.getShot")
async def get_shot(
    shot_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ShotResource:
    """Retrieve shot details."""
    shot = await service.get(NS_SHOTS, shot_id)
    if shot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    return _shot_to_resource(shot)


@router.patch("/shots/{shot_id}", response_model=ShotResource, operation_id="production.updateShot")
async def update_shot(
    shot_id: str = Path(...),
    body: UpdateShotRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ShotResource:
    """Update shot details with optimistic locking."""
    curr = await service.get(NS_SHOTS, shot_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for shot '{shot_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    if body.camera_movement is not None:
        updates["camera_movement"] = body.camera_movement
    if body.focal_length is not None:
        updates["focal_length"] = body.focal_length
    if body.duration_seconds is not None:
        updates["duration_seconds"] = body.duration_seconds
    if body.status is not None:
        updates["status"] = body.status
    if body.audio_asset_id is not None:
        updates["audio_asset_id"] = body.audio_asset_id
    if body.animation_asset_id is not None:
        updates["animation_asset_id"] = body.animation_asset_id
    if body.render_asset_id is not None:
        updates["render_asset_id"] = body.render_asset_id
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_SHOTS, shot_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for shot '{shot_id}'.")
    return _shot_to_resource(updated)


async def _submit_stage_job(
    episode_id: str,
    stage: str,
    body: SubmitJobRequest,
    service: V3ResourceService,
) -> JobSubmissionReceipt:
    """Fail closed: no production executor is composed in P1.

    P1.0 truth repair (P1.0.5): AUDIO/ANIMATION/RENDER/VIDEO submissions MUST
    NOT create fake ``QUEUED`` records without a real consumer. Until P2 wires
    actual executors, every submission returns CAPABILITY_UNAVAILABLE and
    persists nothing.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "CAPABILITY_UNAVAILABLE",
            "job_type": stage.upper(),
            "message": (
                f"No {stage.upper()} executor is composed in this deployment; "
                "production stage jobs are enabled in P2."
            ),
        },
    )


@router.post("/episodes/{episode_id}/production/audio/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitAudio")
async def submit_audio_job(
    episode_id: str = Path(...),
    body: SubmitJobRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> JobSubmissionReceipt:
    return await _submit_stage_job(episode_id, "AUDIO", body, service)


@router.post("/episodes/{episode_id}/production/animation/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitAnimation")
async def submit_animation_job(
    episode_id: str = Path(...),
    body: SubmitJobRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> JobSubmissionReceipt:
    return await _submit_stage_job(episode_id, "ANIMATION", body, service)


@router.post("/episodes/{episode_id}/production/render/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitRender")
async def submit_render_job(
    episode_id: str = Path(...),
    body: SubmitJobRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> JobSubmissionReceipt:
    return await _submit_stage_job(episode_id, "RENDER", body, service)


@router.post("/episodes/{episode_id}/production/video/submit", response_model=JobSubmissionReceipt, status_code=status.HTTP_201_CREATED, operation_id="production.submitVideo")
async def submit_video_job(
    episode_id: str = Path(...),
    body: SubmitJobRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> JobSubmissionReceipt:
    return await _submit_stage_job(episode_id, "VIDEO", body, service)


@router.post("/episodes/{episode_id}/production/{stage}/cancel", response_model=ProductionJobResource, operation_id="production.cancelJob")
async def cancel_job(
    episode_id: str = Path(...),
    stage: str = Path(...),
    body: CancelJobRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProductionJobResource:
    """Cancel a running or queued production job."""
    job = await service.get(NS_PRODUCTION_JOBS, body.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{body.job_id}' not found.")
    updates = dict(job)
    updates["state"] = "CANCELLED"
    updates["completed_at"] = utc_now().isoformat()
    updated = await service.update(NS_PRODUCTION_JOBS, body.job_id, updates, job["version"])
    return _job_to_resource(updated)


@router.post("/episodes/{episode_id}/production/{stage}/retry", response_model=JobSubmissionReceipt, operation_id="production.retryJob")
async def retry_job(
    episode_id: str = Path(...),
    stage: str = Path(...),
    body: RetryJobRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> JobSubmissionReceipt:
    """Retry a failed or blocked job.

    P1.0 truth repair: re-queueing without a real executor consumer is a fake
    ``QUEUED`` claim, so retries fail closed until P2 executors land.
    """
    job = await service.get(NS_PRODUCTION_JOBS, body.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{body.job_id}' not found.")
    if not job.get("retryable", True) and job.get("attempt", 1) >= job.get("max_attempts", 3):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{body.job_id}' has exceeded max retry attempts ({job.get('max_attempts')}).",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "CAPABILITY_UNAVAILABLE",
            "job_type": str(job.get("job_type") or stage).upper(),
            "message": (
                f"No {str(job.get('job_type') or stage).upper()} executor is composed in this "
                "deployment; production stage jobs are enabled in P2."
            ),
        },
    )


@router.get("/episodes/{episode_id}/production/jobs", response_model=List[ProductionJobResource], operation_id="production.listJobs")
async def list_production_jobs(
    episode_id: str = Path(...),
    stage: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[ProductionJobResource]:
    """List all production jobs for an episode."""
    jobs = await service.list(NS_PRODUCTION_JOBS)
    jobs = [j for j in jobs if j.get("episode_id") == episode_id]
    if stage:
        jobs = [j for j in jobs if j.get("job_type", "").upper() == stage.upper()]
    return [_job_to_resource(j) for j in jobs]


@router.get("/production/jobs/{job_id}", response_model=ProductionJobResource, operation_id="production.getJob")
async def get_production_job(
    job_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProductionJobResource:
    """Retrieve details of a specific job."""
    job = await service.get(NS_PRODUCTION_JOBS, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    return _job_to_resource(job)


@router.get("/episodes/{episode_id}/production/delivery", response_model=DeliveryArtifactResource, operation_id="production.getDelivery")
async def get_delivery_artifact(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> DeliveryArtifactResource:
    """Get final delivery package for an episode.

    P1.0 truth repair: read-only. No delivery record is fabricated on GET.
    """
    delivery = await service.get(NS_DELIVERY_ARTIFACTS, episode_id)
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "DELIVERY_ARTIFACT_NOT_READY",
                "message": f"No delivery artifact produced yet for episode '{episode_id}'.",
            },
        )
    return DeliveryArtifactResource(**delivery)


@ws_router.websocket("/{episode_id}")
async def production_realtime_ws(websocket: WebSocket, episode_id: str):
    """Realtime WebSocket streaming production job updates and status changes."""
    await websocket.accept()
    try:
        # Send initial snapshot
        container = getattr(websocket.app.state, "container", None)
        service = container.v3_resource_service if container else None
        plan = None
        shots = []
        jobs = []
        if service is not None:
            plan = await service.get(NS_PRODUCTION_PLANS, episode_id)
            shots = await service.list(NS_SHOTS)
            shots = [s for s in shots if s.get("episode_id") == episode_id]
            jobs = await service.list(NS_PRODUCTION_JOBS)
            jobs = [j for j in jobs if j.get("episode_id") == episode_id]

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
