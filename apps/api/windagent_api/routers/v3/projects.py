"""
V3 Projects and Episodes Router — Canonical project management authority.
Provides CRUD operations, optimistic locking, and episode hierarchy with idempotency keys.
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

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


# In-memory storage seeded with starter projects
_PROJECTS_STORE: Dict[str, Dict[str, Any]] = {
    "proj-cyberpunk-01": {
        "id": "proj-cyberpunk-01",
        "name": "Cyberpunk Odyssey 2099",
        "description": "Vũ trụ siêu đô thị ngầm tương lai nơi các hacker và cyborg tìm kiếm ký ức đã mất.",
        "version": 1,
        "episodes_count": 3,
        "created_at": "2026-08-01T08:00:00Z",
        "updated_at": "2026-08-10T12:00:00Z",
        "metadata": {"genre": "Cyberpunk / Sci-Fi", "accent": "#38bdf8"},
    },
    "proj-fantasy-02": {
        "id": "proj-fantasy-02",
        "name": "Biên Niên Sử Vùng Đất Rồng",
        "description": "Cuộc phiêu lưu huyền ảo qua các vương quốc cổ đại nhằm khôi phục viên ngọc nguyên tố.",
        "version": 1,
        "episodes_count": 2,
        "created_at": "2026-08-05T09:30:00Z",
        "updated_at": "2026-08-12T14:15:00Z",
        "metadata": {"genre": "High Fantasy / Adventure", "accent": "#34d399"},
    },
    "proj-noir-03": {
        "id": "proj-noir-03",
        "name": "Thám Tử Đêm Sương Mù",
        "description": "Những vụ án bí ẩn tại thành phố cảng những năm 1940 với các âm mưu ngầm.",
        "version": 1,
        "episodes_count": 1,
        "created_at": "2026-08-08T11:00:00Z",
        "updated_at": "2026-08-13T16:45:00Z",
        "metadata": {"genre": "Drama / Mystery Noir", "accent": "#fbbf24"},
    },
}

_EPISODES_STORE: Dict[str, List[Dict[str, Any]]] = {
    "proj-cyberpunk-01": [
        {
            "id": "ep-cb-001",
            "project_id": "proj-cyberpunk-01",
            "title": "Tập 01: Mã Nguồn Thức Tỉnh",
            "episode_number": 1,
            "state": "SCREENPLAY",
            "version": 1,
            "created_at": "2026-08-01T08:30:00Z",
            "updated_at": "2026-08-04T10:00:00Z",
        },
        {
            "id": "ep-cb-002",
            "project_id": "proj-cyberpunk-01",
            "title": "Tập 02: Mê Cung Neon",
            "episode_number": 2,
            "state": "OUTLINE",
            "version": 1,
            "created_at": "2026-08-05T08:30:00Z",
            "updated_at": "2026-08-08T10:00:00Z",
        },
        {
            "id": "ep-cb-003",
            "project_id": "proj-cyberpunk-01",
            "title": "Tập 03: Tín Hiệu Cuối Cùng",
            "episode_number": 3,
            "state": "DRAFT",
            "version": 1,
            "created_at": "2026-08-10T08:30:00Z",
            "updated_at": "2026-08-10T12:00:00Z",
        },
    ],
    "proj-fantasy-02": [
        {
            "id": "ep-ft-001",
            "project_id": "proj-fantasy-02",
            "title": "Tập 01: Tiếng Gọi Rừng Thiêng",
            "episode_number": 1,
            "state": "SCREENPLAY",
            "version": 1,
            "created_at": "2026-08-05T10:00:00Z",
            "updated_at": "2026-08-08T11:00:00Z",
        },
        {
            "id": "ep-ft-002",
            "project_id": "proj-fantasy-02",
            "title": "Tập 02: Hẻm Núi Gió Hú",
            "episode_number": 2,
            "state": "DRAFT",
            "version": 1,
            "created_at": "2026-08-12T10:00:00Z",
            "updated_at": "2026-08-12T14:15:00Z",
        },
    ],
    "proj-noir-03": [
        {
            "id": "ep-nr-001",
            "project_id": "proj-noir-03",
            "title": "Tập 01: Vết Bóng Trên Cầu Cảng",
            "episode_number": 1,
            "state": "DRAFT",
            "version": 1,
            "created_at": "2026-08-08T11:30:00Z",
            "updated_at": "2026-08-13T16:45:00Z",
        },
    ],
}

_IDEMPOTENCY_KEYS_PROJECTS: Dict[str, str] = {}
_IDEMPOTENCY_KEYS_EPISODES: Dict[str, str] = {}


@router.get("", response_model=ProjectListResponse, operation_id="projects.list")
async def list_projects(
    search: Optional[str] = Query(None, description="Search term for project title or description"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(50, ge=1, le=200, description="Items limit"),
) -> ProjectListResponse:
    """List all projects in workspace with optional search filtering."""
    projects_list = list(_PROJECTS_STORE.values())

    if search:
        s = search.lower()
        projects_list = [p for p in projects_list if s in p["name"].lower() or (p.get("description") and s in p["description"].lower())]

    if genre and genre != "all":
        projects_list = [p for p in projects_list if p.get("metadata", {}).get("genre") == genre]

    # Sort newest first
    projects_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

    items = [ProjectResource(**p) for p in projects_list[:limit]]
    return ProjectListResponse(
        items=items,
        page_info=PageInfo(next_cursor=None, has_more=False),
    )


@router.post("", response_model=ProjectResource, status_code=status.HTTP_201_CREATED, operation_id="projects.create")
async def create_project(
    body: CreateProjectRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ProjectResource:
    """Create a new project. Supports idempotent submission via Idempotency-Key header."""
    if idempotency_key and idempotency_key in _IDEMPOTENCY_KEYS_PROJECTS:
        existing_id = _IDEMPOTENCY_KEYS_PROJECTS[idempotency_key]
        if existing_id in _PROJECTS_STORE:
            return ProjectResource(**_PROJECTS_STORE[existing_id])

    now_iso = utc_now().isoformat()
    project_id = f"proj-{uuid.uuid4().hex[:8]}"

    metadata = {}
    if body.genre:
        metadata["genre"] = body.genre

    new_project = {
        "id": project_id,
        "name": body.name,
        "description": body.description,
        "version": 1,
        "episodes_count": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
        "metadata": metadata,
    }

    _PROJECTS_STORE[project_id] = new_project
    _EPISODES_STORE[project_id] = []

    # If initial episode specified, create Episode 1
    if body.initial_episode_title:
        ep_id = f"ep-{uuid.uuid4().hex[:8]}"
        initial_ep = {
            "id": ep_id,
            "project_id": project_id,
            "title": body.initial_episode_title,
            "episode_number": 1,
            "state": "DRAFT",
            "version": 1,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        _EPISODES_STORE[project_id].append(initial_ep)
        new_project["episodes_count"] = 1

    if idempotency_key:
        _IDEMPOTENCY_KEYS_PROJECTS[idempotency_key] = project_id

    return ProjectResource(**new_project)


@router.get("/{project_id}", response_model=ProjectResource, operation_id="projects.get")
async def get_project(
    project_id: str = Path(..., description="Project ID"),
) -> ProjectResource:
    """Retrieve details of a specific project."""
    if project_id not in _PROJECTS_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ProjectResource(**_PROJECTS_STORE[project_id])


@router.patch("/{project_id}", response_model=ProjectResource, operation_id="projects.update")
async def update_project(
    project_id: str = Path(..., description="Project ID"),
    body: UpdateProjectRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ProjectResource:
    """Update project title or description with optimistic concurrency check."""
    if project_id not in _PROJECTS_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    curr = _PROJECTS_STORE[project_id]

    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale version conflict for project '{project_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    if body.name is not None:
        curr["name"] = body.name
    if body.description is not None:
        curr["description"] = body.description

    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()

    return ProjectResource(**curr)


@router.get("/{project_id}/episodes", response_model=EpisodeListResponse, operation_id="episodes.listForProject")
async def list_episodes_for_project(
    project_id: str = Path(..., description="Project ID"),
) -> EpisodeListResponse:
    """List all episodes belonging to a project."""
    if project_id not in _PROJECTS_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    episodes_list = _EPISODES_STORE.get(project_id, [])
    episodes_list.sort(key=lambda e: e.get("episode_number", 1))

    items = [EpisodeResource(**e) for e in episodes_list]
    return EpisodeListResponse(
        items=items,
        page_info=PageInfo(next_cursor=None, has_more=False),
    )


@router.post("/{project_id}/episodes", response_model=EpisodeResource, status_code=status.HTTP_201_CREATED, operation_id="episodes.create")
async def create_episode_for_project(
    project_id: str = Path(..., description="Project ID"),
    body: CreateEpisodeRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> EpisodeResource:
    """Create a new episode in a project."""
    if project_id not in _PROJECTS_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    if idempotency_key and idempotency_key in _IDEMPOTENCY_KEYS_EPISODES:
        existing_id = _IDEMPOTENCY_KEYS_EPISODES[idempotency_key]
        for ep in _EPISODES_STORE.get(project_id, []):
            if ep["id"] == existing_id:
                return EpisodeResource(**ep)

    now_iso = utc_now().isoformat()
    ep_id = f"ep-{uuid.uuid4().hex[:8]}"

    existing_episodes = _EPISODES_STORE.get(project_id, [])
    next_num = body.episode_number or (len(existing_episodes) + 1)

    new_episode = {
        "id": ep_id,
        "project_id": project_id,
        "title": body.title,
        "episode_number": next_num,
        "state": "DRAFT",
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    if project_id not in _EPISODES_STORE:
        _EPISODES_STORE[project_id] = []
    _EPISODES_STORE[project_id].append(new_episode)

    _PROJECTS_STORE[project_id]["episodes_count"] = len(_EPISODES_STORE[project_id])
    _PROJECTS_STORE[project_id]["updated_at"] = now_iso

    if idempotency_key:
        _IDEMPOTENCY_KEYS_EPISODES[idempotency_key] = ep_id

    return EpisodeResource(**new_episode)
