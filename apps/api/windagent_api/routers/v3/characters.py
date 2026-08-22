"""
V3 Characters Router — Canonical Character Management for Story Production Domain.
Provides CRUD, relationship graph, and character assets per project.

Phase 4: characters are persisted through the namespaced durable V3 resource
authority with durable idempotency. No module-level RAM stores.

P1.1 Character Canon: the CRUD resource carries the canonical production
profile (identity/personality/visual/voice/continuity/relationships), source
lineage per version, immutable revisions with deterministic content hashes,
a DRAFT -> REVIEW_REQUIRED -> APPROVED -> PRODUCTION_READY readiness ladder,
and a fail-closed Canon Sync that proposes changes from the locked screenplay
without ever overwriting manual edits.
"""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.character_canon_authority import (
    APPLICABLE_ACTIONS,
    ACTION_ADD_CHARACTER,
    ACTION_CONFLICT,
    ACTION_NO_CHANGE,
    ACTION_UPDATE_PROPOSED,
    CHARACTER_STATUSES,
    CHARACTER_STATUS_DRAFT,
    CHARACTER_STATUS_PRODUCTION_READY,
    CHARACTER_STATUS_REVIEW_REQUIRED,
    build_canon_sync_proposal,
    canon_fingerprint,
    compute_content_hash,
    default_continuity,
    readiness_missing,
)
from windagent_api.services.preproduction_authority import (
    EpisodeNotFoundError,
    PreproductionAuthorityError,
    ScreenplayNotLockedError,
)
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_CHARACTERS

router = APIRouter(prefix="/api/v3", tags=["Characters V3"])

NS_CHARACTER_REVISIONS = "character_revisions"
NS_CANON_SYNC = "canon_sync_proposals"


class CharacterIdentity(BaseModel):
    name: str
    role: str = "Supporting"
    biography: str = ""
    aliases: List[str] = Field(default_factory=list)


class CharacterPsychology(BaseModel):
    dominant_trait: str = ""
    flaw: str = ""
    alignment_score: int = 50
    traits: List[str] = Field(default_factory=list)
    archetype: str = ""
    motivation: str = ""
    goal: str = ""
    fears: List[str] = Field(default_factory=list)


class CharacterVisualProfile(BaseModel):
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    physical_description: str = ""
    style_notes: str = ""
    body_type: str = ""
    age_appearance: str = ""
    hair: str = ""
    clothing: str = ""
    colors: List[str] = Field(default_factory=list)
    distinguishing_features: List[str] = Field(default_factory=list)


class CharacterVoiceProfile(BaseModel):
    voice_model_id: Optional[str] = None
    voice_style: str = ""
    sample_lines: List[str] = Field(default_factory=list)
    age_range: str = ""
    speaking_style: str = ""


class CharacterContinuity(BaseModel):
    immutable_features: List[str] = Field(default_factory=list)
    wardrobe_rules: List[str] = Field(default_factory=list)
    allowed_variations: List[str] = Field(default_factory=list)
    forbidden_variations: List[str] = Field(default_factory=list)


class CharacterRelationship(BaseModel):
    target_character_id: str
    target_name: str
    relationship_type: str = "Ally"


class CharacterSourceLineage(BaseModel):
    source_series_id: str = ""
    source_story_bible_artifact_id: str = ""
    source_screenplay_revision_id: str = ""
    source_hash: str = ""


class CharacterResource(BaseModel):
    id: str
    project_id: str
    identity: CharacterIdentity
    psychology: CharacterPsychology
    visual_profile: CharacterVisualProfile
    voice_profile: CharacterVoiceProfile
    continuity: CharacterContinuity
    relationships: List[CharacterRelationship] = Field(default_factory=list)
    status: str = CHARACTER_STATUS_DRAFT
    source_lineage: CharacterSourceLineage
    current_revision_id: Optional[str] = None
    content_hash: Optional[str] = None
    last_synced_hash: Optional[str] = None
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
    aliases: List[str] = Field(default_factory=list)
    physical_description: str = ""
    immutable_features: List[str] = Field(default_factory=list)
    wardrobe_rules: List[str] = Field(default_factory=list)


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    role: Optional[str] = None
    biography: Optional[str] = None
    dominant_trait: Optional[str] = None
    flaw: Optional[str] = None
    alignment_score: Optional[int] = Field(None, ge=0, le=100)
    voice_model_id: Optional[str] = None
    voice_style: Optional[str] = None
    # P1.1 canonical profile extensions.
    aliases: Optional[List[str]] = None
    traits: Optional[List[str]] = None
    motivation: Optional[str] = None
    goal: Optional[str] = None
    fears: Optional[List[str]] = None
    physical_description: Optional[str] = None
    body_type: Optional[str] = None
    age_appearance: Optional[str] = None
    hair: Optional[str] = None
    clothing: Optional[str] = None
    colors: Optional[List[str]] = None
    distinguishing_features: Optional[List[str]] = None
    style_notes: Optional[str] = None
    voice_age_range: Optional[str] = None
    speaking_style: Optional[str] = None
    immutable_features: Optional[List[str]] = None
    wardrobe_rules: Optional[List[str]] = None
    allowed_variations: Optional[List[str]] = None
    forbidden_variations: Optional[List[str]] = None
    expected_version: int = Field(..., description="Optimistic locking version")


