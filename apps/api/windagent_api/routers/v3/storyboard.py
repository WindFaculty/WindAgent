"""
V3 Storyboard Router — Canonical Storyboard + Scene Generation Authority.
Provides storyboard sync from locked screenplay revision and real generation job tracking.
No fake setTimeout timers. All generation returns a server-issued job ID.

Phase 4: storyboards, scenes, and generation jobs are persisted through the
namespaced durable V3 resource authority. No module-level RAM stores.

P1.0 truth repair: storyboard sync reads the ACTUAL locked screenplay from
the lock authority (no synthetic ``rev-{episode_id}-lock`` ids) and scenes
carry full ownership lineage (episode/storyboard/revision, local numbering).

P1.4 Storyboard Authority: a deterministic scene parser projects structured
screenplay scenes into Scene Records pinned to their source scene id/hash,
every sync state is an immutable StoryboardRevision (idempotent re-sync on
the same screenplay; new revision branch when the screenplay changes — old
revisions are never overwritten), manual edits keep the original screenplay
lineage intact, and concept image generation fails closed with
IMAGE_GENERATION_UNAVAILABLE instead of fabricating a QUEUED job.
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.preproduction_authority import (
    EpisodeNotFoundError,
    ScreenplayNotLockedError,
    resolve_locked_screenplay,
)
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.character_canon_authority import compute_content_hash
from windagent_api.services.world_canon_authority import (
    SCREENPLAY_DRAFT_KIND,
    norm_location_name,
    parse_scene_heading,
)
from windagent_api.services.v3_demo_seed import (
    NS_STORYBOARDS,
    NS_SCENES,
    NS_GENERATION_JOBS,
)

router = APIRouter(prefix="/api/v3", tags=["Storyboard V3"])
ws_router = APIRouter(prefix="/ws/v3/storyboard", tags=["Storyboard V3 WebSocket"])

NS_STORYBOARD_REVISIONS = "storyboard_revisions"

# Deterministic default before manual shot planning adjusts it (P1.5).
DEFAULT_SCENE_DURATION_SECONDS = 120


class SceneResource(BaseModel):
    id: str
    storyboard_id: str
    episode_id: str
    storyboard_revision_id: Optional[str] = None
    scene_number: int
    title: str
    status: str = "DRAFT"
    script_text: str = ""
    visual_summary: str = ""
    action_summary: str = ""
    mood: str = ""
    time_of_day: Optional[str] = None
    duration_seconds: int = DEFAULT_SCENE_DURATION_SECONDS
    location: str = ""
    location_id: Optional[str] = None
    character_ids: List[str] = Field(default_factory=list)
    dialogue_refs: List[Dict[str, Any]] = Field(default_factory=list)
    required_asset_refs: List[str] = Field(default_factory=list)
    parent_scene_id: Optional[str] = None
    source_screenplay_revision_id: Optional[str] = None
    source_screenplay_scene_id: Optional[str] = None
    source_screenplay_scene_hash: Optional[str] = None
    concept_image_url: Optional[str] = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class StoryboardResource(BaseModel):
    id: str
    episode_id: str
    current_revision_id: Optional[str] = None
    source_screenplay_revision_id: str
    source_screenplay_content_hash: Optional[str] = None
    source_screenplay_artifact_id: Optional[str] = None
    status: str = "DRAFT"
    scenes_count: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class StoryboardRevisionResource(BaseModel):
    revision_id: str
    episode_id: str
    storyboard_id: str
    revision_number: int
    origin: str = "SYNC"
    source_screenplay_revision_id: str
    source_screenplay_content_hash: Optional[str] = None
    content_hash: str = ""
    scene_count: int = 0
    created_at: str = ""


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
    storyboard_id: str = Field(..., min_length=1, description="Owning storyboard (no orphan scenes)")
    title: str = Field(..., min_length=1, max_length=200)
    script_text: str = ""
    visual_summary: str = ""
    action_summary: str = ""
    mood: str = ""
    location: str = ""
    character_ids: List[str] = Field(default_factory=list)
    duration_seconds: int = DEFAULT_SCENE_DURATION_SECONDS
    source_screenplay_revision_id: Optional[str] = Field(
        None,
        description="Must match the storyboard's pinned screenplay revision when provided.",
    )


class UpdateSceneRequest(BaseModel):
    title: Optional[str] = None
    script_text: Optional[str] = None
    visual_summary: Optional[str] = None
    action_summary: Optional[str] = None
    mood: Optional[str] = None
    location: Optional[str] = None
    character_ids: Optional[List[str]] = None
    duration_seconds: Optional[int] = None
    expected_version: int = Field(..., description="Optimistic lock version")


class SplitSceneRequest(BaseModel):
    expected_version: int = Field(..., description="Optimistic lock version of the scene being split")
    split_at_char: Optional[int] = Field(
        None,
        ge=1,
        description="Character offset in script_text where part 2 begins; defaults to the midpoint.",
    )


class TriggerGenerationRequest(BaseModel):
    style_prompt: Optional[str] = Field(None, description="Visual style override")
    reference_character_ids: List[str] = Field(default_factory=list)


def _scene_to_resource(s: Dict[str, Any]) -> SceneResource:
    return SceneResource(**s)


def _scene_script_text(scene: Dict[str, Any]) -> str:
    """Deterministic script text from a structured screenplay scene."""
    parts: List[str] = []
    heading = str(scene.get("heading") or "").strip()
    if heading:
        parts.append(heading)
    action = str(scene.get("action") or "").strip()
    if action:
        parts.append(action)
    for line in scene.get("dialogue") or []:
        speaker = str(line.get("speaker") or "").strip().upper()
        text = str(line.get("text") or "").strip()
        if speaker or text:
            parts.append(f"{speaker}: {text}".strip())
    return "\n".join(parts)


async def _resolve_scene_references(
    service: V3ResourceService,
    project_id: Optional[str],
    parsed_location_name: Optional[str],
    speakers: List[str],
    scene_number: Any,
    requirements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve Location Canon / Character Canon / requirement ids for a scene.

    Only REAL canon matches produce ids — unmatched names stay unresolved
    (never fabricated).
    """
    location_id: Optional[str] = None
    if project_id and parsed_location_name:
        locations = [
            loc for loc in await service.list("locations")
            if loc.get("project_id") == project_id
        ]
        key = norm_location_name(parsed_location_name)
        location_id = next(
            (loc["id"] for loc in locations if norm_location_name(loc.get("name")) == key),
            None,
        )

    character_ids: List[str] = []
    if project_id and speakers:
        characters = [
            c for c in await service.list("characters")
            if c.get("project_id") == project_id
        ]
        by_name = {
            norm_location_name(c.get("identity", {}).get("name")): c["id"]
            for c in characters
        }
        seen = set()
        for speaker in speakers:
            cid = by_name.get(norm_location_name(speaker))
            if cid and cid not in seen:
                seen.add(cid)
                character_ids.append(cid)

    required_asset_refs: List[str] = []
    for req in requirements:
        usage = [str(u) for u in req.get("scene_usage") or []]
        if str(scene_number) not in usage:
            continue
        name_matches = (
            (parsed_location_name and norm_location_name(req.get("name")) == norm_location_name(parsed_location_name))
            or any(norm_location_name(req.get("name")) == norm_location_name(s) for s in speakers)
        )
        if req.get("type") in ("CHARACTER", "ENVIRONMENT", "PROP") and name_matches:
            required_asset_refs.append(req["requirement_id"])

    return {
        "location_id": location_id,
        "character_ids": character_ids,
        "required_asset_refs": required_asset_refs,
    }


