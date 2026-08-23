"""P1.3 Asset Requirement authority — deterministic requirement extraction.

Separates the two plan-level concepts:

    Asset Requirement ("this production NEEDS an X") from the locked
    screenplay + canon, and the Asset itself (the actual produced media,
    hashed over its real bytes).

Principles (plan §P1.3):
- Deterministic first: requirements are projected from the locked
  screenplay's structured scenes and the existing Character/Location canon —
  no LLM call.
- Idempotent sync: re-running extraction never duplicates or mutates
  existing requirements; it only adds what is genuinely missing.
- Honest limits: music/SFX/reference requirements are only created when a
  structured source actually declares them — none are invented.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Tuple

from windagent_api.services.character_canon_authority import compute_content_hash
from windagent_api.services.preproduction_authority import resolve_locked_screenplay
from windagent_api.services.world_canon_authority import (
    STORY_BIBLE_KIND,
    SCREENPLAY_DRAFT_KIND,
    load_latest_artifacts_of_kind,
    norm_location_name,
    parse_scene_heading,
)
from windagent_api.services.v3_resource_service import V3ResourceService

NS_ASSET_REQUIREMENTS = "asset_requirements"

REQ_TYPE_CHARACTER = "CHARACTER"
REQ_TYPE_ENVIRONMENT = "ENVIRONMENT"
REQ_TYPE_PROP = "PROP"
REQ_TYPE_MUSIC = "MUSIC"
REQ_TYPE_SFX = "SFX"
REQ_TYPE_REFERENCE = "REFERENCE"


def _norm(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


async def build_asset_requirements(
    service: V3ResourceService,
    project_id: str,
    episode_id: str,
    created_at: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Extract (and durably persist missing) asset requirements.

    Returns ``(requirements, lineage)`` where ``requirements`` is the FULL
    project-scoped requirement list after the sync (existing ones untouched).
    Fail closed via :func:`resolve_locked_screenplay` when there is no lock.
    """
    locked = await resolve_locked_screenplay(service, episode_id)

    story_bible = await load_latest_artifacts_of_kind(service, episode_id, STORY_BIBLE_KIND)
    screenplay = await load_latest_artifacts_of_kind(service, episode_id, SCREENPLAY_DRAFT_KIND)

    lineage = {
        "source_series_id": project_id,
        "source_screenplay_revision_id": locked.revision_id,
        "source_story_bible_artifact_id": str((story_bible or {}).get("artifact_id") or ""),
        "locked_content_hash": locked.content_hash,
    }

    # ── Deterministic projections ────────────────────────────────────────
    character_usage: Dict[str, Dict[str, Any]] = {}
    environment_usage: Dict[str, Dict[str, Any]] = {}
    prop_candidates: Dict[str, Dict[str, Any]] = {}

    for scene in ((screenplay or {}).get("content") or {}).get("scenes") or []:
        scene_number = scene.get("scene_number")
        for line in scene.get("dialogue") or []:
            speaker_raw = str(line.get("speaker") or "").strip()
            speaker = _norm(speaker_raw)
            if not speaker:
                continue
            entry = character_usage.setdefault(speaker, {"display_name": speaker_raw, "scenes": []})
            if scene_number not in entry["scenes"]:
                entry["scenes"].append(scene_number)

        parsed = parse_scene_heading(scene.get("heading"))
        if parsed is not None:
            key = norm_location_name(parsed["location_name"])
            if key:
                environment_usage.setdefault(key, {"name": parsed["location_name"], "scenes": []})
                if scene_number not in environment_usage[key]["scenes"]:
                    environment_usage[key]["scenes"].append(scene_number)

    # Props come ONLY from the Location Canon profiles (never guessed from prose).
    locations = [
        loc for loc in await service.list("locations")
        if loc.get("project_id") == project_id
    ]
    loc_by_name = {norm_location_name(loc.get("name")): loc for loc in locations}
    for key, usage in environment_usage.items():
        loc = loc_by_name.get(key)
        if not loc:
            continue
        for prop in loc.get("important_props") or []:
            pkey = _norm(prop)
            entry = prop_candidates.setdefault(
                pkey, {"name": str(prop), "scenes": [], "source_locations": []}
            )
            for scene_number in usage["scenes"]:
                if scene_number not in entry["scenes"]:
                    entry["scenes"].append(scene_number)
            if loc.get("name") not in entry["source_locations"]:
                entry["source_locations"].append(loc.get("name"))

    desired: List[Dict[str, Any]] = []
    # Prefer canon Character names when they match the screenplay speaker.
    canon_names_by_key = {
        _norm(c.get("identity", {}).get("name")): c.get("identity", {}).get("name")
        for c in await service.list("characters")
        if c.get("project_id") == project_id
    }
    for speaker_key, usage in sorted(character_usage.items()):
        display_name = canon_names_by_key.get(speaker_key) or usage["display_name"]
        desired.append(_make_requirement(
            project_id, episode_id, REQ_TYPE_CHARACTER, display_name,
            "Character appearance requirement extracted from locked screenplay dialogue.",
            sorted(usage["scenes"], key=_scene_sort_key), mandatory=True, created_at=created_at,
        ))
    for key, usage in sorted(environment_usage.items()):
        desired.append(_make_requirement(
            project_id, episode_id, REQ_TYPE_ENVIRONMENT, usage["name"],
            "Environment/set requirement extracted from locked screenplay scene headings.",
            sorted(usage["scenes"], key=_scene_sort_key), mandatory=True, created_at=created_at,
        ))
    for key, entry in sorted(prop_candidates.items()):
        desired.append(_make_requirement(
            project_id, episode_id, REQ_TYPE_PROP, entry["name"],
            f"Prop required by Location Canon ({', '.join(entry['source_locations'])}).",
            sorted(entry["scenes"], key=_scene_sort_key), mandatory=False, created_at=created_at,
        ))

    # ── Idempotent merge: only ADD missing requirements ──────────────────
    existing = [
        r for r in await service.list(NS_ASSET_REQUIREMENTS)
        if r.get("project_id") == project_id and r.get("episode_id") == episode_id
    ]
    existing_keys = {(r.get("type"), _norm(r.get("name"))) for r in existing}

    created_now: List[Dict[str, Any]] = []
    for req in desired:
        key = (req["type"], _norm(req["name"]))
        if key in existing_keys:
            continue
        existing_keys.add(key)
        stored = await service.create(NS_ASSET_REQUIREMENTS, req["requirement_id"], req)
        created_now.append(stored)

    all_reqs = [
        r for r in await service.list(NS_ASSET_REQUIREMENTS)
        if r.get("project_id") == project_id and r.get("episode_id") == episode_id
    ]
    all_reqs.sort(key=lambda r: (r.get("type", ""), str(r.get("name", ""))))
    return all_reqs, lineage


