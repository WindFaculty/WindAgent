"""
V3 Production Router — Canonical Production Cutover Domain.
Provides durable endpoints for Episode Production Plans, Shots,
Stage Jobs (Audio, Animation, Render, Video) with failure diagnostics,
and WebSocket realtime streaming.

Phase 4: production plans, shots, jobs, and delivery artifacts are persisted
through the namespaced durable V3 resource authority. No module-level RAM stores.

P1.5 Shot Planning: the existing Shot resource is EXTENDED (never duplicated)
into a production shot model (shot size / framing / angle / lens / subjects /
continuity), generated deterministically per scene from the synced storyboard.
Shot timing must sum to scene duration within tolerance, structural continuity
is validated, and a pinned shot plan is immutable — edits require deriving a
new revision (plan P1.5.1–P1.5.5).
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.character_canon_authority import (
    CHARACTER_STATUS_PRODUCTION_READY,
    compute_content_hash,
)
from windagent_api.services.preproduction_authority import (
    LockedScreenplayRef,
    PreproductionAuthorityError,
    resolve_locked_screenplay,
)
from windagent_api.services.asset_requirement_authority import NS_ASSET_REQUIREMENTS
from windagent_api.routers.v3.storyboard import (
    NS_STORYBOARD_REVISIONS,
    _compute_storyboard_revision_hash,
)
from windagent_api.routers.v3.assets import ASSET_STATUS_PINNED
from windagent_api.services.v3_demo_seed import (
    NS_CHARACTERS,
    NS_EPISODES,
    NS_PRODUCTION_PLANS,
    NS_SCENES,
    NS_SHOTS,
    NS_WORLD_BIBLES,
    NS_PRODUCTION_JOBS,
    NS_DELIVERY_ARTIFACTS,
)

router = APIRouter(prefix="/api/v3", tags=["Production V3"])
ws_router = APIRouter(prefix="/ws/v3/production", tags=["Production V3 WebSocket"])

NS_STORYBOARDS = "storyboards"
NS_ASSETS = "assets"
NS_SHOT_PLANS = "shot_plans"
NS_SHOT_PLAN_REVISIONS = "shot_plan_revisions"

# Σ shot.duration ≈ scene.duration tolerance (plan P1.5.3): small drift is a
# warning; a mismatch beyond this fraction of the scene duration is blocking.
DURATION_TOLERANCE_FRACTION = 0.2
DURATION_TOLERANCE_MIN_SECONDS = 5


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
    shot_size: str = "MEDIUM"
    framing: str = ""
    camera_angle: str = "Eye Level"
    camera_movement: str = "Static"
    focal_length: str = "35mm"
    status: str = "DRAFT"
    duration_seconds: int = 5
    subject_character_refs: List[str] = Field(default_factory=list)
    location_ref: str = ""
    asset_refs: List[str] = Field(default_factory=list)
    action: str = ""
    dialogue_ref: Optional[str] = None
    audio_cue: str = ""
    lighting_intent: str = ""
    composition_notes: str = ""
    continuity_from: Optional[str] = None
    continuity_to: Optional[str] = None
    audio_asset_id: Optional[str] = None
    animation_asset_id: Optional[str] = None
    render_asset_id: Optional[str] = None
    version: int = 1
    created_at: str
    updated_at: str


class CreateShotRequest(BaseModel):
    scene_id: Optional[str] = None
    shot_number: Optional[int] = None
    shot_size: str = "MEDIUM"
    framing: str = ""
    camera_angle: str = "Eye Level"
    camera_movement: str = "Static"
    focal_length: str = "35mm"
    duration_seconds: int = 5
    subject_character_refs: List[str] = Field(default_factory=list)
    location_ref: str = ""
    asset_refs: List[str] = Field(default_factory=list)
    action: str = ""
    dialogue_ref: Optional[str] = None
    audio_cue: str = ""
    lighting_intent: str = ""
    composition_notes: str = ""


class UpdateShotRequest(BaseModel):
    shot_size: Optional[str] = None
    framing: Optional[str] = None
    camera_angle: Optional[str] = None
    camera_movement: Optional[str] = None
    focal_length: Optional[str] = None
    duration_seconds: Optional[int] = Field(None, ge=1)
    subject_character_refs: Optional[List[str]] = None
    location_ref: Optional[str] = None
    asset_refs: Optional[List[str]] = None
    action: Optional[str] = None
    dialogue_ref: Optional[str] = None
    audio_cue: Optional[str] = None
    lighting_intent: Optional[str] = None
    composition_notes: Optional[str] = None
    status: Optional[str] = None
    audio_asset_id: Optional[str] = None
    animation_asset_id: Optional[str] = None
    render_asset_id: Optional[str] = None
    expected_version: int = Field(..., description="Optimistic locking version")


class ReorderShotRequest(BaseModel):
    new_position: int = Field(..., ge=1, description="1-based position in the episode shot order")
    expected_version: int = Field(..., description="Optimistic locking version")


class SplitShotRequest(BaseModel):
    expected_version: int = Field(..., description="Optimistic locking version")
    split_seconds: Optional[int] = Field(
        None, ge=1, description="Duration assigned to part 1; defaults to an even split."
    )


class MergeShotsRequest(BaseModel):
    shot_ids: List[str] = Field(..., min_length=2, description="Consecutive shots to merge, in order")
    expected_versions: Dict[str, int] = Field(..., description="Optimistic lock version per shot id")


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
    await _assert_shot_plan_not_pinned(service, episode_id)
    shot_id = f"shot-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    shots = [s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id]
    next_number = body.shot_number or (max((int(s.get("shot_number", 0)) for s in shots), default=0) + 1)

    plan = await service.get(NS_PRODUCTION_PLANS, episode_id)
    plan_id = plan.get("id", f"plan-{episode_id}") if plan else f"plan-{episode_id}"
    new_shot = {
        "id": shot_id,
        "episode_id": episode_id,
        "production_plan_id": plan_id,
        "scene_id": body.scene_id,
        "shot_number": next_number,
        "shot_size": body.shot_size,
        "framing": body.framing,
        "camera_angle": body.camera_angle,
        "camera_movement": body.camera_movement,
        "focal_length": body.focal_length,
        "status": "DRAFT",
        "duration_seconds": max(1, int(body.duration_seconds)),
        "subject_character_refs": list(body.subject_character_refs),
        "location_ref": body.location_ref,
        "asset_refs": list(body.asset_refs),
        "action": body.action,
        "dialogue_ref": body.dialogue_ref,
        "audio_cue": body.audio_cue,
        "lighting_intent": body.lighting_intent,
        "composition_notes": body.composition_notes,
        "continuity_from": None,
        "continuity_to": None,
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
    """Update shot details with optimistic locking (plan P1.5.5)."""
    curr = await service.get(NS_SHOTS, shot_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    await _assert_shot_plan_not_pinned(service, curr.get("episode_id") or "")
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for shot '{shot_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    for field in (
        "shot_size", "framing", "camera_angle", "camera_movement", "focal_length",
        "location_ref", "action", "dialogue_ref", "audio_cue", "lighting_intent",
        "composition_notes", "status", "audio_asset_id", "animation_asset_id", "render_asset_id",
    ):
        value = getattr(body, field)
        if value is not None:
            updates[field] = value
    if body.duration_seconds is not None:
        updates["duration_seconds"] = max(1, int(body.duration_seconds))
    for list_field in ("subject_character_refs", "asset_refs"):
        value = getattr(body, list_field)
        if value is not None:
            updates[list_field] = list(value)
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_SHOTS, shot_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for shot '{shot_id}'.")
    return _shot_to_resource(updated)


# ─────────────────────────────────────────────────────────────────────────────
# P1.5 — Shot Planning: deterministic generation, validation, pinning
# ─────────────────────────────────────────────────────────────────────────────

async def _get_shot_plan(service: V3ResourceService, episode_id: str) -> Optional[Dict[str, Any]]:
    return await service.get(NS_SHOT_PLANS, episode_id)


async def _assert_shot_plan_not_pinned(service: V3ResourceService, episode_id: str) -> None:
    """Pinned shot plans are immutable — edits must derive a new revision."""
    plan = await _get_shot_plan(service, episode_id)
    if plan is not None and str(plan.get("status")) == "PINNED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SHOT_PLAN_PINNED",
                "message": (
                    f"The shot plan for episode '{episode_id}' is pinned. "
                    "Derive a new draft revision via "
                    "POST /episodes/{episode_id}/production/shot-plan/actions/derive."
                ),
            },
        )


def _distribute_seconds(total: int, weights: List[float]) -> List[int]:
    """Split `total` seconds into integer parts matching the weights exactly."""
    weights = [max(0.0, w) for w in weights] or [1.0]
    scale = sum(weights)
    raw = [total * w / scale for w in weights]
    parts = [max(1, int(r)) for r in raw]
    # Give the remainder to the largest-weight part; clamp to >=1 everywhere.
    diff = total - sum(parts)
    if diff != 0:
        idx = max(range(len(parts)), key=lambda i: weights[i])
        parts[idx] = max(1, parts[idx] + diff)
    return parts


_SCENE_COVERAGE = [
    # (has dialogue?, shot recipe [(size, focal, weight)])
    (True, [("WIDE", "24mm", 0.25), ("MEDIUM", "50mm", 0.45), ("CLOSE_UP", "85mm", 0.30)]),
    (False, [("WIDE", "24mm", 0.60), ("MEDIUM", "50mm", 0.40)]),
]


async def _generate_shots_for_scenes(
    service: V3ResourceService,
    scenes: List[Dict[str, Any]],
    existing_by_scene: Dict[str, List[Dict[str, Any]]],
    episode_id: str,
    plan_id: str,
    now: str,
) -> List[Dict[str, Any]]:
    """Deterministic rule-based shot projection (plan P1.4→P1.5 bridge).

    No LLM: coverage recipes distribute the scene duration across a small
    fixed shot set so Σ shot.duration == scene.duration exactly.
    """
    all_shots = [s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id]
    next_number = max((int(s.get("shot_number", 0)) for s in all_shots), default=0)

    created: List[Dict[str, Any]] = []
    for scene in scenes:
        scene_id = scene["id"]
        if existing_by_scene.get(scene_id):
            continue  # manual work and prior generations are never clobbered
        has_dialogue = bool(scene.get("dialogue_refs"))
        _flag, recipe = _SCENE_COVERAGE[0] if has_dialogue else _SCENE_COVERAGE[1]
        durations = _distribute_seconds(int(scene.get("duration_seconds", 60)), [w for _, _, w in recipe])

        prev_shot_id: Optional[str] = None
        prev_stored: Optional[Dict[str, Any]] = None
        for (size, focal, _w), dur in zip(recipe, durations):
            next_number += 1
            shot_id = f"shot-{uuid.uuid4().hex[:8]}"
            record = {
                "id": shot_id,
                "episode_id": episode_id,
                "production_plan_id": plan_id,
                "scene_id": scene_id,
                "shot_number": next_number,
                "shot_size": size,
                "framing": "",
                "camera_angle": "Eye Level",
                "camera_movement": "Static",
                "focal_length": focal,
                "status": "DRAFT",
                "duration_seconds": max(1, int(dur)),
                "subject_character_refs": list(scene.get("character_ids") or []),
                "location_ref": str(scene.get("location_id") or ""),
                "asset_refs": list(scene.get("required_asset_refs") or []),
                "action": str(scene.get("action_summary") or ""),
                "dialogue_ref": None,
                "audio_cue": "",
                "lighting_intent": "",
                "composition_notes": "",
                "continuity_from": prev_shot_id,
                "continuity_to": None,
                "audio_asset_id": None,
                "animation_asset_id": None,
                "render_asset_id": None,
                "created_at": now,
                "updated_at": now,
            }
            stored = await service.create(NS_SHOTS, shot_id, record)
            if prev_shot_id is not None and prev_stored is not None:
                # Full-record replace: repo.update swaps the whole data payload.
                prev_updates = dict(prev_stored)
                prev_updates["continuity_to"] = shot_id
                prev_updates["updated_at"] = now
                await service.update(
                    NS_SHOTS, prev_shot_id, prev_updates, prev_stored.get("version", 1)
                )
            prev_stored = stored
            created.append(stored)
            prev_shot_id = shot_id
    return created


async def validate_episode_shots(
    service: V3ResourceService, episode_id: str
) -> Dict[str, Any]:
    """Structural shot-plan validation (plans P1.5.3 + P1.5.4).

    Read-only. Returns blocking findings + warnings:
    - SHOT_DURATION_MISMATCH: Σ shot.duration deviates from its scene beyond
      tolerance.
    - EPISODE_DURATION_MISMATCH / EPISODE_DURATION_TARGET_ABSENT: soft target
      checks against episode.metadata.target_duration_seconds.
    - UNRESOLVED_CHARACTER_REF / UNRESOLVED_ASSET_REF: dangling references.
    - CONTINUITY_LOCATION_BREAK: consecutive shots of one scene change location.
    - ORPHAN_SHOT: shot points at a scene that does not exist on this episode.
    """
    findings: List[Dict[str, Any]] = []
    scenes = sorted(
        (s for s in await service.list(NS_SCENES) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("scene_number", 0),
    )
    shots = sorted(
        (s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("shot_number", 0),
    )
    characters = {c["id"] for c in await service.list(NS_CHARACTERS)}
    # A shot may reference either a concrete approved asset or an open
    # asset requirement — both are valid production references at this stage.
    assets = {a["id"] for a in await service.list(NS_ASSETS)}
    assets |= {
        r["requirement_id"]
        for r in await service.list("asset_requirements")
        if r.get("requirement_id")
    }
    scene_ids = {s["id"] for s in scenes}

    by_scene: Dict[str, List[Dict[str, Any]]] = {}
    for shot in shots:
        sid = str(shot.get("scene_id") or "")
        by_scene.setdefault(sid, []).append(shot)

    planned_total = 0
    for scene in scenes:
        scene_id = scene["id"]
        scene_shots = by_scene.get(scene_id, [])
        if not scene_shots:
            continue
        planned = sum(int(s.get("duration_seconds", 0)) for s in scene_shots)
        planned_total += planned
        target = int(scene.get("duration_seconds", 0))
        tolerance = max(DURATION_TOLERANCE_MIN_SECONDS, int(target * DURATION_TOLERANCE_FRACTION))
        if abs(planned - target) > tolerance:
            findings.append({
                "code": "SHOT_DURATION_MISMATCH",
                "severity": "BLOCKING",
                "scene_id": scene_id,
                "message": (
                    f"Scene {scene.get('scene_number')}: shots sum to {planned}s "
                    f"but scene duration is {target}s (tolerance ±{tolerance}s)."
                ),
            })
        prev: Optional[Dict[str, Any]] = None
        for shot in scene_shots:
            for cid in shot.get("subject_character_refs") or []:
                if cid not in characters:
                    findings.append({
                        "code": "UNRESOLVED_CHARACTER_REF",
                        "severity": "BLOCKING",
                        "shot_id": shot["id"],
                        "message": f"Shot {shot.get('shot_number')} references unknown character '{cid}'.",
                    })
            for aid in shot.get("asset_refs") or []:
                if aid not in assets:
                    findings.append({
                        "code": "UNRESOLVED_ASSET_REF",
                        "severity": "BLOCKING",
                        "shot_id": shot["id"],
                        "message": f"Shot {shot.get('shot_number')} references unknown asset/requirement '{aid}'.",
                    })
            if prev is not None:
                prev_loc = str(prev.get("location_ref") or "")
                curr_loc = str(shot.get("location_ref") or "")
                if prev_loc and curr_loc and prev_loc != curr_loc:
                    findings.append({
                        "code": "CONTINUITY_LOCATION_BREAK",
                        "severity": "BLOCKING",
                        "shot_id": shot["id"],
                        "message": (
                            f"Consecutive shots {prev.get('shot_number')}->{shot.get('shot_number')} "
                            f"change location '{prev_loc}' -> '{curr_loc}' inside one scene."
                        ),
                    })
            prev = shot

    for shot in shots:
        sid = str(shot.get("scene_id") or "")
        if sid and sid not in scene_ids:
            findings.append({
                "code": "ORPHAN_SHOT",
                "severity": "BLOCKING",
                "shot_id": shot["id"],
                "message": f"Shot {shot.get('shot_number')} points at missing scene '{sid}'.",
            })

    scene_total = sum(int(s.get("duration_seconds", 0)) for s in scenes)
    ep = await service.get(NS_EPISODES, episode_id)
    target_duration = ((ep or {}).get("metadata") or {}).get("target_duration_seconds")
    if target_duration is None:
        if scenes:
            findings.append({
                "code": "EPISODE_DURATION_TARGET_ABSENT",
                "severity": "WARNING",
                "message": "Episode has no metadata.target_duration_seconds; only per-scene timing was validated.",
            })
    else:
        tolerance = max(DURATION_TOLERANCE_MIN_SECONDS, int(int(target_duration) * DURATION_TOLERANCE_FRACTION))
        if abs(scene_total - int(target_duration)) > tolerance:
            findings.append({
                "code": "EPISODE_DURATION_MISMATCH",
                "severity": "WARNING",
                "message": (
                    f"Scenes sum to {scene_total}s vs episode target {int(target_duration)}s "
                    f"(tolerance ±{tolerance}s)."
                ),
            })

    blocking = [f for f in findings if f["severity"] == "BLOCKING"]
    return {
        "status": "INVALID" if blocking else "VALID",
        "findings": findings,
        "totals": {
            "scenes": len(scenes),
            "shots": len(shots),
            "planned_shot_seconds": planned_total,
            "scene_seconds": scene_total,
            "episode_target_seconds": int(target_duration) if target_duration is not None else None,
        },
    }


@router.get("/episodes/{episode_id}/production/shot-plan/validation", operation_id="production.validateShotPlan")
async def validate_shot_plan_endpoint(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Read-only structural validation of the episode's shots (no mutation)."""
    return await validate_episode_shots(service, episode_id)


