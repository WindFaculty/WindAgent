"""P1.1 Character Canon authority — canonical production characters.

Extends the existing durable Character resource with canon semantics instead
of introducing a duplicate Character model:

    Selected Idea → Story Bible → Locked Screenplay → Character Canon Sync

Principles (plan §P1.1):
- Deterministic first: extraction from the structured Story Bible and locked
  screenplay is a deterministic projection — no LLM call when structured data
  already covers the fields.
- NO SILENT OVERWRITE: sync never mutates canon directly. It produces a
  proposal whose actions are applied through explicit commands.
- Source lineage: every character version knows where it came from
  (series, story bible artifact, screenplay revision, source hash).
- Version pinning: every mutation records an immutable revision with a
  deterministic SHA-256 content hash so a Production Package can pin
  ``character_id + version + content_hash``.
- Readiness gate: PRODUCTION_READY requires name, story role, visual identity
  and continuity constraints (voice is NOT required in P1).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from windagent_api.services.preproduction_authority import (
    PreproductionAuthorityError,
    resolve_locked_screenplay,
)
from windagent_api.services.v3_resource_service import V3ResourceService

STORY_BIBLE_KIND = "StoryBible"
SCREENPLAY_DRAFT_KIND = "ScreenplayDraft"

# Canon lifecycle statuses (plan §P1.1.6).
CHARACTER_STATUS_DRAFT = "DRAFT"
CHARACTER_STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
CHARACTER_STATUS_APPROVED = "APPROVED"
CHARACTER_STATUS_PRODUCTION_READY = "PRODUCTION_READY"
CHARACTER_STATUSES = (
    CHARACTER_STATUS_DRAFT,
    CHARACTER_STATUS_REVIEW_REQUIRED,
    CHARACTER_STATUS_APPROVED,
    CHARACTER_STATUS_PRODUCTION_READY,
)

# Proposal action kinds (plan §P1.1.4).
ACTION_NO_CHANGE = "NO_CHANGE"
ACTION_ADD_CHARACTER = "ADD_CHARACTER"
ACTION_UPDATE_PROPOSED = "UPDATE_PROPOSED"
ACTION_CONFLICT = "CONFLICT"

APPLICABLE_ACTIONS = (ACTION_ADD_CHARACTER, ACTION_UPDATE_PROPOSED)


class CharacterCanonError(PreproductionAuthorityError):
    """Fail-closed error for character canon operations."""


class ProposalNotFoundError(CharacterCanonError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(
            code="CANON_PROPOSAL_NOT_FOUND",
            message=f"Canon sync proposal '{proposal_id}' not found.",
            http_status=404,
        )


class InvalidStatusTransitionError(CharacterCanonError):
    def __init__(self, character_id: str, current: str, target: str) -> None:
        super().__init__(
            code="INVALID_CHARACTER_STATUS_TRANSITION",
            message=(
                f"Character '{character_id}' cannot move from '{current}' to "
                f"'{target}'. Allowed order: DRAFT -> REVIEW_REQUIRED -> "
                "APPROVED -> PRODUCTION_READY."
            ),
            http_status=409,
        )


class NotProductionReadyError(CharacterCanonError):
    def __init__(self, character_id: str, missing: List[str]) -> None:
        super().__init__(
            code="CHARACTER_NOT_PRODUCTION_READY",
            message=(
                f"Character '{character_id}' is not production-ready. Missing: "
                + ", ".join(missing)
                + "."
            ),
            http_status=409,
        )


@dataclass(frozen=True)
class SourceLineage:
    """Where a character version came from (plan §P1.1.3)."""

    source_series_id: str = ""
    source_story_bible_artifact_id: str = ""
    source_screenplay_revision_id: str = ""
    source_hash: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "source_series_id": self.source_series_id,
            "source_story_bible_artifact_id": self.source_story_bible_artifact_id,
            "source_screenplay_revision_id": self.source_screenplay_revision_id,
            "source_hash": self.source_hash,
        }


def compute_content_hash(data: Any) -> str:
    """Deterministic 64-char SHA-256 over canonical JSON of the payload."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_continuity() -> Dict[str, List[str]]:
    return {
        "immutable_features": [],
        "wardrobe_rules": [],
        "allowed_variations": [],
        "forbidden_variations": [],
    }