class SetCharacterStatusRequest(BaseModel):
    status: str = Field(..., description="One of: " + ", ".join(CHARACTER_STATUSES))
    expected_version: int = Field(..., description="Optimistic locking version")


class CanonSyncActionApplyRequest(BaseModel):
    action_index: int = Field(..., ge=0, description="Index into the proposal's actions[]")


def _char_to_resource(c: Dict[str, Any]) -> CharacterResource:
    return CharacterResource(
        id=c["id"],
        project_id=c["project_id"],
        identity=CharacterIdentity(**c["identity"]),
        psychology=CharacterPsychology(**c["psychology"]),
        visual_profile=CharacterVisualProfile(**c["visual_profile"]),
        voice_profile=CharacterVoiceProfile(**c["voice_profile"]),
        continuity=CharacterContinuity(**(c.get("continuity") or default_continuity())),
        relationships=[CharacterRelationship(**r) for r in c.get("relationships", [])],
        status=c.get("status", CHARACTER_STATUS_DRAFT),
        source_lineage=CharacterSourceLineage(**(c.get("source_lineage") or {})),
        current_revision_id=c.get("current_revision_id"),
        content_hash=c.get("content_hash"),
        last_synced_hash=c.get("last_synced_hash"),
        version=c.get("version", 1),
        created_at=c.get("created_at", ""),
        updated_at=c.get("updated_at", ""),
    )


def _canon_sections(
    *,
    name: str,
    role: str,
    biography: str,
    dominant_trait: str,
    flaw: str,
    alignment_score: int,
    aliases: Optional[List[str]] = None,
    physical_description: str = "",
    immutable_features: Optional[List[str]] = None,
    wardrobe_rules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "identity": {"name": name, "role": role, "biography": biography, "aliases": list(aliases or [])},
        "psychology": {
            "dominant_trait": dominant_trait,
            "flaw": flaw,
            "alignment_score": alignment_score,
            "traits": [],
            "archetype": "",
            "motivation": "",
            "goal": "",
            "fears": [],
        },
        "visual_profile": {
            "avatar_url": None,
            "banner_url": None,
            "physical_description": physical_description,
            "style_notes": "",
            "body_type": "",
            "age_appearance": "",
            "hair": "",
            "clothing": "",
            "colors": [],
            "distinguishing_features": [],
        },
        "voice_profile": {
            "voice_model_id": None,
            "voice_style": "",
            "sample_lines": [],
            "age_range": "",
            "speaking_style": "",
        },
        "continuity": {
            **default_continuity(),
            "immutable_features": list(immutable_features or []),
            "wardrobe_rules": list(wardrobe_rules or []),
        },
    }


