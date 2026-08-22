"""
V3 World Bible Router — Canonical World Building for Story Production Domain.
Provides World Bible CRUD and sub-resources: Locations, Factions, Lore.

Phase 4: world bibles, locations, factions, and lore are persisted through
the namespaced durable V3 resource authority. No module-level RAM stores.

P1.2 World Canon: canonical rule fields, location production profiles,
locked-screenplay world sync (proposal-based, never overwriting manual
edits) and a read-only continuity checker.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.preproduction_authority import (
    EpisodeNotFoundError,
    PreproductionAuthorityError,
    ScreenplayNotLockedError,
    resolve_locked_screenplay,
)
from windagent_api.services.v3_demo_seed import (
    NS_WORLD_BIBLES,
    NS_LOCATIONS,
    NS_FACTIONS,
    NS_LORE,
    NS_PROJECTS,
)
from windagent_api.services.world_canon_authority import (
    ACTION_CONFLICT,
    ACTION_NO_CHANGE,
    ACTION_UPDATE_PROPOSED,
    APPLICABLE_ACTIONS,
    build_world_sync_proposal,
    check_continuity,
    compute_content_hash,
    load_latest_artifacts_of_kind,
    location_fingerprint,
)

router = APIRouter(prefix="/api/v3/projects", tags=["World V3"])
sync_router = APIRouter(prefix="/api/v3", tags=["World V3"])

NS_WORLD_REVISIONS = "world_bible_revisions"
NS_WORLD_SYNC = "world_sync_proposals"


class LocationResource(BaseModel):
    id: str
    project_id: str
    name: str
    type: str = "Interior"
    description: str = ""
    atmosphere: str = ""
    # P1.2.2 production profile
    interior: Optional[bool] = None
    exterior: Optional[bool] = None
    day_scene_compatible: bool = True
    night_scene_compatible: bool = True
    architecture: str = ""
    lighting_character: str = ""
    color_palette: List[str] = Field(default_factory=list)
    important_props: List[str] = Field(default_factory=list)
    reusable_set: bool = False
    continuity_notes: str = ""
    content_hash: str = ""
    last_synced_hash: Optional[str] = None
    version: int = 1


class FactionResource(BaseModel):
    id: str
    project_id: str
    name: str
    ideology: str = ""
    influence_level: int = 50
    description: str = ""
    version: int = 1


class LoreEntryResource(BaseModel):
    id: str
    project_id: str
    title: str
    category: str = "History"
    content: str = ""
    version: int = 1


class ContinuityConstraint(BaseModel):
    statement: str = Field(..., min_length=1)
    forbidden_terms: List[str] = Field(default_factory=list)


class WorldBibleResource(BaseModel):
    project_id: str
    world_name: str
    setting_summary: str = ""
    core_theme: str = ""
    rules: List[str] = Field(default_factory=list)
    timeline_era: str = ""
    # P1.2.1 canonical rule categories & visual identity
    physical_rules: List[str] = Field(default_factory=list)
    technology_rules: List[str] = Field(default_factory=list)
    magic_rules: List[str] = Field(default_factory=list)
    social_rules: List[str] = Field(default_factory=list)
    visual_style: str = ""
    environment_style: str = ""
    continuity_constraints: List[Any] = Field(default_factory=list)
    content_hash: str = ""
    current_revision_id: str = ""
    version: int = 1
    locations_count: int = 0
    factions_count: int = 0
    lore_count: int = 0
    updated_at: str = ""


def _rule_categories(body) -> Dict[str, List[str]]:
    return {
        "physical_rules": body.physical_rules or [],
        "technology_rules": body.technology_rules or [],
        "magic_rules": body.magic_rules or [],
        "social_rules": body.social_rules or [],
    }


def _wb_guard_payload(wb: Dict[str, Any]) -> Dict[str, Any]:
    """Guard subset hashed into the world bible content hash."""
    return {
        key: wb.get(key) or []
        for key in (
            "rules",
            "physical_rules",
            "technology_rules",
            "magic_rules",
            "social_rules",
            "continuity_constraints",
        )
    } | {
        "world_name": wb.get("world_name", ""),
        "setting_summary": wb.get("setting_summary", ""),
        "core_theme": wb.get("core_theme", ""),
        "timeline_era": wb.get("timeline_era", ""),
        "visual_style": wb.get("visual_style", ""),
        "environment_style": wb.get("environment_style", ""),
    }


async def _record_world_revision(service: V3ResourceService, wb: Dict[str, Any]) -> Dict[str, Any]:
    revision_id = f"wbrev-{wb['project_id']}-v{wb.get('version', 1)}"
    record = {
        "revision_id": revision_id,
        "project_id": wb["project_id"],
        "world_version": wb.get("version", 1),
        "content_hash": wb.get("content_hash", ""),
        "snapshot": {k: v for k, v in wb.items() if k not in ("locations_count", "factions_count", "lore_count")},
    }
    existing = await service.get(NS_WORLD_REVISIONS, revision_id)
    if existing is None:
        await service.create(NS_WORLD_REVISIONS, revision_id, record)
    else:
        await service.update(NS_WORLD_REVISIONS, revision_id, record, existing.get("version", 1))
    return record


def _apply_wb_fields(target: Dict[str, Any], source: Any) -> None:
    if source.world_name is not None:
        target["world_name"] = source.world_name
    if source.setting_summary is not None:
        target["setting_summary"] = source.setting_summary
    if source.core_theme is not None:
        target["core_theme"] = source.core_theme
    if getattr(source, "rules", None) is not None:
        target["rules"] = source.rules
    if source.timeline_era is not None:
        target["timeline_era"] = source.timeline_era
    for key, value in _rule_categories(source).items():
        target[key] = value
    if source.visual_style is not None:
        target["visual_style"] = source.visual_style
    if source.environment_style is not None:
        target["environment_style"] = source.environment_style
    if source.continuity_constraints is not None:
        target["continuity_constraints"] = [
            c.model_dump() if isinstance(c, ContinuityConstraint) else c
            for c in source.continuity_constraints
        ]


class UpdateWorldBibleRequest(BaseModel):
    world_name: Optional[str] = None
    setting_summary: Optional[str] = None
    core_theme: Optional[str] = None
    rules: Optional[List[str]] = None
    timeline_era: Optional[str] = None
    physical_rules: Optional[List[str]] = None
    technology_rules: Optional[List[str]] = None
    magic_rules: Optional[List[str]] = None
    social_rules: Optional[List[str]] = None
    visual_style: Optional[str] = None
    environment_style: Optional[str] = None
    continuity_constraints: Optional[List[Any]] = None
    expected_version: int = Field(..., description="Optimistic locking version")


class InitializeWorldBibleRequest(UpdateWorldBibleRequest):
    world_name: str = Field(..., min_length=1, max_length=200, description="Explicit canonical world name")
    expected_version: int = Field(default=1, description="Unused on initialize; kept for schema symmetry")


class CreateLocationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = "Interior"
    description: str = ""
    atmosphere: str = ""
    interior: Optional[bool] = None
    exterior: Optional[bool] = None
    day_scene_compatible: bool = True
    night_scene_compatible: bool = True
    architecture: str = ""
    lighting_character: str = ""
    color_palette: List[str] = Field(default_factory=list)
    important_props: List[str] = Field(default_factory=list)
    reusable_set: bool = False
    continuity_notes: str = ""


class UpdateLocationRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    atmosphere: Optional[str] = None
    interior: Optional[bool] = None
    exterior: Optional[bool] = None
    day_scene_compatible: Optional[bool] = None
    night_scene_compatible: Optional[bool] = None
    architecture: Optional[str] = None
    lighting_character: Optional[str] = None
    color_palette: Optional[List[str]] = None
    important_props: Optional[List[str]] = None
    reusable_set: Optional[bool] = None
    continuity_notes: Optional[str] = None
    expected_version: int = Field(..., description="Optimistic locking version")


class CreateFactionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    ideology: str = ""
    influence_level: int = Field(50, ge=0, le=100)
    description: str = ""


class CreateLoreRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = "History"
    content: str = ""


class WorldSyncActionApplyRequest(BaseModel):
    action_index: int = Field(..., ge=0)


def _loc_resource(loc: Dict[str, Any]) -> LocationResource:
    data = dict(loc)
    if data.get("interior") is None:
        t = str(data.get("type") or "").lower()
        if t.startswith("int"):
            data["interior"] = True
        elif t.startswith("ext"):
            data["interior"] = False
    if data.get("exterior") is None and data.get("interior") is not None:
        data["exterior"] = not data["interior"]
    return LocationResource(**data)


@router.get("/{project_id}/world", response_model=WorldBibleResource, operation_id="world.get")
async def get_world_bible(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorldBibleResource:
    """Retrieve the World Bible for a project.

    P1.0 truth repair: GET is read-only. When no World Bible exists the API
    returns 404 WORLD_BIBLE_NOT_INITIALIZED; a read never mutates the domain
    by fabricating an "Untitled World" record.
    """
    wb = await service.get(NS_WORLD_BIBLES, project_id)
    if wb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "WORLD_BIBLE_NOT_INITIALIZED",
                "message": (
                    f"No World Bible initialized for project '{project_id}'. "
                    "Create one explicitly via POST /projects/{project_id}/world/initialize."
                ),
            },
        )

    return await _world_bible_view(project_id, wb, service)


@router.post("/{project_id}/world/initialize", response_model=WorldBibleResource, status_code=status.HTTP_201_CREATED, operation_id="world.initialize")
async def initialize_world_bible(
    project_id: str = Path(...),
    body: InitializeWorldBibleRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorldBibleResource:
    """Explicitly initialize the World Bible for a project (P1.0 truth repair).

    Creation is a command, not a side effect of reads or Canon Sync.
    """
    project = await service.get(NS_PROJECTS, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "PROJECT_NOT_FOUND", "message": f"Project '{project_id}' not found."},
        )

    existing = await service.get(NS_WORLD_BIBLES, project_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "WORLD_BIBLE_ALREADY_INITIALIZED",
                "message": f"World Bible for project '{project_id}' already exists.",
            },
        )

    now = utc_now().isoformat()
    wb: Dict[str, Any] = {
        "project_id": project_id,
        "world_name": "",
        "setting_summary": "",
        "core_theme": "",
        "rules": [],
        "timeline_era": "",
        "visual_style": "",
        "environment_style": "",
        "continuity_constraints": [],
        "updated_at": now,
    }
    _apply_wb_fields(wb, body)
    wb["content_hash"] = compute_content_hash(_wb_guard_payload(wb))
    # The creation itself is version 1; its pinned revision id matches.
    wb["current_revision_id"] = f"wbrev-{project_id}-v{wb.get('version', 1)}"
    created = await service.create(NS_WORLD_BIBLES, project_id, wb)
    await _record_world_revision(service, created)
    return await _world_bible_view(project_id, created, service)


async def _world_bible_view(
    project_id: str,
    wb: dict,
    service: V3ResourceService,
) -> WorldBibleResource:
    locs = await service.list(NS_LOCATIONS)
    locs = [loc for loc in locs if loc.get("project_id") == project_id]
    facs = await service.list(NS_FACTIONS)
    facs = [f for f in facs if f.get("project_id") == project_id]
    lore = await service.list(NS_LORE)
    lore = [entry for entry in lore if entry.get("project_id") == project_id]

    return WorldBibleResource(
        project_id=wb["project_id"],
        world_name=wb.get("world_name", ""),
        setting_summary=wb.get("setting_summary", ""),
        core_theme=wb.get("core_theme", ""),
        rules=wb.get("rules", []),
        timeline_era=wb.get("timeline_era", ""),
        physical_rules=wb.get("physical_rules", []),
        technology_rules=wb.get("technology_rules", []),
        magic_rules=wb.get("magic_rules", []),
        social_rules=wb.get("social_rules", []),
        visual_style=wb.get("visual_style", ""),
        environment_style=wb.get("environment_style", ""),
        continuity_constraints=wb.get("continuity_constraints", []),
        content_hash=wb.get("content_hash", ""),
        current_revision_id=wb.get("current_revision_id", ""),
        version=wb.get("version", 1),
        locations_count=len(locs),
        factions_count=len(facs),
        lore_count=len(lore),
        updated_at=wb.get("updated_at", ""),
    )


@router.patch("/{project_id}/world", response_model=WorldBibleResource, operation_id="world.update")
async def update_world_bible(
    project_id: str = Path(...),
    body: UpdateWorldBibleRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> WorldBibleResource:
    """Update the World Bible with optimistic concurrency check.

    P1.2: every manual edit bumps the version, recomputes the deterministic
    content hash and pins an immutable revision.
    """
    wb = await service.get(NS_WORLD_BIBLES, project_id)
    if wb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"World Bible for project '{project_id}' not found.")

    if wb["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for World Bible. Expected {wb['version']}, got {body.expected_version}.")

    updates = dict(wb)
    _apply_wb_fields(updates, body)
    updates["updated_at"] = utc_now().isoformat()
    updates["content_hash"] = compute_content_hash(_wb_guard_payload(updates))

    updated = await service.update(NS_WORLD_BIBLES, project_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version conflict for World Bible.")
    await _record_world_revision(service, updated)
    return await _world_bible_view(project_id, updated, service)


@router.get("/{project_id}/world/revisions", response_model=List[Dict[str, Any]], operation_id="world.listRevisions")
async def list_world_revisions(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[Dict[str, Any]]:
    """Immutable version history of the World Bible (P1.2 pinning)."""
    wb = await service.get(NS_WORLD_BIBLES, project_id)
    if wb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"World Bible for project '{project_id}' not found.")
    revisions = await service.list(NS_WORLD_REVISIONS)
    own = [r for r in revisions if r.get("project_id") == project_id]
    # NOTE: bare ``version`` is reserved by the durable authority; records
    # store ``world_version``.
    own.sort(key=lambda r: int(r.get("world_version", 0)))
    return own


@router.get("/{project_id}/world/locations", response_model=List[LocationResource], operation_id="world.listLocations")
async def list_locations(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[LocationResource]:
    locs = await service.list(NS_LOCATIONS)
    return [_loc_resource(loc) for loc in locs if loc.get("project_id") == project_id]


@router.post("/{project_id}/world/locations", response_model=LocationResource, status_code=status.HTTP_201_CREATED, operation_id="world.createLocation")
async def create_location(
    project_id: str = Path(...),
    body: CreateLocationRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> LocationResource:
    loc_id = f"loc-{uuid.uuid4().hex[:8]}"
    new_loc: Dict[str, Any] = {
        "id": loc_id,
        "project_id": project_id,
        "name": body.name,
        "type": body.type,
        "description": body.description,
        "atmosphere": body.atmosphere,
        "interior": body.interior,
        "exterior": body.exterior,
        "day_scene_compatible": body.day_scene_compatible,
        "night_scene_compatible": body.night_scene_compatible,
        "architecture": body.architecture,
        "lighting_character": body.lighting_character,
        "color_palette": list(body.color_palette),
        "important_props": list(body.important_props),
        "reusable_set": body.reusable_set,
        "continuity_notes": body.continuity_notes,
        "last_synced_hash": None,
    }
    new_loc["content_hash"] = compute_content_hash(location_fingerprint(new_loc))
    created = await service.create(NS_LOCATIONS, loc_id, new_loc)
    return _loc_resource(created)


@router.patch("/{project_id}/world/locations/{location_id}", response_model=LocationResource, operation_id="world.updateLocation")
async def update_location(
    project_id: str = Path(...),
    location_id: str = Path(...),
    body: UpdateLocationRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> LocationResource:
    """Update the location production profile with optimistic concurrency.

    ``last_synced_hash`` is intentionally left untouched — drift against the
    stored baseline classifies this location as CONFLICT on the next sync.
    """
    loc = await service.get(NS_LOCATIONS, location_id)
    if loc is None or loc.get("project_id") != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "LOCATION_NOT_FOUND", "message": f"Location '{location_id}' not found."},
        )
    if loc["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for location '{location_id}'. Expected {loc['version']}, got {body.expected_version}.",
        )

    updates = dict(loc)
    for field in (
        "name", "type", "description", "atmosphere", "interior", "exterior",
        "day_scene_compatible", "night_scene_compatible", "architecture",
        "lighting_character", "color_palette", "important_props",
        "reusable_set", "continuity_notes",
    ):
        value = getattr(body, field)
        if value is not None:
            updates[field] = list(value) if isinstance(value, list) else value
    updates["updated_at"] = utc_now().isoformat()
    updates["content_hash"] = compute_content_hash(location_fingerprint(updates))

    updated = await service.update(NS_LOCATIONS, location_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for location '{location_id}'.")
    return _loc_resource(updated)


@router.get("/{project_id}/world/factions", response_model=List[FactionResource], operation_id="world.listFactions")
async def list_factions(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[FactionResource]:
    facs = await service.list(NS_FACTIONS)
    return [FactionResource(**f) for f in facs if f.get("project_id") == project_id]


@router.post("/{project_id}/world/factions", response_model=FactionResource, status_code=status.HTTP_201_CREATED, operation_id="world.createFaction")
async def create_faction(
    project_id: str = Path(...),
    body: CreateFactionRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> FactionResource:
    fac_id = f"fac-{uuid.uuid4().hex[:8]}"
    new_fac = {"id": fac_id, "project_id": project_id, "name": body.name, "ideology": body.ideology, "influence_level": body.influence_level, "description": body.description}
    created = await service.create(NS_FACTIONS, fac_id, new_fac)
    return FactionResource(**created)


@router.get("/{project_id}/world/lore", response_model=List[LoreEntryResource], operation_id="world.listLore")
async def list_lore(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[LoreEntryResource]:
    lore = await service.list(NS_LORE)
    return [LoreEntryResource(**entry) for entry in lore if entry.get("project_id") == project_id]


@router.post("/{project_id}/world/lore", response_model=LoreEntryResource, status_code=status.HTTP_201_CREATED, operation_id="world.createLore")
async def create_lore(
    project_id: str = Path(...),
    body: CreateLoreRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> LoreEntryResource:
    lore_id = f"lore-{uuid.uuid4().hex[:8]}"
    new_lore = {"id": lore_id, "project_id": project_id, "title": body.title, "category": body.category, "content": body.content}
    created = await service.create(NS_LORE, lore_id, new_lore)
    return LoreEntryResource(**created)


# ─────────────────────────────────────────────────────────────────────────────
# P1.2.4 World sync + P1.2.5 Continuity checker (episode-scoped)
# ─────────────────────────────────────────────────────────────────────────────


@sync_router.post("/episodes/{episode_id}/world/actions/canon-sync", response_model=Dict[str, Any], operation_id="world.canonSync")
async def world_canon_sync(
    episode_id: str = Path(...),
    project_id: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Propose world canon changes from the episode's locked screenplay.

    Fail closed with 409 SCREENPLAY_NOT_LOCKED when there is no locked
    screenplay. Never mutates canon directly — proposals are applied through
    explicit apply commands.
    """
    ep = await service.get("episodes", episode_id)
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EPISODE_NOT_FOUND", "message": f"Episode '{episode_id}' not found."},
        )
    resolved_project = project_id or ep.get("project_id")
    if not resolved_project:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "PROJECT_UNRESOLVED", "message": "project_id query parameter is required when the episode has no project."},
        )

    proposal_id = f"wsync-{uuid.uuid4().hex[:10]}"
    try:
        proposal, _lineage = await build_world_sync_proposal(
            service,
            resolved_project,
            episode_id,
            proposal_id,
            utc_now().isoformat(),
        )
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": exc.code, "message": exc.message}) from exc
    except ScreenplayNotLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error_code": exc.code, "message": exc.message}) from exc
    except PreproductionAuthorityError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.code, "message": exc.message}) from exc
    return proposal