async def _load_pinned_screenplay(
    service: V3ResourceService, episode_id: str, locked_revision_id: str
) -> Optional[Dict[str, Any]]:
    """Load the screenplay draft artifact for the locked revision.

    The artifact whose ``revision_id`` matches the lock authority pin wins.
    Older seeds may lock a bare receipt without a matching draft; in that case
    the latest available draft is the truthful best-effort source — the pin
    itself still comes from the lock authority, never from this artifact.
    """
    artifacts = [
        a for a in await service.list("episode_artifacts")
        if a.get("episode_id") == episode_id and a.get("kind") == SCREENPLAY_DRAFT_KIND
    ]
    if not artifacts:
        return None
    pinned = [a for a in artifacts if str(a.get("revision_id") or "") == str(locked_revision_id)]
    pool = pinned or artifacts
    pool.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
    return pool[0]


def _compute_storyboard_revision_hash(
    revision: Dict[str, Any], scenes: List[Dict[str, Any]]
) -> str:
    """Deterministic content hash over a storyboard revision's scene set."""
    fingerprint = {
        "revision_id": revision.get("revision_id"),
        "revision_number": revision.get("revision_number"),
        "source_screenplay_revision_id": revision.get("source_screenplay_revision_id"),
        "scenes": sorted(
            (
                {
                    "scene_id": s.get("id"),
                    "scene_number": s.get("scene_number"),
                    "title": s.get("title"),
                    "script_text": s.get("script_text"),
                    "duration_seconds": s.get("duration_seconds"),
                    "location": s.get("location"),
                    "location_id": s.get("location_id"),
                    "character_ids": sorted(s.get("character_ids") or []),
                    "status": s.get("status"),
                    "parent_scene_id": s.get("parent_scene_id"),
                    "source_screenplay_scene_id": s.get("source_screenplay_scene_id"),
                    "source_screenplay_scene_hash": s.get("source_screenplay_scene_hash"),
                }
                for s in scenes
            ),
            key=lambda f: (f.get("scene_number") or 0, str(f.get("scene_id"))),
        ),
    }
    return compute_content_hash(fingerprint)