@router.get("/episodes/{episode_id}/production/shot-plan", operation_id="production.getShotPlan")
async def get_shot_plan(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Retrieve the shot plan state for an episode.

    P1 truth rule: GET never creates the plan. Absent plan => 404
    SHOT_PLAN_NOT_CREATED.
    """
    plan = await _get_shot_plan(service, episode_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SHOT_PLAN_NOT_CREATED",
                "message": (
                    f"No shot plan initialized for episode '{episode_id}'. "
                    "Generate one via POST .../production/shot-plan/actions/generate."
                ),
            },
        )
    shots = sorted(
        (s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("shot_number", 0),
    )
    validation = await validate_episode_shots(service, episode_id)
    return {
        **plan,
        "shots": [_shot_to_resource(s).model_dump() for s in shots],
        "validation": validation,
    }


@router.post("/episodes/{episode_id}/production/shot-plan/actions/generate", operation_id="production.generateShotPlan")
async def generate_shot_plan(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Deterministically project shots for scenes that have none (P1.5.1).

    Rule-based — no LLM. Scenes with existing shots are left untouched, so
    re-runs are idempotent backfill. Fails closed when no storyboard exists.
    """
    sb = await service.get(NS_STORYBOARDS, episode_id)
    if sb is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "STORYBOARD_NOT_SYNCED",
                "message": (
                    f"Episode '{episode_id}' has no synced storyboard; "
                    "run POST /episodes/{episode_id}/storyboard/actions/sync first."
                ),
            },
        )
    await _assert_shot_plan_not_pinned(service, episode_id)

    plan = await _get_shot_plan(service, episode_id)
    now = utc_now().isoformat()
    if plan is None:
        plan = {
            "id": f"sp-{episode_id}",
            "episode_id": episode_id,
            "status": "DRAFT",
            "current_revision_id": None,
            "created_at": now,
            "updated_at": now,
        }
        plan = await service.create(NS_SHOT_PLANS, episode_id, plan)

    scenes = sorted(
        (s for s in await service.list(NS_SCENES) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("scene_number", 0),
    )
    shots = [s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id]
    existing_by_scene: Dict[str, List[Dict[str, Any]]] = {}
    for s in shots:
        existing_by_scene.setdefault(str(s.get("scene_id") or ""), []).append(s)

    created = await _generate_shots_for_scenes(
        service, scenes, existing_by_scene, episode_id, plan["id"], now
    )

    updates = dict(plan)
    updates["updated_at"] = now
    await service.update(NS_SHOT_PLANS, episode_id, updates, plan.get("version", 1))

    validation = await validate_episode_shots(service, episode_id)
    return {
        "episode_id": episode_id,
        "generated_count": len(created),
        "validation": validation,
    }


@router.post("/episodes/{episode_id}/production/shot-plan/actions/pin", operation_id="production.pinShotPlan")
async def pin_shot_plan(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Pin the current shot ordering as an immutable revision (P1.5.5).

    A pinned plan snapshots every shot with a deterministic content hash.
    While pinned, all shot mutations fail closed; derive a new draft revision
    to keep editing.
    """
    shots = sorted(
        (s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("shot_number", 0),
    )
    if not shots:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SHOT_PLAN_EMPTY",
                "message": f"Episode '{episode_id}' has no shots to pin.",
            },
        )

    plan = await _get_shot_plan(service, episode_id)
    now = utc_now().isoformat()
    if plan is None:
        plan = {
            "id": f"sp-{episode_id}",
            "episode_id": episode_id,
            "status": "DRAFT",
            "current_revision_id": None,
            "created_at": now,
            "updated_at": now,
        }
        plan = await service.create(NS_SHOT_PLANS, episode_id, plan)

    revisions = [
        r for r in await service.list(NS_SHOT_PLAN_REVISIONS)
        if r.get("episode_id") == episode_id
    ]
    next_number = max((int(r.get("revision_number", 0)) for r in revisions), default=0) + 1
    revision_id = f"sprev-{episode_id}-v{next_number}"

    snapshot = [_snapshot_shot(s) for s in shots]
    content_hash = compute_content_hash(snapshot)
    await service.create(NS_SHOT_PLAN_REVISIONS, revision_id, {
        "revision_id": revision_id,
        "episode_id": episode_id,
        "revision_number": next_number,
        "origin": "PIN",
        "content_hash": content_hash,
        "shots_snapshot": snapshot,
        "created_at": now,
    })

    updates = dict(plan)
    updates["status"] = "PINNED"
    updates["current_revision_id"] = revision_id
    updates["content_hash"] = content_hash
    updates["updated_at"] = now
    await service.update(NS_SHOT_PLANS, episode_id, updates, plan.get("version", 1))

    return {
        "episode_id": episode_id,
        "status": "PINNED",
        "current_revision_id": revision_id,
        "content_hash": content_hash,
        "shot_count": len(snapshot),
    }


@router.post("/episodes/{episode_id}/production/shot-plan/actions/derive", operation_id="production.deriveShotPlan")
async def derive_shot_plan(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Derive a fresh DRAFT revision from the pinned snapshot (P1.5.5).

    The pinned revision stays immutable for the production package; live shot
    records become editable again from the derived copy.
    """
    plan = await _get_shot_plan(service, episode_id)
    if plan is None or not plan.get("current_revision_id"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SHOT_PLAN_NOT_PINNED",
                "message": f"Episode '{episode_id}' has no pinned shot plan to derive from.",
            },
        )

    rev = await service.get(NS_SHOT_PLAN_REVISIONS, plan["current_revision_id"])
    if rev is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pinned revision '{plan['current_revision_id']}' record is missing.",
        )

    now = utc_now().isoformat()
    # Replace live shots with the pinned snapshot copy.
    old_shots = [s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id]
    id_map: Dict[str, str] = {}
    for s in old_shots:
        id_map[s["id"]] = f"shot-{uuid.uuid4().hex[:8]}"

    await _delete_shots(service, old_shots)

    plan_ref = await service.get(NS_PRODUCTION_PLANS, episode_id)
    plan_id = (plan_ref or {}).get("id", f"plan-{episode_id}")

    created: List[Dict[str, Any]] = []
    for snap in rev.get("shots_snapshot") or []:
        new_id = id_map.get(str(snap.get("id")), f"shot-{uuid.uuid4().hex[:8]}")
        record = dict(snap)
        record["id"] = new_id
        record["episode_id"] = episode_id
        record["production_plan_id"] = plan_id
        record["status"] = "DRAFT"
        record["audio_asset_id"] = None
        record["animation_asset_id"] = None
        record["render_asset_id"] = None
        record["version"] = 1
        record["created_at"] = now
        record["updated_at"] = now
        stored = await service.create(NS_SHOTS, new_id, record)
        created.append(stored)

    revisions = [
        r for r in await service.list(NS_SHOT_PLAN_REVISIONS)
        if r.get("episode_id") == episode_id
    ]
    next_number = max((int(r.get("revision_number", 0)) for r in revisions), default=0) + 1
    derivation_id = f"sprev-{episode_id}-v{next_number}"
    await service.create(NS_SHOT_PLAN_REVISIONS, derivation_id, {
        "revision_id": derivation_id,
        "episode_id": episode_id,
        "revision_number": next_number,
        "origin": "DERIVE",
        "derived_from": rev["revision_id"],
        "content_hash": "",
        "shots_snapshot": [],
        "created_at": now,
    })

    updates = dict(plan)
    updates["status"] = "DRAFT"
    updates["current_revision_id"] = derivation_id
    updates["derived_from_revision_id"] = rev["revision_id"]
    updates["updated_at"] = now
    await service.update(NS_SHOT_PLANS, episode_id, updates, plan.get("version", 1))

    return {
        "episode_id": episode_id,
        "status": "DRAFT",
        "current_revision_id": derivation_id,
        "derived_from": rev["revision_id"],
        "restored_shot_count": len(created),
    }


