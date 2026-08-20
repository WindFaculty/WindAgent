"""
V3 Characters Router — Canonical Character Management for Story Production Domain.
Provides CRUD, relationship graph, and character assets per project.

Phase 4: characters are persisted through the namespaced durable V3 resource
authority with durable idempotency. No module-level RAM stores.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_CHARACTERS

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


def _char_to_resource(c: Dict[str, Any]) -> CharacterResource:
    return CharacterResource(
        id=c["id"],
        project_id=c["project_id"],
        identity=CharacterIdentity(**c["identity"]),
        psychology=CharacterPsychology(**c["psychology"]),
        visual_profile=CharacterVisualProfile(**c["visual_profile"]),
        voice_profile=CharacterVoiceProfile(**c["voice_profile"]),
        relationships=[CharacterRelationship(**r) for r in c.get("relationships", [])],
        version=c.get("version", 1),
        created_at=c.get("created_at", ""),
        updated_at=c.get("updated_at", ""),
    )


@router.get("/projects/{project_id}/characters", response_model=List[CharacterResource], operation_id="characters.listForProject")
async def list_project_characters(
    project_id: str = Path(...),
    search: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[CharacterResource]:
    """List all characters belonging to a project."""
    chars = await service.list(NS_CHARACTERS)
    chars = [c for c in chars if c.get("project_id") == project_id]
    if search:
        s = search.lower()
        chars = [c for c in chars if s in c["identity"]["name"].lower() or s in c["identity"]["role"].lower()]
    return [_char_to_resource(c) for c in chars]


@router.post("/projects/{project_id}/characters", response_model=CharacterResource, status_code=status.HTTP_201_CREATED, operation_id="characters.create")
async def create_character(
    project_id: str = Path(...),
    body: CreateCharacterRequest = ...,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> CharacterResource:
    """Create a new character in a project with idempotency support."""
    if idempotency_key:
        existing = await service.find_by_idempotency(NS_CHARACTERS, idempotency_key)
        if existing is not None:
            return _char_to_resource(existing)

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
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_CHARACTERS, char_id, new_char, idempotency_key)
    return _char_to_resource(created)


@router.get("/characters/{character_id}", response_model=CharacterResource, operation_id="characters.get")
async def get_character(
    character_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> CharacterResource:
    """Retrieve full character detail by ID."""
    char = await service.get(NS_CHARACTERS, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    return _char_to_resource(char)


@router.patch("/characters/{character_id}", response_model=CharacterResource, operation_id="characters.update")
async def update_character(
    character_id: str = Path(...),
    body: UpdateCharacterRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> CharacterResource:
    """Update character fields with optimistic concurrency check."""
    curr = await service.get(NS_CHARACTERS, character_id)
    if curr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")

    if curr["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for character '{character_id}'. Expected {curr['version']}, got {body.expected_version}.",
        )

    updates = dict(curr)
    identity = dict(curr["identity"])
    psychology = dict(curr["psychology"])
    voice_profile = dict(curr["voice_profile"])
    if body.name is not None:
        identity["name"] = body.name
    if body.role is not None:
        identity["role"] = body.role
    if body.biography is not None:
        identity["biography"] = body.biography
    if body.dominant_trait is not None:
        psychology["dominant_trait"] = body.dominant_trait
    if body.flaw is not None:
        psychology["flaw"] = body.flaw
    if body.alignment_score is not None:
        psychology["alignment_score"] = body.alignment_score
    if body.voice_model_id is not None:
        voice_profile["voice_model_id"] = body.voice_model_id
    if body.voice_style is not None:
        voice_profile["voice_style"] = body.voice_style
    updates["identity"] = identity
    updates["psychology"] = psychology
    updates["voice_profile"] = voice_profile
    updates["updated_at"] = utc_now().isoformat()

    updated = await service.update(NS_CHARACTERS, character_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for character '{character_id}'.")
    return _char_to_resource(updated)


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="characters.delete")
async def delete_character(
    character_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> None:
    """Delete a character by ID."""
    await service.delete(NS_CHARACTERS, character_id)


@router.get("/characters/{character_id}/relationships", response_model=List[CharacterRelationship], operation_id="characters.getRelationships")
async def get_character_relationships(
    character_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[CharacterRelationship]:
    """Retrieve the relationship graph for a character."""
    char = await service.get(NS_CHARACTERS, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    return [CharacterRelationship(**r) for r in char.get("relationships", [])]


@router.get("/characters/{character_id}/assets", response_model=List[Dict[str, Any]], operation_id="characters.getAssets")
async def get_character_assets(
    character_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[Dict[str, Any]]:
    """Retrieve generated visual/voice assets linked to a character."""
    char = await service.get(NS_CHARACTERS, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    return []
