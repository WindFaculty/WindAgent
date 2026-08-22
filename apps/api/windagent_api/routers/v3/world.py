"""
V3 World Bible Router — Canonical World Building for Story Production Domain.
Provides World Bible CRUD and sub-resources: Locations, Factions, Lore.

Phase 4: world bibles, locations, factions, and lore are persisted through
the namespaced durable V3 resource authority. No module-level RAM stores.
"""
from __future__ import annotations
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import (
    NS_WORLD_BIBLES,
    NS_LOCATIONS,
    NS_FACTIONS,
    NS_LORE,
    NS_PROJECTS,
)

router = APIRouter(prefix="/api/v3/projects", tags=["World V3"])


class LocationResource(BaseModel):
    id: str
    project_id: str
    name: str
    type: str = "Interior"
    description: str = ""
    atmosphere: str = ""
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


class WorldBibleResource(BaseModel):
    project_id: str
    world_name: str
    setting_summary: str = ""
    core_theme: str = ""
    rules: List[str] = Field(default_factory=list)
    timeline_era: str = ""
    version: int = 1
    locations_count: int = 0
    factions_count: int = 0
    lore_count: int = 0
    updated_at: str = ""


class UpdateWorldBibleRequest(BaseModel):
    world_name: Optional[str] = None
    setting_summary: Optional[str] = None
    core_theme: Optional[str] = None
    rules: Optional[List[str]] = None
    timeline_era: Optional[str] = None
    expected_version: int = Field(..., description="Optimistic locking version")


class InitializeWorldBibleRequest(BaseModel):
    world_name: str = Field(..., min_length=1, max_length=200, description="Explicit canonical world name")
    setting_summary: str = ""
    core_theme: str = ""
    rules: List[str] = Field(default_factory=list)
    timeline_era: str = ""


class CreateLocationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = "Interior"
    description: str = ""
    atmosphere: str = ""


class CreateFactionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    ideology: str = ""
    influence_level: int = Field(50, ge=0, le=100)
    description: str = ""


class CreateLoreRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = "History"
    content: str = ""


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
    wb = {
        "project_id": project_id,
        "world_name": body.world_name,
        "setting_summary": body.setting_summary,
        "core_theme": body.core_theme,
        "rules": body.rules,
        "timeline_era": body.timeline_era,
        "updated_at": now,
    }
    created = await service.create(NS_WORLD_BIBLES, project_id, wb)
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
    """Update the World Bible with optimistic concurrency check."""
    wb = await service.get(NS_WORLD_BIBLES, project_id)
    if wb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"World Bible for project '{project_id}' not found.")

    if wb["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for World Bible. Expected {wb['version']}, got {body.expected_version}.")

    updates = dict(wb)
    if body.world_name is not None:
        updates["world_name"] = body.world_name
    if body.setting_summary is not None:
        updates["setting_summary"] = body.setting_summary
    if body.core_theme is not None:
        updates["core_theme"] = body.core_theme
    if body.rules is not None:
        updates["rules"] = body.rules
    if body.timeline_era is not None:
        updates["timeline_era"] = body.timeline_era
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_WORLD_BIBLES, project_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version conflict for World Bible.")
    return await get_world_bible(project_id, service)


@router.get("/{project_id}/world/locations", response_model=List[LocationResource], operation_id="world.listLocations")
async def list_locations(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[LocationResource]:
    locs = await service.list(NS_LOCATIONS)
    return [LocationResource(**loc) for loc in locs if loc.get("project_id") == project_id]


@router.post("/{project_id}/world/locations", response_model=LocationResource, status_code=status.HTTP_201_CREATED, operation_id="world.createLocation")
async def create_location(
    project_id: str = Path(...),
    body: CreateLocationRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> LocationResource:
    loc_id = f"loc-{uuid.uuid4().hex[:8]}"
    new_loc = {"id": loc_id, "project_id": project_id, "name": body.name, "type": body.type, "description": body.description, "atmosphere": body.atmosphere}
    created = await service.create(NS_LOCATIONS, loc_id, new_loc)
    return LocationResource(**created)


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