async def _stamp_storyboard_revision_hash(
    service: V3ResourceService,
    episode_id: str,
    revision_id: str,
) -> str:
    """Recompute and persist a revision's content hash (truthful snapshot).

    The hash covers EVERY scene record of the episode board at stamp time —
    a content address of the whole board state as of this revision. Package
    preflight later recomputes it to detect silent drift.
    """
    rev = await service.get(NS_STORYBOARD_REVISIONS, revision_id)
    if rev is None:
        return ""
    scenes = [
        s for s in await service.list(NS_SCENES)
        if s.get("episode_id") == episode_id
    ]
    content_hash = _compute_storyboard_revision_hash(rev, scenes)
    updates = dict(rev)
    updates["content_hash"] = content_hash
    updates["scene_count"] = len(scenes)
    await service.update(NS_STORYBOARD_REVISIONS, revision_id, updates, rev.get("version", 1))
    return content_hash


async def _project_scenes_from_screenplay(
    service: V3ResourceService,
    episode_id: str,
    sb: Dict[str, Any],
    sbrev_id: str,
    locked_revision_id: str,
    created_at: str,
) -> List[Dict[str, Any]]:
    """Deterministically create missing Scene Records from the locked screenplay.

    Idempotency is keyed on ``(source_screenplay_revision_id,
    source_screenplay_scene_id)`` across the WHOLE board — not per storyboard
    revision — so back-filling after a MANUAL_EDIT revision bump can never
    duplicate the projected scene set. Scenes already projected stay untouched.
    """
    screenplay = await _load_pinned_screenplay(service, episode_id, locked_revision_id)
    raw_scenes = ((screenplay or {}).get("content") or {}).get("scenes") or []

    project_id = sb.get("project_id") or ""
    ep = await service.get("episodes", episode_id)
    project_id = project_id or (ep or {}).get("project_id") or ""

    existing_scenes = [
        s for s in await service.list(NS_SCENES)
        if s.get("storyboard_id") == sb["id"]
        and str(s.get("source_screenplay_revision_id") or "") == str(locked_revision_id)
    ]
    existing_keys = {str(s.get("source_screenplay_scene_id")) for s in existing_scenes}

    # Requirements resolved once per sync (P1.3 registry feeds scene refs).
    requirements = [
        r for r in await service.list("asset_requirements")
        if r.get("episode_id") == episode_id
    ]

    created: List[Dict[str, Any]] = []
    board_scenes = [
        s for s in await service.list(NS_SCENES)
        if s.get("storyboard_id") == sb["id"]
    ]
    next_number = max((int(s.get("scene_number", 0)) for s in board_scenes), default=0)

    for raw in raw_scenes:
        source_scene_id = str(raw.get("scene_number") if raw.get("scene_number") is not None else raw.get("id") or "")
        if not source_scene_id or source_scene_id in existing_keys:
            continue

        parsed = parse_scene_heading(raw.get("heading"))
        location_name = parsed["location_name"] if parsed else ""
        speakers = [str(line.get("speaker") or "") for line in raw.get("dialogue") or []]
        refs = await _resolve_scene_references(
            service, project_id, location_name, speakers, source_scene_id, requirements
        )

        next_number += 1
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
        scene_hash = compute_content_hash(raw)
        record: Dict[str, Any] = {
            "id": scene_id,
            "storyboard_id": sb["id"],
            "episode_id": episode_id,
            "storyboard_revision_id": sbrev_id,
            "scene_number": next_number,
            "title": str(raw.get("title") or location_name or f"Scene {source_scene_id}"),
            "status": "DRAFT",
            "script_text": _scene_script_text(raw),
            "visual_summary": "",
            "action_summary": str(raw.get("action") or ""),
            "mood": "",
            "time_of_day": parsed["time_of_day"] if parsed else None,
            "duration_seconds": DEFAULT_SCENE_DURATION_SECONDS,
            "location": location_name,
            "location_id": refs["location_id"],
            "character_ids": refs["character_ids"],
            "dialogue_refs": list(raw.get("dialogue") or []),
            "required_asset_refs": refs["required_asset_refs"],
            "parent_scene_id": None,
            "concept_image_url": None,
            "source_screenplay_revision_id": locked_revision_id,
            "source_screenplay_scene_id": source_scene_id,
            "source_screenplay_scene_hash": scene_hash,
            "created_at": created_at,
            "updated_at": created_at,
        }
        stored = await service.create(NS_SCENES, scene_id, record)
        created.append(stored)
    return created