@sync_router.post("/episodes/{episode_id}/world/actions/continuity-check", response_model=Dict[str, Any], operation_id="world.continuityCheck")
async def world_continuity_check(
    episode_id: str = Path(...),
    project_id: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Read-only continuity check of the locked screenplay vs World Canon.

    Reports UNKNOWN_LOCATION / WORLD_RULE_CONFLICT / TIMELINE_CONFLICT /
    LOCATION_CONTINUITY_CONFLICT findings. Never mutates anything.
    """
    ep = await service.get("episodes", episode_id)
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EPISODE_NOT_FOUND", "message": f"Episode '{episode_id}' not found."},
        )
    resolved_project = project_id or ep.get("project_id")

    try:
        locked = await resolve_locked_screenplay(service, episode_id)
    except EpisodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": exc.code, "message": exc.message}) from exc
    except ScreenplayNotLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error_code": exc.code, "message": exc.message}) from exc

    screenplay = await load_latest_artifacts_of_kind(service, episode_id, "ScreenplayDraft")
    locations = [
        loc for loc in await service.list(NS_LOCATIONS)
        if not resolved_project or loc.get("project_id") == resolved_project
    ]
    world_bible = await service.get(NS_WORLD_BIBLES, resolved_project) if resolved_project else None

    findings = check_continuity(screenplay, world_bible, locations)
    summary: Dict[str, int] = {}
    for finding in findings:
        summary[finding["finding_type"]] = summary.get(finding["finding_type"], 0) + 1

    return {
        "episode_id": episode_id,
        "checked_screenplay_revision_id": locked.revision_id,
        "findings": findings,
        "summary": summary,
        "blocking_count": sum(1 for f in findings if f.get("severity") == "blocking"),
        "checked_at": utc_now().isoformat(),
    }


@sync_router.get("/world-sync/{proposal_id}", response_model=Dict[str, Any], operation_id="world.getWorldSyncProposal")
async def get_world_sync_proposal(
    proposal_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    proposal = await service.get(NS_WORLD_SYNC, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "WORLD_PROPOSAL_NOT_FOUND", "message": f"World sync proposal '{proposal_id}' not found."},
        )
    return proposal


@sync_router.post("/world-sync/{proposal_id}/apply", response_model=Dict[str, Any], operation_id="world.applyWorldSyncAction")
async def apply_world_sync_action(
    proposal_id: str = Path(...),
    body: WorldSyncActionApplyRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Apply one proposed action.

    ADD_LOCATION creates the canon location with a sync baseline;
    UPDATE_PROPOSED merges structural facts only. NO_CHANGE and CONFLICT are
    refused — manual resolution is the only path for conflicts.
    """
    proposal = await service.get(NS_WORLD_SYNC, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "WORLD_PROPOSAL_NOT_FOUND", "message": f"World sync proposal '{proposal_id}' not found."},
        )

    actions = proposal.get("actions") or []
    if body.action_index >= len(actions):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "ACTION_INDEX_OUT_OF_RANGE", "message": f"action_index {body.action_index} out of range (0..{len(actions) - 1})."},
        )
    action = actions[body.action_index]
    kind = action.get("action")
    if kind == ACTION_NO_CHANGE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "ACTION_NOT_APPLICABLE", "message": "NO_CHANGE actions have nothing to apply."},
        )
    if kind == ACTION_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ACTION_NOT_APPLICABLE",
                "message": (
                    "CONFLICT actions require a manual resolution; world sync "
                    "never overwrites manual edits."
                ),
            },
        )
    if kind not in APPLICABLE_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "UNKNOWN_ACTION", "message": f"Unknown proposal action '{kind}'."},
        )

    lineage = dict(proposal.get("lineage") or {})
    proposed = action.get("proposed") or {}
    now = utc_now().isoformat()

    if kind == "ADD_LOCATION":
        loc_id = f"loc-{uuid.uuid4().hex[:8]}"
        interior = proposed.get("interior")
        new_loc: Dict[str, Any] = {
            "id": loc_id,
            "project_id": proposal["project_id"],
            "name": str(proposed.get("name") or ""),
            "type": "Interior" if interior is True else "Exterior" if interior is False else "Unspecified",
            "description": "",
            "atmosphere": "",
            "interior": interior,
            "day_scene_compatible": True,
            "night_scene_compatible": True,
            "source_lineage": lineage,
            "last_synced_hash": None,
        }
        new_loc["content_hash"] = compute_content_hash(location_fingerprint(new_loc))
        new_loc["last_synced_hash"] = compute_content_hash(location_fingerprint(new_loc))
        created = await service.create(NS_LOCATIONS, loc_id, new_loc)
        result_kind = "ADD_LOCATION"
        result = _loc_resource(created).model_dump()
    else:  # UPDATE_PROPOSED
        loc_id = str(action.get("location_id") or "")
        curr = await service.get(NS_LOCATIONS, loc_id)
        if curr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "LOCATION_NOT_FOUND", "message": f"Location '{loc_id}' not found."},
            )
        updates = dict(curr)
        if proposed.get("interior") is not None:
            # Sync only proposes structural facts; human prose stays untouched.
            updates["interior"] = bool(proposed["interior"])
        updates["updated_at"] = now
        updates["content_hash"] = compute_content_hash(location_fingerprint(updates))
        updates["last_synced_hash"] = compute_content_hash(location_fingerprint(updates))
        merged_lineage = dict(curr.get("source_lineage") or {})
        merged_lineage.update({k: v for k, v in lineage.items() if v})
        updates["source_lineage"] = merged_lineage
        updated = await service.update(NS_LOCATIONS, loc_id, updates, curr["version"])
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "VERSION_CONFLICT", "message": f"Version conflict updating location '{loc_id}'."},
            )
        result_kind = ACTION_UPDATE_PROPOSED
        result = _loc_resource(updated).model_dump()

    actions[body.action_index] = {**action, "applied": True, "applied_location_id": result.get("id")}
    remaining = [a for a in actions if not a.get("applied") and a.get("action") in APPLICABLE_ACTIONS]
    proposal_updates = dict(proposal)
    proposal_updates["actions"] = actions
    proposal_updates["status"] = "APPLIED" if not remaining else "PARTIALLY_APPLIED"
    proposal_updates["updated_at"] = now
    await service.update(NS_WORLD_SYNC, proposal_id, proposal_updates, proposal.get("version", 1))

    return {"applied_action": result_kind, "location": result, "proposal_status": proposal_updates["status"]}