_SNAPSHOT_FIELDS = (
    "id", "scene_id", "shot_number", "shot_size", "framing", "camera_angle",
    "camera_movement", "focal_length", "duration_seconds",
    "subject_character_refs", "location_ref", "asset_refs", "action",
    "dialogue_ref", "audio_cue", "lighting_intent", "composition_notes",
    "continuity_from", "continuity_to",
)


def _snapshot_shot(s: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a shot into a schema-complete snapshot row.

    Seeded/legacy shots may pre-date the extended production schema; missing
    scalars are filled so a derived draft always satisfies ShotResource.
    """
    out: Dict[str, Any] = {}
    for k in _SNAPSHOT_FIELDS:
        v = s.get(k)
        if k in ("subject_character_refs", "asset_refs"):
            out[k] = list(v or [])
        elif v is None and k not in ("dialogue_ref", "continuity_from", "continuity_to"):
            out[k] = 1 if k == "duration_seconds" else (0 if k == "shot_number" else "")
        else:
            out[k] = v
    return out


async def _delete_shots(service: V3ResourceService, shots: List[Dict[str, Any]]) -> None:
    for s in shots:
        await service.delete(NS_SHOTS, s["id"])


@router.delete("/shots/{shot_id}", response_model=Dict[str, Any], operation_id="production.deleteShot")
async def delete_shot(
    shot_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Delete a DRAFT shot (manual editing, plan P1.5.5)."""
    shot = await service.get(NS_SHOTS, shot_id)
    if shot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    await _assert_shot_plan_not_pinned(service, shot.get("episode_id") or "")
    await service.delete(NS_SHOTS, shot_id)
    return {"deleted": shot_id}


@router.post("/shots/{shot_id}/actions/reorder", response_model=ShotResource, operation_id="production.reorderShot")
async def reorder_shot(
    shot_id: str = Path(...),
    body: ReorderShotRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ShotResource:
    """Server-side reorder command — the frontend never persists order locally."""
    shot = await service.get(NS_SHOTS, shot_id)
    if shot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    episode_id = shot.get("episode_id") or ""
    await _assert_shot_plan_not_pinned(service, episode_id)
    if shot["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for shot '{shot_id}'.",
        )

    shots = sorted(
        (s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("shot_number", 0),
    )
    others = [s for s in shots if s["id"] != shot_id]
    position = min(max(1, body.new_position), len(others) + 1)
    ordered = others[:position - 1] + [shot] + others[position - 1:]

    now = utc_now().isoformat()
    updated = shot
    for index, s in enumerate(ordered, start=1):
        if int(s.get("shot_number", 0)) == index:
            continue
        updates = dict(s)
        updates["shot_number"] = index
        updates["updated_at"] = now
        result = await service.update(NS_SHOTS, s["id"], updates, s.get("version", 1))
        if s["id"] == shot_id and result is not None:
            updated = result
    return _shot_to_resource(updated)


@router.post("/shots/{shot_id}/actions/split", response_model=List[ShotResource], operation_id="production.splitShot")
async def split_shot(
    shot_id: str = Path(...),
    body: SplitShotRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[ShotResource]:
    """Split one shot into two consecutive halves sharing the framing."""
    shot = await service.get(NS_SHOTS, shot_id)
    if shot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot '{shot_id}' not found.")
    episode_id = shot.get("episode_id") or ""
    await _assert_shot_plan_not_pinned(service, episode_id)
    if shot["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for shot '{shot_id}'.")

    total = int(shot.get("duration_seconds", 2))
    first = body.split_seconds if body.split_seconds is not None else total // 2
    if not (1 <= first < total):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "SPLIT_OUT_OF_RANGE",
                "message": f"split_seconds must be within 1..{total - 1}.",
            },
        )

    now = utc_now().isoformat()
    shots = [s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id]
    next_number = max((int(s.get("shot_number", 0)) for s in shots), default=0) + 1

    part_two = dict(shot)
    part_two.pop("version", None)
    part_two.update({
        "id": f"shot-{uuid.uuid4().hex[:8]}",
        "shot_number": next_number,
        "duration_seconds": total - first,
        "continuity_from": shot["id"],
        "continuity_to": shot.get("continuity_to"),
        "created_at": now,
        "updated_at": now,
    })
    await service.create(NS_SHOTS, part_two["id"], part_two)

    updates = dict(shot)
    updates["duration_seconds"] = first
    updates["continuity_to"] = part_two["id"]
    updates["updated_at"] = now
    updated = await service.update(NS_SHOTS, shot_id, updates, body.expected_version)
    return [_shot_to_resource(updated or updates), _shot_to_resource(part_two)]


@router.post("/episodes/{episode_id}/shots/actions/merge", response_model=ShotResource, operation_id="production.mergeShots")
async def merge_shots(
    episode_id: str = Path(...),
    body: MergeShotsRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ShotResource:
    """Merge two CONSECUTIVE shots of the same scene into one."""
    await _assert_shot_plan_not_pinned(service, episode_id)
    shots = {
        s["id"]: s
        for s in await service.list(NS_SHOTS)
        if s.get("episode_id") == episode_id
    }
    missing = [sid for sid in body.shot_ids if sid not in shots]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shot(s) '{', '.join(missing)}' not found.")

    pair = [shots[sid] for sid in body.shot_ids]
    pair.sort(key=lambda s: s.get("shot_number", 0))
    first, second = pair[0], pair[1]
    if str(first.get("scene_id") or "") != str(second.get("scene_id") or ""):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "MERGE_ACROSS_SCENES", "message": "Merged shots must belong to the same scene."},
        )
    if second.get("shot_number") != first.get("shot_number", 0) + 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "MERGE_NON_CONSECUTIVE", "message": "Merged shots must be consecutive."},
        )
    for s in pair:
        if s["version"] != body.expected_versions.get(s["id"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for shot '{s['id']}'.")

    now = utc_now().isoformat()
    merged_updates = dict(first)
    merged_updates["duration_seconds"] = (
        int(first.get("duration_seconds", 0)) + int(second.get("duration_seconds", 0))
    )
    merged_updates["action"] = " ".join(
        p for p in (str(first.get("action") or ""), str(second.get("action") or "")) if p
    )
    merged_updates["continuity_to"] = second.get("continuity_to")
    merged_updates["updated_at"] = now
    merged = await service.update(NS_SHOTS, first["id"], merged_updates, first["version"])

    await service.delete(NS_SHOTS, second["id"])
    return _shot_to_resource(merged or merged_updates)


# ─────────────────────────────────────────────────────────────────────────────
# P1.6 — Production Package: preflight validation + immutable handoff
# ─────────────────────────────────────────────────────────────────────────────

NS_PRODUCTION_PACKAGES = "production_packages"
NS_LOCATIONS = "locations"
PACKAGE_SCHEMA = "windagent.production_package.v1"
PRODUCTION_TARGETS = ("BLENDER", "UNREAL", "GENERIC_3D")


class FinalizePackageRequest(BaseModel):
    production_target: str = Field(
        "GENERIC_3D",
        description="Target engine label stored on the package. P1 never executes the engine.",
    )


def _referenced_character_ids(
    scenes: List[Dict[str, Any]], shots: List[Dict[str, Any]]
) -> List[str]:
    refs: set = set()
    for s in scenes:
        refs |= set(s.get("character_ids") or [])
    for s in shots:
        refs |= set(s.get("subject_character_refs") or [])
    return sorted(refs)


def _episode_requirement(req: Dict[str, Any], episode_id: str) -> bool:
    if str(req.get("episode_id") or "") == episode_id:
        return True
    # Older requirement rows may only carry scene_usage scene numbers.
    return False


async def build_production_preflight(
    service: V3ResourceService, episode_id: str
) -> Dict[str, Any]:
    """Read-only preflight validator (plan §P1.6.3).

    Returns READY/BLOCKED with blocking_findings[] and warnings[]. A GET never
    mutates state and never fabricates readiness.
    """
    blocking: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    def block(code: str, message: str, **extra: Any) -> None:
        finding = {"code": code, "severity": "BLOCKING", "message": message}
        finding.update(extra)
        blocking.append(finding)

    def warn(code: str, message: str, **extra: Any) -> None:
        finding = {"code": code, "severity": "WARNING", "message": message}
        finding.update(extra)
        warnings.append(finding)

    checks: Dict[str, Any] = {}

    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    # ── Locked screenplay ────────────────────────────────────────────────────
    lock_ref = None
    try:
        lock_ref = await resolve_locked_screenplay(service, episode_id)
    except PreproductionAuthorityError as exc:
        block("SCREENPLAY_NOT_LOCKED", str(exc))
    checks["screenplay_locked"] = lock_ref is not None

    # ── Storyboard sync + lineage + drift ────────────────────────────────────
    board = await service.get(NS_STORYBOARDS, episode_id)
    board_rev: Optional[Dict[str, Any]] = None
    if board is None:
        block(
            "STORYBOARD_NOT_SYNCED",
            f"Episode '{episode_id}' has no synced storyboard.",
        )
        checks["storyboard_synced"] = False
        checks["storyboard_lineage_matches_lock"] = False
        checks["storyboard_hash_current"] = False
    else:
        checks["storyboard_synced"] = True
        lineage_ok = True
        if lock_ref is not None and str(board.get("source_screenplay_revision_id") or "") != lock_ref.revision_id:
            lineage_ok = False
            block(
                "PREPRODUCTION_LINEAGE_MISMATCH",
                (
                    f"Storyboard pins screenplay '{board.get('source_screenplay_revision_id')}' "
                    f"but the episode lock pins '{lock_ref.revision_id}'."
                ),
                storyboard_revision=board.get("source_screenplay_revision_id"),
                locked_revision=lock_ref.revision_id,
            )
        checks["storyboard_lineage_matches_lock"] = lineage_ok

        rev_id = str(board.get("current_revision_id") or "")
        board_rev = await service.get(NS_STORYBOARD_REVISIONS, rev_id) if rev_id else None
        if board_rev is None or not board_rev.get("content_hash"):
            checks["storyboard_hash_current"] = False
            block("STORYBOARD_REVISION_HASH_MISSING", "Storyboard revision has no content hash.")
        else:
            current_scenes = [
                s for s in await service.list(NS_SCENES) if s.get("episode_id") == episode_id
            ]
            recomputed = _compute_storyboard_revision_hash(board_rev, current_scenes)
            drift = recomputed != board_rev["content_hash"]
            checks["storyboard_hash_current"] = not drift
            if drift:
                block(
                    "STORYBOARD_REVISION_DRIFT",
                    "Scenes changed after the last storyboard revision stamp.",
                )

    scenes = sorted(
        (s for s in await service.list(NS_SCENES) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("scene_number", 0),
    )
    shots = sorted(
        (s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("shot_number", 0),
    )
    if not scenes:
        block("STORYBOARD_EMPTY", f"Episode '{episode_id}' has no scene records.")

    for scene in scenes:
        loc_id = str(scene.get("location_id") or "")
        if not loc_id:
            warn(
                "LOCATION_UNRESOLVED",
                f"Scene {scene.get('scene_number')} has no canonical location_id.",
                scene_id=scene["id"],
            )
        elif await service.get(NS_LOCATIONS, loc_id) is None:
            block(
                "LOCATION_UNRESOLVED",
                f"Scene {scene.get('scene_number')} references unknown location '{loc_id}'.",
                scene_id=scene["id"],
                location_id=loc_id,
            )

    # ── Shot plan pinned + structurally valid ────────────────────────────────
    plan = await _get_shot_plan(service, episode_id)
    pinned = plan is not None and str(plan.get("status")) == "PINNED"
    checks["shot_plan_pinned"] = pinned
    if not pinned:
        block(
            "SHOT_PLAN_NOT_PINNED",
            f"Episode '{episode_id}' has no pinned shot plan.",
        )

    validation = await validate_episode_shots(service, episode_id)
    shot_blockers = [f for f in validation.get("findings", []) if f["severity"] == "BLOCKING"]
    checks["shots_valid"] = not shot_blockers
    if shot_blockers:
        block(
            "SHOT_PLAN_INVALID",
            f"{len(shot_blockers)} structural shot finding(s).",
            findings=shot_blockers,
        )
    for finding in validation.get("findings", []):
        if finding["severity"] == "WARNING":
            warn(finding["code"], finding["message"])

    # ── Character canon readiness ────────────────────────────────────────────
    characters_by_id = {c["id"]: c for c in await service.list(NS_CHARACTERS)}
    referenced_ids = _referenced_character_ids(scenes, shots)
    unresolved = [cid for cid in referenced_ids if cid not in characters_by_id]
    not_ready = [
        {"character_id": cid, "status": str(characters_by_id[cid].get("status") or "")}
        for cid in referenced_ids
        if cid in characters_by_id
        and str(characters_by_id[cid].get("status") or "") != CHARACTER_STATUS_PRODUCTION_READY
    ]
    checks["characters_production_ready"] = not unresolved and not not_ready
    for cid in unresolved:
        block(
            "UNRESOLVED_CHARACTER_REF",
            f"Episode references unknown character '{cid}'.",
            character_id=cid,
        )
    if not_ready:
        block(
            "CHARACTERS_NOT_PRODUCTION_READY",
            "Referenced characters have not reached PRODUCTION_READY.",
            characters=not_ready,
        )

    # ── Mandatory assets resolved to PINNED assets ──────────────────────────
    requirements = [
        r for r in await service.list(NS_ASSET_REQUIREMENTS)
        if _episode_requirement(r, episode_id)
    ]
    mandatory_missing: List[Dict[str, Any]] = []
    assets_not_pinned: List[Dict[str, Any]] = []
    pinned_assets: List[Dict[str, Any]] = []
    for req in requirements:
        if not req.get("mandatory"):
            continue
        if str(req.get("status") or "") != "FULFILLED" or not req.get("linked_asset_id"):
            mandatory_missing.append({
                "requirement_id": req.get("requirement_id"),
                "name": req.get("name"),
            })
            continue
        asset = await service.get(NS_ASSETS, str(req["linked_asset_id"]))
        pin = (asset or {}).get("approval_pin") or {}
        if (
            asset is None
            or str(asset.get("status") or "") != ASSET_STATUS_PINNED
            or not pin.get("revision_id")
            or not pin.get("content_hash")
        ):
            assets_not_pinned.append({
                "requirement_id": req.get("requirement_id"),
                "asset_id": req.get("linked_asset_id"),
            })
        else:
            pinned_assets.append({
                "asset_id": asset["id"],
                "revision_id": pin["revision_id"],
                "content_hash": pin["content_hash"],
            })
    checks["mandatory_assets_resolved"] = not mandatory_missing and not assets_not_pinned
    if mandatory_missing:
        block(
            "MANDATORY_ASSET_MISSING",
            f"{len(mandatory_missing)} mandatory requirement(s) unfulfilled.",
            requirements=mandatory_missing,
        )
    if assets_not_pinned:
        block(
            "ASSET_NOT_PINNED",
            "Fulfilled mandatory assets are missing a verified approval pin.",
            assets=assets_not_pinned,
        )

    # ── World canon present ──────────────────────────────────────────────────
    world = await service.get(NS_WORLD_BIBLES, str(ep.get("project_id") or ""))
    checks["world_canon_present"] = world is not None
    if world is None:
        block("WORLD_BIBLE_MISSING", "The episode's project has no world bible.")
    elif not world.get("content_hash"):
        warn(
            "WORLD_CANON_HASH_ABSENT",
            "World bible has no stamped content hash; run a world sync first.",
        )

    status_value = "READY" if not blocking else "BLOCKED"
    return {
        "episode_id": episode_id,
        "status": status_value,
        "blocking_findings": blocking,
        "warnings": warnings,
        "checks": checks,
    }


@router.get("/episodes/{episode_id}/production/package/preflight", operation_id="production.preflightPackage")
async def preflight_package_endpoint(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Read-only production package preflight (plan §P1.6.3). Never mutates."""
    if await service.get(NS_EPISODES, episode_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")
    return await build_production_preflight(service, episode_id)


def _build_package_manifest(
    *,
    lock_ref: LockedScreenplayRef,
    ep: Dict[str, Any],
    world: Dict[str, Any],
    board: Dict[str, Any],
    board_rev: Dict[str, Any],
    scenes: List[Dict[str, Any]],
    plan: Dict[str, Any],
    characters: List[Dict[str, Any]],
    character_refs: List[str],
    pinned_assets: List[Dict[str, Any]],
    locations: List[Dict[str, Any]],
    validation_totals: Dict[str, Any],
    production_target: str,
) -> Dict[str, Any]:
    """Assemble the canonical ProductionPackage manifest (plan §P1.6.1).

    The hash covers EVERYTHING except package_id/package_hash/created_at so
    identical content deterministically re-addresses the same package.
    """
    character_rows = []
    by_id = {c["id"]: c for c in characters}
    for cid in character_refs:
        c = by_id.get(cid)
        if c is not None:
            character_rows.append({
                "character_id": cid,
                "version": int(c.get("version", 1)),
                "hash": str(c.get("content_hash") or ""),
            })

    manifest: Dict[str, Any] = {
        "schema": PACKAGE_SCHEMA,
        "episode": {
            "episode_id": ep["id"],
            "project_id": ep.get("project_id"),
            "title": ep.get("title"),
            "state": ep.get("state"),
        },
        "locked_screenplay": {
            "revision_id": lock_ref.revision_id,
            "artifact_id": lock_ref.artifact_id,
            "content_hash": lock_ref.content_hash,
        },
        "character_canon": character_rows,
        "world_canon": {
            "project_id": (world or {}).get("project_id"),
            "current_revision_id": (world or {}).get("current_revision_id", ""),
            "content_hash": (world or {}).get("content_hash", ""),
            "version": (world or {}).get("version", 1),
        },
        "locations": locations,
        "assets": pinned_assets,
        "storyboard": {
            "revision_id": board.get("current_revision_id"),
            "source_screenplay_revision_id": board.get("source_screenplay_revision_id"),
            "hash": (board_rev or {}).get("content_hash", ""),
        },
        "scenes": [
            {
                "scene_id": s["id"],
                "scene_number": s.get("scene_number"),
                "title": s.get("title"),
                "duration_seconds": s.get("duration_seconds"),
                "location_id": s.get("location_id"),
                "source_screenplay_scene_hash": s.get("source_screenplay_scene_hash"),
            }
            for s in scenes
        ],
        "shot_plan": {
            "revision_id": plan.get("current_revision_id"),
            "hash": plan.get("content_hash", ""),
            "shot_count": validation_totals.get("shots", 0),
        },
        "constraints": {
            "duration_tolerance_fraction": DURATION_TOLERANCE_FRACTION,
            "duration_tolerance_min_seconds": DURATION_TOLERANCE_MIN_SECONDS,
            **validation_totals,
        },
        "production_target": production_target,
    }
    package_hash = compute_content_hash(manifest)
    manifest["package_hash"] = package_hash
    manifest["package_id"] = f"pkg-{package_hash[:12]}"
    return manifest


@router.post("/episodes/{episode_id}/production/package/actions/finalize", operation_id="production.finalizePackage")
async def finalize_package(
    episode_id: str = Path(...),
    body: FinalizePackageRequest = ...,
    response: Response = None,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Freeze the pre-production state into an immutable Production Package.

    Fails closed with every blocking finding when preflight is BLOCKED.
    Content-addressed idempotency: finalizing unchanged content returns the
    SAME package (HTTP 200); changed content yields a NEW immutable package.
    """
    if body.production_target not in PRODUCTION_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_PRODUCTION_TARGET",
                "message": f"production_target must be one of {', '.join(PRODUCTION_TARGETS)}.",
            },
        )
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Episode '{episode_id}' not found.")

    preflight = await build_production_preflight(service, episode_id)
    if preflight["status"] != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "PREPRODUCTION_NOT_READY",
                "message": "Preflight blocked package finalization.",
                "blocking_findings": preflight["blocking_findings"],
                "warnings": preflight["warnings"],
            },
        )

    lock_ref = await resolve_locked_screenplay(service, episode_id)
    world = await service.get(NS_WORLD_BIBLES, str(ep.get("project_id") or ""))
    board = await service.get(NS_STORYBOARDS, episode_id)
    board_rev = await service.get(NS_STORYBOARD_REVISIONS, board["current_revision_id"])
    scenes = sorted(
        (s for s in await service.list(NS_SCENES) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("scene_number", 0),
    )
    shots = sorted(
        (s for s in await service.list(NS_SHOTS) if s.get("episode_id") == episode_id),
        key=lambda s: s.get("shot_number", 0),
    )
    plan = (await _get_shot_plan(service, episode_id)) or {}
    all_characters = await service.list(NS_CHARACTERS)
    referenced = _referenced_character_ids(scenes, shots)

    # Locations actually used by the package's scenes (resolved during preflight).
    location_ids: List[str] = []
    for s in scenes:
        loc_id = str(s.get("location_id") or "")
        if loc_id and loc_id not in location_ids:
            location_ids.append(loc_id)
    locations: List[Dict[str, Any]] = []
    for loc_id in location_ids:
        loc = await service.get(NS_LOCATIONS, loc_id)
        if loc is not None:
            locations.append({
                "location_id": loc_id,
                "name": loc.get("name"),
                "type": loc.get("type"),
            })

    # Mandatory fulfilled+PINNED assets (already validated by preflight).
    pinned_assets: List[Dict[str, Any]] = []
    requirements = [
        r for r in await service.list(NS_ASSET_REQUIREMENTS)
        if _episode_requirement(r, episode_id) and r.get("mandatory")
    ]
    for req in requirements:
        if str(req.get("status") or "") != "FULFILLED" or not req.get("linked_asset_id"):
            continue
        if str(req.get("status") or "") != "FULFILLED" or not req.get("linked_asset_id"):
            continue
        asset = await service.get(NS_ASSETS, str(req["linked_asset_id"])) or {}
        pin = asset.get("approval_pin") or {}
        pinned_assets.append({
            "asset_id": asset.get("id"),
            "revision_id": pin.get("revision_id"),
            "content_hash": pin.get("content_hash"),
        })

    manifest = _build_package_manifest(
        lock_ref=lock_ref,
        ep=ep,
        world=world,
        board=board,
        board_rev=board_rev,
        scenes=scenes,
        plan=plan,
        characters=all_characters,
        character_refs=referenced,
        pinned_assets=pinned_assets,
        locations=locations,
        validation_totals=(await validate_episode_shots(service, episode_id))["totals"],
        production_target=body.production_target,
    )

    existing = await service.get(NS_PRODUCTION_PACKAGES, manifest["package_id"])
    if existing is not None:
        if response is not None:
            response.status_code = status.HTTP_200_OK
        return {"package": existing, "reused": True}

    now = utc_now().isoformat()
    record = {
        **manifest,
        "episode_id": episode_id,
        "status": "FINALIZED",
        "created_at": now,
    }
    created = await service.create(NS_PRODUCTION_PACKAGES, manifest["package_id"], record)
    if response is not None:
        response.status_code = status.HTTP_201_CREATED
    return {"package": created, "reused": False}


@router.get("/episodes/{episode_id}/production/packages", operation_id="production.listPackages")
async def list_packages(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[Dict[str, Any]]:
    """Finalized packages for an episode, newest first."""
    packages = [
        p for p in await service.list(NS_PRODUCTION_PACKAGES)
        if p.get("episode_id") == episode_id
    ]
    packages.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return packages


@router.get("/production/packages/{package_id}", operation_id="production.getPackage")
async def get_package(
    package_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Fetch one finalized package by its content-addressed id."""
    package = await service.get(NS_PRODUCTION_PACKAGES, package_id)
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "PACKAGE_NOT_FOUND", "message": f"No package '{package_id}'."},
        )
    return package


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