async def _next_storyboard_revision(
    service: V3ResourceService,
    sb: Dict[str, Any],
    locked_revision_id: str,
    locked_content_hash: Optional[str],
    origin: str,
    now: str,
) -> str:
    """Create the next immutable StoryboardRevision and point the board at it."""
    revisions = [
        r for r in await service.list(NS_STORYBOARD_REVISIONS)
        if r.get("episode_id") == sb["episode_id"]
    ]
    next_number = max((int(r.get("revision_number", 0)) for r in revisions), default=0) + 1
    revision_id = f"sbrev-{sb['episode_id']}-v{next_number}"
    await service.create(NS_STORYBOARD_REVISIONS, revision_id, {
        "revision_id": revision_id,
        "episode_id": sb["episode_id"],
        "storyboard_id": sb["id"],
        "revision_number": next_number,
        "origin": origin,
        "source_screenplay_revision_id": locked_revision_id,
        "source_screenplay_content_hash": locked_content_hash,
        "content_hash": "",
        "scene_count": 0,
        "created_at": now,
    })
    updates = dict(sb)
    updates["current_revision_id"] = revision_id
    updates["updated_at"] = now
    await service.update(NS_STORYBOARDS, sb["episode_id"], updates, sb.get("version", 1))
    return revision_id


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
        current_revision_id=sb.get("current_revision_id"),
        source_screenplay_revision_id=sb["source_screenplay_revision_id"],
        source_screenplay_content_hash=sb.get("source_screenplay_content_hash"),
        source_screenplay_artifact_id=sb.get("source_screenplay_artifact_id"),
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
    """Sync the storyboard from the ACTUAL locked screenplay (plan P1.4.4).

    - No lock → fail closed 409 SCREENPLAY_NOT_LOCKED.
    - First sync → Storyboard v1 + immutable StoryboardRevision v1 + Scene
      Records projected deterministically from the structured screenplay.
    - Same screenplay revision again → IDEMPOTENT (missing scenes backfilled,
      nothing duplicated, no new revision).
    - Changed screenplay revision → the old revision remains immutable; a NEW
      storyboard revision branch is created and projected.
    """
    try:
        locked = await resolve_locked_screenplay(service, episode_id)
    except EpisodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc
    except ScreenplayNotLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc

    sb = await service.get(NS_STORYBOARDS, episode_id)
    now = utc_now().isoformat()
    if sb is None:
        sb_data = {
            "id": f"sb-{uuid.uuid4().hex[:8]}",
            "episode_id": episode_id,
            "current_revision_id": None,
            "source_screenplay_revision_id": locked.revision_id,
            "source_screenplay_content_hash": locked.content_hash or None,
            "source_screenplay_artifact_id": locked.artifact_id,
            "status": "SYNCED",
            "created_at": now,
            "updated_at": now,
        }
        sb = await service.create(NS_STORYBOARDS, episode_id, sb_data)
        revision_id = await _next_storyboard_revision(service, sb, locked.revision_id, locked.content_hash, "SYNC", now)
    elif str(sb.get("source_screenplay_revision_id")) != str(locked.revision_id):
        # New screenplay revision → new immutable branch; the old one stands.
        updates = dict(sb)
        updates["source_screenplay_revision_id"] = locked.revision_id
        updates["source_screenplay_content_hash"] = locked.content_hash or None
        updates["source_screenplay_artifact_id"] = locked.artifact_id
        updates["status"] = "SYNCED"
        updates["updated_at"] = now
        sb = await service.update(NS_STORYBOARDS, episode_id, updates, sb.get("version", 1)) or updates
        revision_id = await _next_storyboard_revision(service, sb, locked.revision_id, locked.content_hash, "SYNC", now)
    else:
        # IDEMPOTENT: same pin — only backfill scenes that never landed.
        revision_id = sb.get("current_revision_id")
        if not revision_id:
            revision_id = await _next_storyboard_revision(service, sb, locked.revision_id, locked.content_hash, "SYNC", now)

    await _project_scenes_from_screenplay(service, episode_id, sb, revision_id, locked.revision_id, now)
    await _stamp_storyboard_revision_hash(service, episode_id, revision_id)
    return await get_episode_storyboard(episode_id, service)