def _scene_sort_key(value: Any) -> Tuple[int, str]:
    try:
        return (0, "", int(value))
    except (TypeError, ValueError):
        return (1, str(value), 0)


def _make_requirement(
    project_id: str,
    episode_id: str,
    req_type: str,
    name: str,
    description: str,
    scene_usage: List[Any],
    mandatory: bool,
    created_at: str,
) -> Dict[str, Any]:
    requirement_id = f"areq-{uuid.uuid4().hex[:10]}"
    payload = {
        "requirement_id": requirement_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "type": req_type,
        "name": name,
        "description": description,
        "scene_usage": scene_usage,
        "mandatory": mandatory,
        "status": "OPEN",
        "linked_asset_id": None,
        "content_hash": compute_content_hash({
            "type": req_type,
            "name": _norm(name),
            "scene_usage": [str(s) for s in scene_usage],
        }),
        "created_at": created_at,
        "updated_at": created_at,
    }
    return payload


__all__ = [
    "NS_ASSET_REQUIREMENTS",
    "REQ_TYPE_CHARACTER",
    "REQ_TYPE_ENVIRONMENT",
    "REQ_TYPE_MUSIC",
    "REQ_TYPE_PROP",
    "REQ_TYPE_REFERENCE",
    "REQ_TYPE_SFX",
    "build_asset_requirements",
    "compute_content_hash",
]
