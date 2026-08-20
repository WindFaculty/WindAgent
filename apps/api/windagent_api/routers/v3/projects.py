"""
V3 Projects and Episodes Router — Canonical project management authority.
Provides CRUD operations, optimistic locking, and episode hierarchy with idempotency keys.

Phase 4: all mutable state is persisted through the namespaced durable V3
resource authority (Router -> Application Service -> Core Port -> SQL
Repository -> Unit of Work). No module-level RAM stores.
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_PROJECTS, NS_EPISODES

router = APIRouter(prefix="/api/v3/projects", tags=["Projects V3"])


class ProjectResource(BaseModel):
    id: str = Field(..., description="Canonical project UUID")
    name: str = Field(..., description="Project display title")
    description: Optional[str] = Field(None, description="Detailed project overview or logline")
    version: int = Field(1, description="Optimistic locking version counter")
    episodes_count: int = Field(0, description="Total number of episodes in this project")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    updated_at: str = Field(..., description="ISO 8601 UTC timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom project metadata")


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Project title")
    description: Optional[str] = Field(None, max_length=2000, description="Project logline or synopsis")
    genre: Optional[str] = Field(None, description="Cinematic genre tag")
    initial_episode_title: Optional[str] = Field(None, description="Optional title for Episode 1")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    expected_version: int = Field(..., description="Expected current version for optimistic concurrency")


class EpisodeResource(BaseModel):
    id: str = Field(..., description="Canonical episode UUID")
    project_id: str = Field(..., description="Parent project identifier")
    title: str = Field(..., description="Episode title")
    episode_number: int = Field(1, description="Sequential episode order")
    state: str = Field("DRAFT", description="Workflow state ('DRAFT', 'STORY_BIBLE', 'OUTLINE', 'SCREENPLAY', 'LOCKED')")
    version: int = Field(1, description="Optimistic version counter")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")
    updated_at: str = Field(..., description="ISO 8601 UTC timestamp")


class CreateEpisodeRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Episode title")
    episode_number: Optional[int] = Field(None, description="Optional episode order number")


class PageInfo(BaseModel):
    next_cursor: Optional[str] = None
    has_more: bool = False


class ProjectListResponse(BaseModel):
    items: List[ProjectResource]
    page_info: PageInfo


class EpisodeListResponse(BaseModel):
    items: List[EpisodeResource]
    page_info: PageInfo


def _project_to_resource(p: Dict[str, Any]) -> ProjectResource:
    return ProjectResource(
        id=p["id"],
        name=p["name"],
        description=p.get("description"),
        version=p.get("version", 1),
        episodes_count=p.get("episodes_count", 0),
        created_at=p.get("created_at", ""),
        updated_at=p.get("updated_at", ""),
        metadata=p.get("metadata", {}),
    )


def _episode_to_resource(e: Dict[str, Any]) -> EpisodeResource:
    return EpisodeResource(
        id=e["id"],
        project_id=e["project_id"],
        title=e["title"],
        episode_number=e.get("episode_number", 1),
        state=e.get("state", "DRAFT"),
        version=e.get("version", 1),
        created_at=e.get("created_at", ""),
        updated_at=e.get("updated_at", ""),
    )


@router.get("", response_model=ProjectListResponse, operation_id="projects.list")
async def list_projects(
    search: Optional[str] = Query(None, description="Search term for project title or description"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=200, description="Items limit"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProjectListResponse:
    """List all projects in workspace with optional search filtering."""
    projects_list = await service.list(NS_PROJECTS)

    if search:
        s = search.lower()
        projects_list = [p for p in projects_list if s in p["name"].lower() or (p.get("description") and s in p["description"].lower())]

    if genre and genre != "all":
        projects_list = [p for p in projects_list if p.get("metadata", {}).get("genre") == genre]

    # Sort newest first
    projects_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

    items = [_project_to_resource(p) for p in projects_list[:limit]]
    return ProjectListResponse(
        items=items,
        page_info=PageInfo(next_cursor=None, has_more=False),
    )


@router.post("", response_model=ProjectResource, status_code=status.HTTP_201_CREATED, operation_id="projects.create")
async def create_project(
    body: CreateProjectRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProjectResource:
    """Create a new project. Supports idempotent submission via Idempotency-Key header."""
    if idempotency_key:
        existing = await service.find_by_idempotency(NS_PROJECTS, idempotency_key)
        if existing is not None:
            return _project_to_resource(existing)

    now_iso = utc_now().isoformat()
    project_id = f"proj-{uuid.uuid4().hex[:8]}"

    metadata = {}
    if body.genre:
        metadata["genre"] = body.genre

    new_project = {
        "id": project_id,
        "name": body.name,
        "description": body.description,
        "episodes_count": 0,
        "metadata": metadata,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    # If initial episode specified, create Episode 1
    if body.initial_episode_title:
        ep_id = f"ep-{uuid.uuid4().hex[:8]}"
        initial_ep = {
            "id": ep_id,
            "project_id": project_id,
            "title": body.initial_episode_title,
            "episode_number": 1,
            "state": "DRAFT",
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await service.create(NS_EPISODES, ep_id, initial_ep)
        new_project["episodes_count"] = 1

    created = await service.create(NS_PROJECTS, project_id, new_project, idempotency_key)
    return _project_to_resource(created)


@router.get("/{project_id}", response_model=ProjectResource, operation_id="projects.get")
async def get_project(
    project_id: str = Path(..., description="Project ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProjectResource:
    """Retrieve details of a specific project."""
    project = await service.get(NS_PROJECTS, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return _project_to_resource(project)


@router.patch("/{project_id}", response_model=ProjectResource, operation_id="projects.update")
async def update_project(
    project_id: str = Path(..., description="Project ID"),
    body: UpdateProjectRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ProjectResource:
    """Update project title or description with optimistic concurrency check."""
    curr = await service.get(NS_PROJECTS, project_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for project '{project_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_PROJECTS, project_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Stale version conflict for project '{project_id}'.")
    return _project_to_resource(updated)


@router.get("/{project_id}/episodes", response_model=EpisodeListResponse, operation_id="episodes.listForProject")
async def list_episodes_for_project(
    project_id: str = Path(..., description="Project ID"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeListResponse:
    """List all episodes belonging to a project."""
    project = await service.get(NS_PROJECTS, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    episodes_list = await service.list(NS_EPISODES)
    episodes_list = [e for e in episodes_list if e.get("project_id") == project_id]
    episodes_list.sort(key=lambda e: e.get("episode_number", 1))

    items = [_episode_to_resource(e) for e in episodes_list]
    return EpisodeListResponse(
        items=items,
        page_info=PageInfo(next_cursor=None, has_more=False),
    )


@router.post("/{project_id}/episodes", response_model=EpisodeResource, status_code=status.HTTP_201_CREATED, operation_id="episodes.create")
async def create_episode_for_project(
    project_id: str = Path(..., description="Project ID"),
    body: CreateEpisodeRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> EpisodeResource:
    """Create a new episode in a project."""
    project = await service.get(NS_PROJECTS, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    if idempotency_key:
        existing = await service.find_by_idempotency(NS_EPISODES, idempotency_key)
        if existing is not None:
            return _episode_to_resource(existing)

    now_iso = utc_now().isoformat()
    ep_id = f"ep-{uuid.uuid4().hex[:8]}"

    existing_episodes = await service.list(NS_EPISODES)
    existing_episodes = [e for e in existing_episodes if e.get("project_id") == project_id]
    next_num = body.episode_number or (len(existing_episodes) + 1)

    new_episode = {
        "id": ep_id,
        "project_id": project_id,
        "title": body.title,
        "episode_number": next_num,
        "state": "DRAFT",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    created = await service.create(NS_EPISODES, ep_id, new_episode, idempotency_key)

    # Update project episode count
    project_updates = dict(project)
    project_updates["episodes_count"] = len(existing_episodes) + 1
    project_updates["updated_at"] = now_iso
    await service.update(NS_PROJECTS, project_id, project_updates, project["version"])

    return _episode_to_resource(created)