def _norm_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def extract_characters_from_artifacts(
    story_bible: Optional[Dict[str, Any]],
    screenplay: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Deterministic projection of candidate characters from P0 artifacts.

    The Story Bible's structured ``characters[]`` entries are authoritative;
    screenplay dialogue speakers only confirm which names actually appear on
    screen (no LLM involved).
    """
    if not story_bible:
        return []
    content = story_bible.get("content") or {}
    extracted: List[Dict[str, Any]] = []
    for entry in content.get("characters") or []:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        speakers = _screenplay_speakers(screenplay)
        extracted.append(
            {
                "identity": {
                    "name": name,
                    "story_role": str(entry.get("role") or "Supporting"),
                    "biography": "",
                    "aliases": [str(a) for a in entry.get("aliases", []) if str(a).strip()],
                },
                "personality": {
                    "archetype": str(entry.get("archetype") or ""),
                    "traits": [str(t) for t in entry.get("traits", [])],
                },
                "appears_in_screenplay": not speakers or _norm_name(name) in speakers,
            }
        )
    return extracted


def _screenplay_speakers(screenplay: Optional[Dict[str, Any]]) -> set:
    speakers: set = set()
    if not screenplay:
        return speakers
    for scene in (screenplay.get("content") or {}).get("scenes") or []:
        for line in scene.get("dialogue") or []:
            speaker = _norm_name(str(line.get("speaker") or ""))
            if speaker:
                speakers.add(speaker)
    return speakers


def diff_canon(
    current_characters: List[Dict[str, Any]],
    extracted: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compare extracted candidates against canon and classify each action.

    - NO_CHANGE: canon already carries this identity from the same source.
    - ADD_CHARACTER: new identity absent from canon.
    - UPDATE_PROPOSED: identity exists and its stored sync hash still matches
      the canon content (no manual edit since the last sync).
    - CONFLICT: identity exists but was manually edited after the last sync —
      never overwritten silently.
    """
    by_name = {_norm_name(c["identity"]["name"]): c for c in current_characters}
    actions: List[Dict[str, Any]] = []
    for cand in extracted:
        name = cand["identity"]["name"]
        existing = by_name.get(_norm_name(name))
        if existing is None:
            actions.append(
                {
                    "action": ACTION_ADD_CHARACTER,
                    "character_name": name,
                    "proposed": cand,
                }
            )
            continue

        stored_sync_hash = str(existing.get("last_synced_hash") or "")
        if not stored_sync_hash:
            # Never synced before: any difference is treated as manual authoring.
            actions.append(_update_or_no_change(existing, cand))
            continue

        current_hash = compute_content_hash(_canon_fingerprint(existing))
        if current_hash == stored_sync_hash:
            actions.append(_update_or_no_change(existing, cand))
        else:
            actions.append(
                {
                    "action": ACTION_CONFLICT,
                    "character_name": name,
                    "character_id": existing["id"],
                    "current_version": existing.get("version", 1),
                    "reason": (
                        "Character was modified after its last canon sync; "
                        "manual edits are never overwritten silently."
                    ),
                    "proposed": cand,
                }
            )
    return actions


def _update_or_no_change(existing: Dict[str, Any], cand: Dict[str, Any]) -> Dict[str, Any]:
    changed = _canon_field_changes(existing, cand)
    if not changed:
        return {
            "action": ACTION_NO_CHANGE,
            "character_name": cand["identity"]["name"],
            "character_id": existing["id"],
        }
    return {
        "action": ACTION_UPDATE_PROPOSED,
        "character_name": cand["identity"]["name"],
        "character_id": existing["id"],
        "changed_fields": changed,
        "proposed": cand,
    }


def canon_fingerprint(character: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of canon fields that the sync guard covers.

    Single source of truth for the sync baseline: ``last_synced_hash`` is
    always ``compute_content_hash(canon_fingerprint(...))`` of the same
    character shape, both when a sync applies a proposal and when a later
    sync diffs against canon.

    Durable resources store the psychology section as ``psychology``; extracted
    candidates carry ``personality`` — both shapes are accepted. ``biography``
    is part of the GUARD set (a manual edit after a sync must surface as
    CONFLICT) but is excluded from the proposal diff in
    :func:`_canon_field_changes`, because sync never writes biography.
    """
    identity = character.get("identity") or {}
    psych = character.get("psychology")
    if psych is None:
        psych = character.get("personality")
    psych = psych or {}
    return {
        "identity": {
            "story_role": str(identity.get("role") or identity.get("story_role") or ""),
            "aliases": [str(a) for a in identity.get("aliases", [])],
            "biography": str(identity.get("biography") or ""),
        },
        "personality": {
            "archetype": str(psych.get("archetype") or ""),
            "traits": [str(t) for t in psych.get("traits", [])],
        },
    }


# Internal alias kept for the diff helpers below.
_canon_fingerprint = canon_fingerprint


def _canon_field_changes(
    existing: Dict[str, Any], cand: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    fingerprint = canon_fingerprint(existing)
    proposed_fp = canon_fingerprint(cand)
    # Biography is guarded by the sync hash but never PROPOSED by sync —
    # proposing it would overwrite human narrative with an empty projection.
    comparable = (
        ("identity", "story_role"),
        ("identity", "aliases"),
        ("personality", "archetype"),
        ("personality", "traits"),
    )
    changes: Dict[str, Dict[str, Any]] = {}
    for section, key in comparable:
        current_value = fingerprint[section].get(key)
        proposed_value = proposed_fp[section].get(key)
        differs = (
            list(current_value or []) != list(proposed_value or [])
            if isinstance(proposed_value, list)
            else current_value != proposed_value
        )
        if differs:
            changes[f"{section}.{key}"] = {
                "current": current_value,
                "proposed": proposed_value,
            }
    return changes


async def load_latest_artifacts_of_kind(
    service: V3ResourceService, episode_id: str, kind: str
) -> Optional[Dict[str, Any]]:
    """Latest artifact of ``kind`` for an episode (read-only), newest first."""
    artifacts = await service.list("episode_artifacts")
    matching = [
        a for a in artifacts if a.get("episode_id") == episode_id and a.get("kind") == kind
    ]
    if not matching:
        return None
    matching.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
    return matching[0]


async def build_canon_sync_proposal(
    service: V3ResourceService,
    project_id: str,
    episode_id: str,
    proposal_id: str,
    created_at: str,
) -> Tuple[Dict[str, Any], SourceLineage]:
    """Build (and persist) a canon-sync proposal from the locked screenplay.

    Fail closed via :func:`resolve_locked_screenplay` when the episode has no
    locked screenplay — a sync without real lineage must never run.
    """
    locked = await resolve_locked_screenplay(service, episode_id)

    story_bible = await load_latest_artifacts_of_kind(service, episode_id, STORY_BIBLE_KIND)
    screenplay = await load_latest_artifacts_of_kind(service, episode_id, SCREENPLAY_DRAFT_KIND)

    extracted = extract_characters_from_artifacts(story_bible, screenplay)
    characters = await service.list("characters")
    project_characters = [c for c in characters if c.get("project_id") == project_id]
    actions = diff_canon(project_characters, extracted)

    lineage = SourceLineage(
        source_series_id=project_id,
        source_story_bible_artifact_id=str((story_bible or {}).get("artifact_id") or ""),
        source_screenplay_revision_id=locked.revision_id,
        source_hash=compute_content_hash(
            {
                "story_bible": story_bible.get("content") if story_bible else None,
                "screenplay_scenes": (screenplay or {}).get("revision_id"),
                "locked": {
                    "revision_id": locked.revision_id,
                    "content_hash": locked.content_hash,
                },
            }
        ),
    )

    counts = {a: 0 for a in (ACTION_NO_CHANGE, ACTION_ADD_CHARACTER, ACTION_UPDATE_PROPOSED, ACTION_CONFLICT)}
    for act in actions:
        counts[act["action"]] += 1

    proposal = {
        "proposal_id": proposal_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "domain": "characters",
        "status": "PROPOSED",
        "summary": counts,
        "actions": actions,
        "lineage": lineage.to_dict(),
        "created_at": created_at,
        "updated_at": created_at,
    }
    await service.create("canon_sync_proposals", proposal_id, proposal)
    return proposal, lineage


def readiness_missing(character: Dict[str, Any]) -> List[str]:
    """Fields required for PRODUCTION_READY (plan §P1.1.6).

    name, story role, visual identity, continuity constraints. Voice is NOT
    required in P1.
    """
    missing: List[str] = []
    identity = character.get("identity") or {}
    visual = character.get("visual_profile") or {}
    continuity = character.get("continuity") or {}
    if not str(identity.get("name") or "").strip():
        missing.append("identity.name")
    role = str(identity.get("role") or identity.get("story_role") or "").strip()
    if not role or role.lower() == "draft":
        missing.append("identity.story_role")
    if not str(visual.get("physical_description") or "").strip():
        missing.append("visual_profile.physical_description")
    has_constraints = bool(continuity.get("immutable_features")) or bool(
        continuity.get("wardrobe_rules")
    )
    if not has_constraints:
        missing.append("continuity constraints")
    return missing


__all__ = [
    "ACTION_ADD_CHARACTER",
    "ACTION_CONFLICT",
    "ACTION_NO_CHANGE",
    "ACTION_UPDATE_PROPOSED",
    "APPLICABLE_ACTIONS",
    "CharacterCanonError",
    "InvalidStatusTransitionError",
    "NotProductionReadyError",
    "ProposalNotFoundError",
    "SourceLineage",
    "build_canon_sync_proposal",
    "compute_content_hash",
    "default_continuity",
    "diff_canon",
    "extract_characters_from_artifacts",
    "readiness_missing",
]