async def _record_revision(service: V3ResourceService, char: Dict[str, Any], lineage: Dict[str, Any]) -> Dict[str, Any]:
    """Persist an immutable revision pinning the character's current state."""
    revision_id = f"charrev-{char['id']}-v{char.get('version', 1)}"
    snapshot = {k: v for k, v in char.items() if k not in ("relationships",)}
    revision = {
        "revision_id": revision_id,
        "character_id": char["id"],
        # NB: named ``character_version`` because the durable store reserves
        # ``version`` for the resource row's own optimistic-locking counter.
        "character_version": char.get("version", 1),
        "content_hash": char.get("content_hash"),
        "source_lineage": dict(lineage or {}),
        "snapshot": snapshot,
        "created_at": char.get("updated_at", ""),
    }
    existing = await service.get(NS_CHARACTER_REVISIONS, revision_id)
    if existing is None:
        await service.create(NS_CHARACTER_REVISIONS, revision_id, revision)
    else:
        await service.update(NS_CHARACTER_REVISIONS, revision_id, revision, existing.get("version", 1))
    return revision


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
        chars = [
            c for c in chars
            if s in c["identity"]["name"].lower()
            or s in (c["identity"].get("role") or "").lower()
        ]
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
    sections = _canon_sections(
        name=body.name,
        role=body.role,
        biography=body.biography,
        dominant_trait=body.dominant_trait,
        flaw=body.flaw,
        alignment_score=body.alignment_score,
        aliases=body.aliases,
        physical_description=body.physical_description,
        immutable_features=body.immutable_features,
        wardrobe_rules=body.wardrobe_rules,
    )
    fingerprint = {k: v for k, v in sections.items() if k != "continuity"}
    new_char: Dict[str, Any] = {
        "id": char_id,
        "project_id": project_id,
        **sections,
        "relationships": [],
        "status": CHARACTER_STATUS_DRAFT,
        "source_lineage": {},
        "current_revision_id": f"charrev-{char_id}-v1",
        "last_synced_hash": None,
        "created_at": now,
        "updated_at": now,
    }
    new_char["content_hash"] = compute_content_hash(fingerprint)
    created = await service.create(NS_CHARACTERS, char_id, new_char, idempotency_key)
    await _record_revision(service, created, created.get("source_lineage") or {})
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
    """Update character fields with optimistic concurrency check.

    P1.1: every manual edit bumps the version and records an immutable
    revision with a fresh deterministic content hash. ``last_synced_hash`` is
    deliberately left untouched — the next canon sync recomputes the guard
    fingerprint and detects the drift against the stored baseline, which
    classifies the character as CONFLICT instead of overwriting it.
    """
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
    visual_profile = dict(curr["visual_profile"])
    voice_profile = dict(curr["voice_profile"])
    continuity = dict(curr.get("continuity") or default_continuity())
    if body.name is not None:
        identity["name"] = body.name
    if body.role is not None:
        identity["role"] = body.role
    if body.biography is not None:
        identity["biography"] = body.biography
    if body.aliases is not None:
        identity["aliases"] = body.aliases
    if body.dominant_trait is not None:
        psychology["dominant_trait"] = body.dominant_trait
    if body.flaw is not None:
        psychology["flaw"] = body.flaw
    if body.alignment_score is not None:
        psychology["alignment_score"] = body.alignment_score
    if body.traits is not None:
        psychology["traits"] = body.traits
    if body.motivation is not None:
        psychology["motivation"] = body.motivation
    if body.goal is not None:
        psychology["goal"] = body.goal
    if body.fears is not None:
        psychology["fears"] = body.fears
    if body.physical_description is not None:
        visual_profile["physical_description"] = body.physical_description
    if body.body_type is not None:
        visual_profile["body_type"] = body.body_type
    if body.age_appearance is not None:
        visual_profile["age_appearance"] = body.age_appearance
    if body.hair is not None:
        visual_profile["hair"] = body.hair
    if body.clothing is not None:
        visual_profile["clothing"] = body.clothing
    if body.colors is not None:
        visual_profile["colors"] = body.colors
    if body.distinguishing_features is not None:
        visual_profile["distinguishing_features"] = body.distinguishing_features
    if body.style_notes is not None:
        visual_profile["style_notes"] = body.style_notes
    if body.voice_model_id is not None:
        voice_profile["voice_model_id"] = body.voice_model_id
    if body.voice_style is not None:
        voice_profile["voice_style"] = body.voice_style
    if body.voice_age_range is not None:
        voice_profile["age_range"] = body.voice_age_range
    if body.speaking_style is not None:
        voice_profile["speaking_style"] = body.speaking_style
    if body.immutable_features is not None:
        continuity["immutable_features"] = body.immutable_features
    if body.wardrobe_rules is not None:
        continuity["wardrobe_rules"] = body.wardrobe_rules
    if body.allowed_variations is not None:
        continuity["allowed_variations"] = body.allowed_variations
    if body.forbidden_variations is not None:
        continuity["forbidden_variations"] = body.forbidden_variations
    updates["identity"] = identity
    updates["psychology"] = psychology
    updates["visual_profile"] = visual_profile
    updates["voice_profile"] = voice_profile
    updates["continuity"] = continuity
    now = utc_now().isoformat()
    updates["updated_at"] = now

    fingerprint = {
        "identity": updates["identity"],
        "psychology": updates["psychology"],
        "visual_profile": updates["visual_profile"],
        "voice_profile": updates["voice_profile"],
    }
    updates["content_hash"] = compute_content_hash(fingerprint)
    # last_synced_hash is intentionally NOT cleared here: drift is detected by
    # comparing the recomputed guard fingerprint against the stored baseline,
    # so a later sync classifies this character as CONFLICT — never overwrite.

    updated = await service.update(NS_CHARACTERS, character_id, updates, body.expected_version)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for character '{character_id}'.")
    await _record_revision(service, updated, updated.get("source_lineage") or {})
    return _char_to_resource(updated)


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="characters.delete")
async def delete_character(
    character_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> None:
    """Delete a character by ID."""
    await service.delete(NS_CHARACTERS, character_id)


@router.get("/characters/{character_id}/revisions", response_model=List[Dict[str, Any]], operation_id="characters.listRevisions")
async def list_character_revisions(
    character_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[Dict[str, Any]]:
    """Immutable version history of a character (P1.1 version pinning)."""
    char = await service.get(NS_CHARACTERS, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    revisions = await service.list(NS_CHARACTER_REVISIONS)
    own = [r for r in revisions if r.get("character_id") == character_id]
    # NOTE: revision records store ``character_version`` (the bare ``version``
    # key is reserved by the durable resource authority for optimistic locking
    # and is filtered out of persisted payloads).
    own.sort(key=lambda r: int(r.get("character_version", 0)))
    return own


@router.post("/characters/{character_id}/actions/set-status", response_model=CharacterResource, operation_id="characters.setStatus")
async def set_character_status(
    character_id: str = Path(...),
    body: SetCharacterStatusRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> CharacterResource:
    """Advance the canon readiness ladder (plan §P1.1.6).

    DRAFT -> REVIEW_REQUIRED -> APPROVED -> PRODUCTION_READY. Moving to
    PRODUCTION_READY fails closed until name, story role, visual identity and
    continuity constraints are all present.
    """
    char = await service.get(NS_CHARACTERS, character_id)
    if char is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character '{character_id}' not found.")
    if char["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for character '{character_id}'. Expected {char['version']}, got {body.expected_version}.",
        )
    if body.status not in CHARACTER_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown character status '{body.status}'.")

    order = list(CHARACTER_STATUSES)
    current_idx = order.index(char.get("status", CHARACTER_STATUS_DRAFT))
    target_idx = order.index(body.status)
    if target_idx != current_idx + 1 and target_idx != current_idx:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "INVALID_CHARACTER_STATUS_TRANSITION",
                "message": (
                    f"Cannot move '{character_id}' from '{char.get('status')}' to "
                    f"'{body.status}'; statuses advance one step at a time."
                ),
            },
        )
    if target_idx == current_idx and body.status == char.get("status"):
        return _char_to_resource(char)

    if body.status == CHARACTER_STATUS_PRODUCTION_READY:
        missing = readiness_missing(char)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "CHARACTER_NOT_PRODUCTION_READY",
                    "message": f"Character '{character_id}' is not production-ready. Missing: " + ", ".join(missing) + ".",
                    "missing_fields": missing,
                },
            )

    updates = dict(char)
    updates["status"] = body.status
    updates["updated_at"] = utc_now().isoformat()
    updated = await service.update(NS_CHARACTERS, character_id, updates, char["version"])
    if updated is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version conflict for character '{character_id}'.")
    # Status transitions are mutations too: pin an immutable revision so the
    # PRODUCTION_READY state can be referenced by a Production Package.
    await _record_revision(service, updated, updated.get("source_lineage") or {})
    return _char_to_resource(updated)