@router.get("/episodes/{episode_id}/storyboard/revisions", response_model=List[StoryboardRevisionResource], operation_id="storyboard.listRevisions")
async def list_storyboard_revisions(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[StoryboardRevisionResource]:
    """Immutable storyboard revision history (plan P1.4.3)."""
    sb = await service.get(NS_STORYBOARDS, episode_id)
    if sb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Storyboard for episode '{episode_id}' not found.")
    revisions = [
        r for r in await service.list(NS_STORYBOARD_REVISIONS)
        if r.get("episode_id") == episode_id
    ]
    revisions.sort(key=lambda r: int(r.get("revision_number", 0)))
    return [StoryboardRevisionResource(**r) for r in revisions]


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
    """Create a storyboard scene with full ownership lineage (P1.0 truth repair).

    A scene MUST belong to an existing storyboard (and through it an episode),
    pin the storyboard's actual screenplay revision, and number locally within
    that storyboard. Orphan scenes cannot be created.
    """
    boards = await service.list(NS_STORYBOARDS)
    sb = next(
        (
            b
            for b in boards
            if b.get("id") == body.storyboard_id or b.get("episode_id") == body.storyboard_id
        ),
        None,
    )
    if sb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "STORYBOARD_NOT_FOUND", "message": f"Storyboard '{body.storyboard_id}' not found."},
        )

    board_revision = str(sb.get("source_screenplay_revision_id") or "")
    if body.source_screenplay_revision_id and body.source_screenplay_revision_id != board_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SCREENPLAY_REVISION_MISMATCH",
                "message": (
                    f"Scene revision '{body.source_screenplay_revision_id}' does not match "
                    f"storyboard pin '{board_revision}'."
                ),
            },
        )

    now = utc_now().isoformat()
    scenes = await service.list(NS_SCENES)
    board_scenes = [s for s in scenes if s.get("storyboard_id") == sb["id"]]
    scene_number = max((int(s.get("scene_number", 0)) for s in board_scenes), default=0) + 1

    scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    new_scene = {
        "id": scene_id,
        "storyboard_id": sb["id"],
        "episode_id": sb["episode_id"],
        "storyboard_revision_id": sb.get("current_revision_id"),
        "scene_number": scene_number,
        "title": body.title,
        "status": "DRAFT",
        "script_text": body.script_text,
        "visual_summary": body.visual_summary,
        "action_summary": body.action_summary,
        "mood": body.mood,
        "duration_seconds": body.duration_seconds,
        "location": body.location,
        "character_ids": body.character_ids,
        "dialogue_refs": [],
        "required_asset_refs": [],
        "parent_scene_id": None,
        "concept_image_url": None,
        "source_screenplay_revision_id": board_revision,
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
    """Manual storyboard operation (plan P1.4.6).

    Edits may change presentation fields but NEVER touch the original
    screenplay lineage (source_* columns are immutable here). Every manual
    edit bumps the storyboard's immutable revision (origin MANUAL_EDIT).
    """
    curr = await service.get(NS_SCENES, scene_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for scene '{scene_id}'.")

    updates = dict(curr)
    changed = False
    for field in ("title", "script_text", "visual_summary", "action_summary", "mood", "location"):
        value = getattr(body, field)
        if value is not None and value != curr.get(field):
            updates[field] = value
            changed = True
    if body.character_ids is not None and body.character_ids != curr.get("character_ids"):
        updates["character_ids"] = body.character_ids
        changed = True
    if body.duration_seconds is not None and body.duration_seconds != curr.get("duration_seconds"):
        updates["duration_seconds"] = body.duration_seconds
        changed = True
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_SCENES, scene_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for scene '{scene_id}'.")

    if changed:
        sb = await service.get(NS_STORYBOARDS, updated["episode_id"])
        if sb is not None:
            new_rev = await _next_storyboard_revision(
                service, sb,
                str(sb.get("source_screenplay_revision_id") or ""),
                sb.get("source_screenplay_content_hash"),
                "MANUAL_EDIT",
                updates["updated_at"],
            )
            await _stamp_storyboard_revision_hash(service, updated["episode_id"], new_rev)
    return _scene_to_resource(updated)


@router.post("/storyboard/scenes/{scene_id}/actions/split", response_model=List[SceneResource], operation_id="storyboard.splitScene")
async def split_scene(
    scene_id: str = Path(...),
    body: SplitSceneRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[SceneResource]:
    """Split a scene into two consecutive parts (plan P1.4.6).

    Both parts keep the original screenplay lineage (same source revision,
    scene id and hash); part 2 carries ``parent_scene_id`` pointing at part 1.
    The estimated duration splits evenly as a starting point for manual tuning.
    """
    curr = await service.get(NS_SCENES, scene_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")
    if curr["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for scene '{scene_id}'.")

    text = str(curr.get("script_text") or "")
    if len(text.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "SCENE_NOT_SPLITTABLE", "message": "Scene has no script text to split."},
        )

    split_at = body.split_at_char if body.split_at_char is not None else len(text) // 2
    if split_at <= 0 or split_at >= len(text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "SPLIT_POINT_OUT_OF_RANGE", "message": f"split_at_char must be within 1..{len(text) - 1}."},
        )

    now = utc_now().isoformat()
    scenes = await service.list(NS_SCENES)
    board_scenes = [s for s in scenes if s.get("storyboard_id") == curr.get("storyboard_id")]
    next_number = max((int(s.get("scene_number", 0)) for s in board_scenes), default=0) + 1

    half_duration = max(1, int(curr.get("duration_seconds", DEFAULT_SCENE_DURATION_SECONDS)) // 2)
    part_two_id = f"scene-{uuid.uuid4().hex[:8]}"
    part_two = dict(curr)
    part_two.update({
        "id": part_two_id,
        "scene_number": next_number,
        "title": f"{curr.get('title', 'Scene')} (Part 2)",
        "parent_scene_id": curr["id"],
        "script_text": text[split_at:].lstrip(),
        "duration_seconds": half_duration,
        "status": "DRAFT",
        "concept_image_url": None,
        "created_at": now,
        "updated_at": now,
    })
    part_two.pop("version", None)
    part_two.pop("created_row_id", None)
    await service.create(NS_SCENES, part_two_id, part_two)

    part_one_updates = dict(curr)
    part_one_updates["script_text"] = text[:split_at].rstrip()
    part_one_updates["duration_seconds"] = half_duration
    part_one_updates["updated_at"] = now
    updated_part_one = await service.update(NS_SCENES, scene_id, part_one_updates, body.expected_version)

    # A split is a manual storyboard operation: it bumps an immutable
    # MANUAL_EDIT revision and re-stamps the board snapshot hash (plan P1.4.6).
    sb = await service.get(NS_STORYBOARDS, curr.get("episode_id") or "")
    if sb is not None:
        new_rev = await _next_storyboard_revision(
            service, sb,
            str(sb.get("source_screenplay_revision_id") or ""),
            sb.get("source_screenplay_content_hash"),
            "MANUAL_EDIT",
            now,
        )
        await _stamp_storyboard_revision_hash(service, sb["episode_id"], new_rev)

    return [_scene_to_resource(updated_part_one or part_one_updates), _scene_to_resource(part_two)]


@router.post("/storyboard/scenes/{scene_id}/generations", response_model=GenerationJobResource, status_code=status.HTTP_201_CREATED, operation_id="storyboard.triggerGeneration")
async def trigger_concept_generation(
    scene_id: str = Path(...),
    body: TriggerGenerationRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> GenerationJobResource:
    """Trigger concept art generation for a storyboard scene.

    P1.4.5 truth repair: there is NO wired image-generation provider in P1,
    so this fails closed with 503 IMAGE_GENERATION_UNAVAILABLE instead of
    fabricating a QUEUED job that would sit forever. The UI disables the
    button until a provider exists.
    """
    scene = await service.get(NS_SCENES, scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scene '{scene_id}' not found.")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "IMAGE_GENERATION_UNAVAILABLE",
            "message": (
                "No image-generation provider is configured for pre-production "
                "concept scenes; upload reference assets manually via "
                "POST /api/v3/assets instead."
            ),
        },
    )


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
        payload_scenes = []
        for s in scenes:
            try:
                payload_scenes.append(_scene_to_resource(s).model_dump())
            except Exception:
                continue
        await websocket.send_json({
            "event": "storyboard.snapshot",
            "episode_id": episode_id,
            "scenes": payload_scenes,
            "timestamp": utc_now().isoformat(),
        })
        while True:
            await asyncio.sleep(10.0)
            await websocket.send_json({"event": "heartbeat", "episode_id": episode_id, "timestamp": utc_now().isoformat()})
    except WebSocketDisconnect:
        pass
