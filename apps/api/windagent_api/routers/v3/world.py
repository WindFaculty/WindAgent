"""
V3 World Bible Router — Canonical World Building for Story Production Domain.
Provides World Bible CRUD and sub-resources: Locations, Factions, Lore.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

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


_WORLD_BIBLES: Dict[str, Dict[str, Any]] = {
    "proj-cyberpunk-01": {
        "project_id": "proj-cyberpunk-01",
        "world_name": "Neo-Saigon 2099",
        "setting_summary": "Siêu đô thị chia làm 3 tầng: Tầng Thượng lưu trên đỉnh mây, Tầng Trung cư nhộn nhịp và Tầng Ngầm 404 của các tin tặc và phế nhân.",
        "core_theme": "Ranh giới giữa ý thức nhân tạo và linh hồn con người trong thời đại dữ liệu thống trị tất cả.",
        "rules": [
            "AI được coi là công cụ pháp lý, không phải thực thể.",
            "Tầng Ngầm 404 là vùng tự trị, ngoài tầm kiểm soát của Apex Cortex.",
            "Mọi giao dịch đều được lưu trong blockchain phi tập trung.",
        ],
        "timeline_era": "Hậu-Sụp Đổ Tài Chính Toàn Cầu năm 2071",
        "version": 1,
        "updated_at": "2026-08-14T00:00:00Z",
    },
}

_LOCATIONS: Dict[str, Dict[str, Any]] = {
    "loc-tầng-404-01": {"id": "loc-tầng-404-01", "project_id": "proj-cyberpunk-01", "name": "Tầng Ngầm 404", "type": "Exterior", "description": "Khu vực ngầm hỗn loạn bên dưới thành phố, nơi ẩn náu của tin tặc và những người ngoài vòng pháp luật.", "atmosphere": "Tối tăm, ẩm ướt, đèn neon, tiếng máy móc vang vọng", "version": 1},
    "loc-apex-tower-01": {"id": "loc-apex-tower-01", "project_id": "proj-cyberpunk-01", "name": "Apex Cortex Tower", "type": "Interior", "description": "Trụ sở tập đoàn Apex Cortex cao 200 tầng, vươn lên khỏi tầng mây.", "atmosphere": "Lạnh lùng, vô trùng, ánh sáng trắng sterile, an ninh dày đặc", "version": 1},
}

_FACTIONS: Dict[str, Dict[str, Any]] = {
    "fac-apex-01": {"id": "fac-apex-01", "project_id": "proj-cyberpunk-01", "name": "Apex Cortex Corp", "ideology": "Kiểm soát thông tin = kiểm soát nhân loại", "influence_level": 95, "description": "Tập đoàn công nghệ độc quyền thống trị nền kinh tế dữ liệu toàn cầu.", "version": 1},
    "fac-ghost-net-01": {"id": "fac-ghost-net-01", "project_id": "proj-cyberpunk-01", "name": "Ghost Net Collective", "ideology": "Thông tin tự do, không có quyền lực tập trung", "influence_level": 35, "description": "Liên minh tin tặc hoạt động trong Tầng Ngầm 404, chiến đấu cho quyền riêng tư kỹ thuật số.", "version": 1},
}

_LORE: Dict[str, Dict[str, Any]] = {
    "lore-collapse-01": {"id": "lore-collapse-01", "project_id": "proj-cyberpunk-01", "title": "Sụp Đổ Tài Chính 2071", "category": "History", "content": "Cuộc khủng hoảng kinh tế toàn cầu xảy ra khi các AI giao dịch tần số cao sụp đổ đồng loạt, xóa sổ 60% tài sản số toàn thế giới trong 3 giờ.", "version": 1},
}


@router.get("/{project_id}/world", response_model=WorldBibleResource, operation_id="world.get")
async def get_world_bible(project_id: str = Path(...)) -> WorldBibleResource:
    """Retrieve the World Bible for a project."""
    if project_id not in _WORLD_BIBLES:
        # Create empty world bible on demand
        now = utc_now().isoformat()
        _WORLD_BIBLES[project_id] = {
            "project_id": project_id,
            "world_name": "Untitled World",
            "setting_summary": "",
            "core_theme": "",
            "rules": [],
            "timeline_era": "",
            "version": 1,
            "updated_at": now,
        }

    wb = _WORLD_BIBLES[project_id]
    locs = [l for l in _LOCATIONS.values() if l["project_id"] == project_id]
    facs = [f for f in _FACTIONS.values() if f["project_id"] == project_id]
    lore = [l for l in _LORE.values() if l["project_id"] == project_id]

    return WorldBibleResource(
        **{k: v for k, v in wb.items() if k != "updated_at"},
        locations_count=len(locs),
        factions_count=len(facs),
        lore_count=len(lore),
        updated_at=wb["updated_at"],
    )


@router.patch("/{project_id}/world", response_model=WorldBibleResource, operation_id="world.update")
async def update_world_bible(project_id: str = Path(...), body: UpdateWorldBibleRequest = ...) -> WorldBibleResource:
    """Update the World Bible with optimistic concurrency check."""
    if project_id not in _WORLD_BIBLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"World Bible for project '{project_id}' not found.")

    wb = _WORLD_BIBLES[project_id]
    if wb["version"] != body.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for World Bible. Expected {wb['version']}, got {body.expected_version}.")

    if body.world_name is not None:
        wb["world_name"] = body.world_name
    if body.setting_summary is not None:
        wb["setting_summary"] = body.setting_summary
    if body.core_theme is not None:
        wb["core_theme"] = body.core_theme
    if body.rules is not None:
        wb["rules"] = body.rules
    if body.timeline_era is not None:
        wb["timeline_era"] = body.timeline_era
    wb["version"] += 1
    wb["updated_at"] = utc_now().isoformat()
    return await get_world_bible(project_id)


@router.get("/{project_id}/world/locations", response_model=List[LocationResource], operation_id="world.listLocations")
async def list_locations(project_id: str = Path(...)) -> List[LocationResource]:
    return [LocationResource(**l) for l in _LOCATIONS.values() if l["project_id"] == project_id]


@router.post("/{project_id}/world/locations", response_model=LocationResource, status_code=status.HTTP_201_CREATED, operation_id="world.createLocation")
async def create_location(project_id: str = Path(...), body: CreateLocationRequest = ...) -> LocationResource:
    loc_id = f"loc-{uuid.uuid4().hex[:8]}"
    new_loc = {"id": loc_id, "project_id": project_id, "name": body.name, "type": body.type, "description": body.description, "atmosphere": body.atmosphere, "version": 1}
    _LOCATIONS[loc_id] = new_loc
    return LocationResource(**new_loc)


@router.get("/{project_id}/world/factions", response_model=List[FactionResource], operation_id="world.listFactions")
async def list_factions(project_id: str = Path(...)) -> List[FactionResource]:
    return [FactionResource(**f) for f in _FACTIONS.values() if f["project_id"] == project_id]


@router.post("/{project_id}/world/factions", response_model=FactionResource, status_code=status.HTTP_201_CREATED, operation_id="world.createFaction")
async def create_faction(project_id: str = Path(...), body: CreateFactionRequest = ...) -> FactionResource:
    fac_id = f"fac-{uuid.uuid4().hex[:8]}"
    new_fac = {"id": fac_id, "project_id": project_id, "name": body.name, "ideology": body.ideology, "influence_level": body.influence_level, "description": body.description, "version": 1}
    _FACTIONS[fac_id] = new_fac
    return FactionResource(**new_fac)


@router.get("/{project_id}/world/lore", response_model=List[LoreEntryResource], operation_id="world.listLore")
async def list_lore(project_id: str = Path(...)) -> List[LoreEntryResource]:
    return [LoreEntryResource(**l) for l in _LORE.values() if l["project_id"] == project_id]


@router.post("/{project_id}/world/lore", response_model=LoreEntryResource, status_code=status.HTTP_201_CREATED, operation_id="world.createLore")
async def create_lore(project_id: str = Path(...), body: CreateLoreRequest = ...) -> LoreEntryResource:
    lore_id = f"lore-{uuid.uuid4().hex[:8]}"
    new_lore = {"id": lore_id, "project_id": project_id, "title": body.title, "category": body.category, "content": body.content, "version": 1}
    _LORE[lore_id] = new_lore
    return LoreEntryResource(**new_lore)