@router.post("/episodes/{episode_id}/characters/actions/canon-sync", response_model=Dict[str, Any], operation_id="characters.canonSync")
async def canon_sync_characters(
    episode_id: str = Path(...),
    project_id: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Propose character canon changes from the episode's locked screenplay.

    Fail closed with 409 SCREENPLAY_NOT_LOCKED when there is no locked
    screenplay. Never mutates canon directly — the returned proposal must be
    applied through explicit apply commands.
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

    proposal_id = f"cansync-{uuid.uuid4().hex[:10]}"
    try:
        proposal, _lineage = await build_canon_sync_proposal(
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


@router.get("/canon-sync/{proposal_id}", response_model=Dict[str, Any], operation_id="characters.getCanonSyncProposal")
async def get_canon_sync_proposal(
    proposal_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    proposal = await service.get(NS_CANON_SYNC, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANON_PROPOSAL_NOT_FOUND", "message": f"Canon sync proposal '{proposal_id}' not found."},
        )
    return proposal


@router.post("/canon-sync/{proposal_id}/apply", response_model=Dict[str, Any], operation_id="characters.applyCanonSyncAction")
async def apply_canon_sync_action(
    proposal_id: str = Path(...),
    body: CanonSyncActionApplyRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Apply one proposed action (ADD_CHARACTER | UPDATE_PROPOSED).

    Applying an ADD creates the character pinned to the proposal's lineage;
    applying an UPDATE advances the existing character to a new revision and
    refreshes its sync baseline. NO_CHANGE and CONFLICT actions are not
    applicable.
    """
    proposal = await service.get(NS_CANON_SYNC, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "CANON_PROPOSAL_NOT_FOUND", "message": f"Canon sync proposal '{proposal_id}' not found."},
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
                    "CONFLICT actions require a manual resolution; canon sync never "
                    "overwrites manual edits."
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
    proposed_identity = proposed.get("identity") or {}
    now = utc_now().isoformat()

    if kind == ACTION_ADD_CHARACTER:
        char_id = f"char-{uuid.uuid4().hex[:8]}"
        sections = _canon_sections(
            name=str(proposed_identity.get("name") or ""),
            role=str(proposed_identity.get("story_role") or "Supporting"),
            biography="",
            dominant_trait="",
            flaw="",
            alignment_score=50,
            aliases=[str(a) for a in proposed_identity.get("aliases", [])],
        )
        personality = dict(sections["psychology"])
        personality.update(proposed.get("personality") or {})
        sections["psychology"] = personality
        new_char: Dict[str, Any] = {
            "id": char_id,
            "project_id": proposal["project_id"],
            **sections,
            "relationships": [],
            "status": CHARACTER_STATUS_REVIEW_REQUIRED,
            "source_lineage": lineage,
            "last_synced_hash": None,
            "created_at": now,
            "updated_at": now,
        }
        new_char["last_synced_hash"] = compute_content_hash(canon_fingerprint(new_char))
        new_char["content_hash"] = compute_content_hash(
            {k: v for k, v in new_char.items() if k in ("identity", "psychology", "visual_profile", "voice_profile")}
        )
        new_char["current_revision_id"] = f"charrev-{char_id}-v1"
        created = await service.create(NS_CHARACTERS, char_id, new_char)
        applied_revision = await _record_revision(service, created, lineage)
        result_resource = _char_to_resource(created).model_dump()
        result_kind = ACTION_ADD_CHARACTER
    else:  # UPDATE_PROPOSED
        char_id = str(action.get("character_id") or "")
        curr = await service.get(NS_CHARACTERS, char_id)
        if curr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "CHARACTER_NOT_FOUND", "message": f"Character '{char_id}' not found."},
            )
        updates = dict(curr)
        identity = dict(curr["identity"])
        identity["role"] = str(proposed_identity.get("story_role") or identity.get("role") or "")
        identity["aliases"] = [str(a) for a in proposed_identity.get("aliases", [])]
        personality = dict(curr["psychology"])
        personality.update(proposed.get("personality") or {})
        updates["identity"] = identity
        updates["psychology"] = personality
        updates["updated_at"] = now
        fingerprint = {
            "identity": updates["identity"],
            "psychology": updates["psychology"],
            "visual_profile": updates["visual_profile"],
            "voice_profile": updates["voice_profile"],
        }
        updates["content_hash"] = compute_content_hash(fingerprint)
        merged_lineage = dict(curr.get("source_lineage") or {})
        merged_lineage.update({k: v for k, v in lineage.items() if v})
        updates["source_lineage"] = merged_lineage
        updates["last_synced_hash"] = compute_content_hash(canon_fingerprint(updates))
        updated = await service.update(NS_CHARACTERS, char_id, updates, curr["version"])
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "VERSION_CONFLICT", "message": f"Version conflict updating character '{char_id}'."},
            )
        applied_revision = await _record_revision(service, updated, merged_lineage)
        result_resource = _char_to_resource(updated).model_dump()
        result_kind = ACTION_UPDATE_PROPOSED

    # Mark the action applied inside the durable proposal record.
    actions[body.action_index] = {**action, "applied": True, "applied_revision_id": applied_revision["revision_id"]}
    remaining = [a for a in actions if not a.get("applied") and a.get("action") in APPLICABLE_ACTIONS]
    proposal_updates = dict(proposal)
    proposal_updates["actions"] = actions
    proposal_updates["status"] = "APPLIED" if not remaining else "PARTIALLY_APPLIED"
    proposal_updates["updated_at"] = now
    await service.update(NS_CANON_SYNC, proposal_id, proposal_updates, proposal.get("version", 1))

    return {
        "proposal_id": proposal_id,
        "applied_action": result_kind,
        "revision": applied_revision,
        "character": result_resource,
        "proposal_status": proposal_updates["status"],
    }


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
    assets = await service.list("assets")
    return [a for a in assets if a.get("character_id") == character_id]
