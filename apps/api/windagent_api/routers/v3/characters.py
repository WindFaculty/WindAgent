"""
V3 Characters Router — Canonical Character Management for Story Production Domain.
Provides CRUD, relationship graph, and character assets per project.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v3", tags=["Characters V3"])


class CharacterIdentity(BaseModel):
    name: str
    role: str = "Supporting"
    biography: str = ""


class CharacterPsychology(BaseModel):
    dominant_trait: str = ""
    flaw: str = ""
    alignment_score: int = 50


class CharacterVisualProfile(BaseModel):
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    physical_description: str = ""
    style_notes: str = ""


class CharacterVoiceProfile(BaseModel):
    voice_model_id: Optional[str] = None
    voice_style: str = ""
    sample_lines: List[str] = Field(default_factory=list)


class CharacterRelationship(BaseModel):
    target_character_id: str
    target_name: str
    relationship_type: str = "Ally"


class CharacterResource(BaseModel):
    id: str
    project_id: str
    identity: CharacterIdentity
    psychology: CharacterPsychology
    visual_profile: CharacterVisualProfile
    voice_profile: CharacterVoiceProfile
    relationships: List[CharacterRelationship] = Field(default_factory=list)
    version: int = 1
    created_at: str
    updated_at: str


class CreateCharacterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field("Supporting", description="Protagonist | Antagonist | Supporting | Draft")
    biography: str = Field("", max_length=5000)
    dominant_trait: str = ""
    flaw: str = ""
    alignment_score: int = Field(50, ge=0, le=100)
    voice_model_id: Optional[str] = None
    voice_style: str = ""


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    role: Optional[str] = None
    biography: Optional[str] = None
    dominant_trait: Optional[str] = None
    flaw: Optional[str] = None
    alignment_score: Optional[int] = Field(None, ge=0, le=100)
    voice_model_id: Optional[str] = None
    voice_style: Optional[str] = None
    expected_version: int = Field(..., description="Optimistic locking version")


_CHARACTERS: Dict[str, Dict[str, Any]] = {
    "char-kaelen-01": {
        "id": "char-kaelen-01",
        "project_id": "proj-cyberpunk-01",
        "identity": {"name": "Kaelen Vance", "role": "Protagonist", "biography": "Cựu đặc nhiệm bị bỏ lại tại các phân khu Outer Rim. Dựa vào sự chính xác chiến thuật và nghi ngờ chính quyền để sinh tồn. Dù vẻ ngoài lạnh lùng, sở hữu la bàn đạo đức kiên định."},
        "psychology": {"dominant_trait": "Stoic", "flaw": "Distrustful", "alignment_score": 75},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "Tóc bạc, mắt xám, vóc dáng rắn chắc", "style_notes": "Áo khoác dài tối màu, găng tay chiến thuật"},
        "voice_profile": {"voice_model_id": "ELEVEN_GRIT_02", "voice_style": "Trầm ấm, đanh thép, quyết đoán", "sample_lines": ["Không ai được bỏ lại.", "Chiến thuật trước, cảm xúc sau."]},
        "relationships": [
            {"target_character_id": "char-nova-01", "target_name": "Nova Tink", "relationship_type": "Ally"},
            {"target_character_id": "char-sylas-01", "target_name": "Sylas Thorne", "relationship_type": "Rival"},
        ],
        "version": 1,
        "created_at": "2026-08-01T08:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
    "char-nova-01": {
        "id": "char-nova-01",
        "project_id": "proj-cyberpunk-01",
        "identity": {"name": "Nova Tink", "role": "Supporting", "biography": "Kỹ sư cơ khí thiên tài với tính cách lập dị. Có khả năng biến phế liệu công nghệ thành vũ khí thông minh trong thời gian kỷ lục."},
        "psychology": {"dominant_trait": "Chaotic Good", "flaw": "Impulsive", "alignment_score": 60},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "Tóc đỏ ngắn, mắt xanh lá, ngón tay nhanh thoăn thoắt", "style_notes": "Áo liền thân kỹ thuật số, găng tay công cụ"},
        "voice_profile": {"voice_model_id": "ELEVEN_ENERGETIC_01", "voice_style": "Nhanh, hào hứng, tự nhiên", "sample_lines": ["Xong rồi! Thật ra nhanh hơn tôi nghĩ.", "Đừng chạm vào cái đó — trừ khi bạn muốn bị điện giật."]},
        "relationships": [
            {"target_character_id": "char-kaelen-01", "target_name": "Kaelen Vance", "relationship_type": "Ally"},
        ],
        "version": 1,
        "created_at": "2026-08-01T09:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
    "char-sylas-01": {
        "id": "char-sylas-01",
        "project_id": "proj-cyberpunk-01",
        "identity": {"name": "Sylas Thorne", "role": "Antagonist", "biography": "Giám đốc điều hành tập đoàn Apex Cortex. Thao túng thị trường thông tin để củng cố quyền lực. Tin rằng sự hỗn loạn là công cụ, không phải mối đe dọa."},
        "psychology": {"dominant_trait": "Manipulative", "flaw": "Arrogant", "alignment_score": 15},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "Tóc đen bóng, khuôn mặt sắc lạnh, ăn mặc hoàn hảo theo phong cách corporate", "style_notes": "Vest cao cấp, cà vạt bạch kim, nhẫn Apex Cortex"},
        "voice_profile": {"voice_model_id": "ELEVEN_COLD_01", "voice_style": "Lạnh lùng, thong thả, thao túng", "sample_lines": ["Tất cả đều có giá. Kể cả lý tưởng của anh.", "Hỗn loạn? Không. Đây là thiết kế."]},
        "relationships": [
            {"target_character_id": "char-kaelen-01", "target_name": "Kaelen Vance", "relationship_type": "Rival"},
        ],
        "version": 1,
        "created_at": "2026-08-01T10:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
}

_IDEMPOTENCY_CHARS: Dict[str, str] = {}


def _char_to_resource(c: Dict[str, Any]) -> CharacterResource:
    return CharacterResource(
        id=c["id"],
        project_id=c["project_id"],
        identity=CharacterIdentity(**c["identity"]),
        psychology=CharacterPsychology(**c["psychology"]),
        visual_profile=CharacterVisualProfile(**c["visual_profile"]),
        voice_profile=CharacterVoiceProfile(**c["voice_profile"]),
        relationships=[CharacterRelationship(**r) for r in c.get("relationships", [])],
        version=c["version"],
        created_at=c["created_at"],
        updated_at=c["updated_at"],
    )


@router.get("/projects/{project_id}/characters", response_model=List[CharacterResource], operation_id="characters.listForProject")
async def list_project_characters(
    project_id: str = Path(...),
    search: Optional[str] = Query(None),
) -> List[CharacterResource]:
    """List all characters belonging to a project."""
    chars = [c for c in _CHARACTERS.values() if c["project_id"] == project_id]
    if search:
        s = search.lower()
        chars = [c for c in chars if s in c["identity"]["name"].lower() or s in c["identity"]["role"].lower()]
    return [_char_to_resource(c) for c in chars]


@router.post("/projects/{project_id}/characters", response_model=CharacterResource, status_code=status.HTTP_201_CREATED, operation_id="characters.create")
async def create_character(
    project_id: str = Path(...),
    body: CreateCharacterRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CharacterResource:
    """Create a new character in a project with idempotency support."""
    if idempotency_key and idempotency_key in _IDEMPOTENCY_CHARS:
        return _char_to_resource(_CHARACTERS[_IDEMPOTENCY_CHARS[idempotency_key]])

    char_id = f"char-{uuid.uuid4().hex[:8]}"
    now = utc_now().isoformat()
    new_char = {
        "id": char_id,
        "project_id": project_id,
        "identity": {"name": body.name, "role": body.role, "biography": body.biography},
        "psychology": {"dominant_trait": body.dominant_trait, "flaw": body.flaw, "alignment_score": body.alignment_score},
        "visual_profile": {"avatar_url": None, "banner_url": None, "physical_description": "", "style_notes": ""},
        "voice_profile": {"voice_model_id": body.voice_model_id, "voice_style": body.voice_style, "sample_lines": []},
        "relationships": [],
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    _CHARACTERS[char_id] = new_char
    if idempotency_key:
        _IDEMPOTENCY_CHARS[idempotency_key] = char_id

    return _char_to_resource(new_char)


@router.get("/characters/{character_id}", response_model=CharacterResource, operation_id="characters.get")
async def get_character(character_id: str = Path(...)) -> CharacterResource:
    """Retrieve full character detail by ID."""
    if character_id not in _CHARACTERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    return _char_to_resource(_CHARACTERS[character_id])


@router.patch("/characters/{character_id}", response_model=CharacterResource, operation_id="characters.update")
async def update_character(
    character_id: str = Path(...),
    body: UpdateCharacterRequest = ...,
) -> CharacterResource:
    """Update character fields with optimistic concurrency check."""
    if character_id not in _CHARACTERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")

    curr = _CHARACTERS[character_id]
    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for character '{character_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    if body.name is not None:
        curr["identity"]["name"] = body.name
    if body.role is not None:
        curr["identity"]["role"] = body.role
    if body.biography is not None:
        curr["identity"]["biography"] = body.biography
    if body.dominant_trait is not None:
        curr["psychology"]["dominant_trait"] = body.dominant_trait
    if body.flaw is not None:
        curr["psychology"]["flaw"] = body.flaw
    if body.alignment_score is not None:
        curr["psychology"]["alignment_score"] = body.alignment_score
    if body.voice_model_id is not None:
        curr["voice_profile"]["voice_model_id"] = body.voice_model_id
    if body.voice_style is not None:
        curr["voice_profile"]["voice_style"] = body.voice_style

    curr["version"] += 1
    curr["updated_at"] = utc_now().isoformat()
    return _char_to_resource(curr)


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="characters.delete")
async def delete_character(character_id: str = Path(...)) -> None:
    """Delete a character by ID."""
    if character_id in _CHARACTERS:
        del _CHARACTERS[character_id]


@router.get("/characters/{character_id}/relationships", response_model=List[CharacterRelationship], operation_id="characters.getRelationships")
async def get_character_relationships(character_id: str = Path(...)) -> List[CharacterRelationship]:
    """Retrieve the relationship graph for a character."""
    if character_id not in _CHARACTERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    return [CharacterRelationship(**r) for r in _CHARACTERS[character_id].get("relationships", [])]


@router.get("/characters/{character_id}/assets", response_model=List[Dict[str, Any]], operation_id="characters.getAssets")
async def get_character_assets(character_id: str = Path(...)) -> List[Dict[str, Any]]:
    """Retrieve generated visual/voice assets linked to a character."""
    if character_id not in _CHARACTERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    return []
