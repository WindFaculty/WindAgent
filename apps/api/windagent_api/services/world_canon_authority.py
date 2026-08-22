"""P1.2 World Canon authority — production world bible and locations.

Extends the durable World Bible / Location resources with canon semantics:

    Locked Screenplay + Story Bible → World Canon Sync → Continuity Check

Principles (plan §P1.2):
- Deterministic first: scene headings are parsed with a strict screenplay
  heading grammar; no LLM call is involved in extraction or checking.
- NO SILENT OVERWRITE: sync produces proposals applied through explicit
  commands; manual edits surface as CONFLICT via the same guard-hash
  mechanism as Character Canon (plan §P1.1).
- Continuity checker NEVER mutates anything — it only reports findings:
  UNKNOWN_LOCATION, WORLD_RULE_CONFLICT, TIMELINE_CONFLICT,
  LOCATION_CONTINUITY_CONFLICT.
- Honest limits: a rule that carries no machine-checkable constraint cannot
  produce a WORLD_RULE_CONFLICT finding — it is reported as unverified
  instead of fabricating a violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from windagent_api.services.character_canon_authority import (
    ACTION_ADD_CHARACTER,
    ACTION_CONFLICT,
    ACTION_NO_CHANGE,
    ACTION_UPDATE_PROPOSED,
    PreproductionAuthorityError,
    compute_content_hash,
)
from windagent_api.services.preproduction_authority import resolve_locked_screenplay
from windagent_api.services.v3_resource_service import V3ResourceService

# Proposal action kinds reuse the character canon vocabulary with a
# location-specific ADD kind.
ACTION_ADD_LOCATION = "ADD_LOCATION"

APPLICABLE_ACTIONS = (ACTION_ADD_LOCATION, ACTION_UPDATE_PROPOSED)

STORY_BIBLE_KIND = "StoryBible"
SCREENPLAY_DRAFT_KIND = "ScreenplayDraft"

# Machine-readable continuity constraint shape: {"statement": str,
# "forbidden_terms": [str]}. Plain-string rules stay human-only.
FORBIDDEN_TERMS_KEY = "forbidden_terms"

_HEADING_RE = re.compile(
    r"^\s*(INT\.?|EXT\.?|INT\./EXT\.|I/E\.?)\s+(?P<name>.+?)\s*[-–—]\s*(?P<time>\S+)\s*$",
    re.IGNORECASE,
)

_NIGHT_TOKENS = {"đêm", "dem", "night"}
_DAY_TOKENS = {"ngày", "ngay", "day", "sáng", "sang", "morning", "chiều", "chieu", "afternoon"}
_DUSK_TOKENS = {"hoàng hôn", "hoang hon", "dusk", "twilight", "hoànghôn"}
_TIME_RESOLUTION = {
    **{token: "NIGHT" for token in _NIGHT_TOKENS},
    **{token: "DAY" for token in _DAY_TOKENS},
    **{token: "DUSK" for token in _DUSK_TOKENS},
}


class WorldCanonError(PreproductionAuthorityError):
    """Fail-closed error for world canon operations."""


class WorldProposalNotFoundError(WorldCanonError):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(
            code="WORLD_PROPOSAL_NOT_FOUND",
            message=f"World sync proposal '{proposal_id}' not found.",
            http_status=404,
        )


def norm_location_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def parse_scene_heading(heading: str) -> Optional[Dict[str, Any]]:
    """Deterministic parse of a screenplay scene heading.

    ``INT./EXT. LOCATION NAME - TIME`` → dict(interior, location_name,
    time_of_day). Returns ``None`` for headings that do not follow the
    grammar (never guesses).
    """
    match = _HEADING_RE.match(str(heading or ""))
    if match is None:
        return None
    slug = match.group(1).upper()
    if slug.startswith("I/E") or "/" in slug:
        interior: Optional[bool] = None  # both interior and exterior
    elif slug.startswith("INT"):
        interior = True
    else:
        interior = False
    time_raw = match.group("time").strip().lower()
    return {
        "interior": interior,
        "location_name": match.group("name").strip(),
        "time_of_day": _TIME_RESOLUTION.get(time_raw),
        "time_raw": match.group("time").strip(),
    }


def extract_locations_from_screenplay(screenplay: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unique candidate locations projected from parsed scene headings."""
    candidates: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for scene in ((screenplay or {}).get("content") or {}).get("scenes") or []:
        parsed = parse_scene_heading(scene.get("heading"))
        if parsed is None:
            continue
        key = norm_location_name(parsed["location_name"])
        if not key:
            continue
        if key not in candidates:
            candidates[key] = {
                "name": parsed["location_name"],
                "interior": parsed["interior"],
                "times_used": [],
                "scene_numbers": [scene.get("scene_number")],
            }
            order.append(key)
        else:
            candidates[key]["scene_numbers"].append(scene.get("scene_number"))
        if parsed["time_of_day"] and parsed["time_of_day"] not in candidates[key]["times_used"]:
            candidates[key]["times_used"].append(parsed["time_of_day"])
    return [candidates[key] for key in order]


def extract_world_facts(story_bible: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic world facts from the Story Bible (may be empty)."""
    content = (story_bible or {}).get("content") or {}
    return {
        "world_rules_text": str(content.get("world_rules") or ""),
        "theme": str(content.get("theme") or ""),
    }


def location_fingerprint(location: Dict[str, Any]) -> Dict[str, Any]:
    """Guard subset for the location sync baseline (same scheme as §P1.1)."""
    return {
        "name": str(location.get("name") or ""),
        "interior": location.get("interior"),
        "atmosphere": str(location.get("atmosphere") or ""),
        "description": str(location.get("description") or ""),
    }


@dataclass(frozen=True)
class WorldSyncLineage:
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


def diff_locations(
    existing_locations: List[Dict[str, Any]],
    extracted: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Classify per-candidate actions against the durable location canon."""
    by_name = {norm_location_name(loc.get("name")): loc for loc in existing_locations}
    actions: List[Dict[str, Any]] = []
    for cand in extracted:
        existing = by_name.get(norm_location_name(cand["name"]))
        if existing is None:
            actions.append(
                {
                    "action": ACTION_ADD_LOCATION,
                    "location_name": cand["name"],
                    "proposed": cand,
                    "scene_numbers": cand["scene_numbers"],
                }
            )
            continue

        stored_hash = str(existing.get("last_synced_hash") or "")
        current_hash = compute_content_hash(location_fingerprint(existing))
        changed = _location_field_changes(existing, cand)
        if stored_hash and current_hash != stored_hash:
            actions.append(
                {
                    "action": ACTION_CONFLICT,
                    "location_name": cand["name"],
                    "location_id": existing["id"],
                    "reason": (
                        "Location was modified after its last canon sync; "
                        "manual edits are never overwritten silently."
                    ),
                    "proposed": cand,
                }
            )
        elif changed:
            actions.append(
                {
                    "action": ACTION_UPDATE_PROPOSED,
                    "location_name": cand["name"],
                    "location_id": existing["id"],
                    "changed_fields": changed,
                    "proposed": cand,
                }
            )
        else:
            actions.append(
                {
                    "action": ACTION_NO_CHANGE,
                    "location_name": cand["name"],
                    "location_id": existing["id"],
                }
            )
    return actions


def _location_field_changes(
    existing: Dict[str, Any], cand: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    fingerprint = location_fingerprint(existing)
    changes: Dict[str, Dict[str, Any]] = {}
    proposed = {
        # Sync proposes structural facts from the screenplay only — never
        # narrative prose written by humans (description/atmosphere are guard-
        # only, mirroring biography handling in §P1.1).
        "interior": cand["interior"],
    }
    for key, proposed_value in proposed.items():
        current_value = fingerprint.get(key)
        if current_value != proposed_value:
            changes[f"location.{key}"] = {"current": current_value, "proposed": proposed_value}
    return changes


def check_continuity(
    screenplay: Optional[Dict[str, Any]],
    world_bible: Optional[Dict[str, Any]],
    locations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Deterministic continuity findings — read-only, never mutating.

    Only machine-verifiable rules can yield WORLD_RULE_CONFLICT; plain-text
    rules are listed as ``unverified_rules`` context instead of being guessed.
    """
    findings: List[Dict[str, Any]] = []
    by_name = {norm_location_name(loc.get("name")): loc for loc in locations}

    constraints = (world_bible or {}).get("continuity_constraints") or []
    machine_rules = [
        c for c in constraints if isinstance(c, dict) and (c.get(FORBIDDEN_TERMS_KEY) or [])
    ]
    unverified_rules = [
        c if isinstance(c, str) else str((c or {}).get("statement") or "")
        for c in constraints
        if not (isinstance(c, dict) and (c.get(FORBIDDEN_TERMS_KEY) or []))
    ]

    for scene in ((screenplay or {}).get("content") or {}).get("scenes") or []:
        scene_number = scene.get("scene_number")
        parsed = parse_scene_heading(scene.get("heading"))
        if parsed is None:
            findings.append(
                {
                    "finding_type": "UNPARSEABLE_HEADING",
                    "severity": "warning",
                    "scene_number": scene_number,
                    "message": f"Scene heading does not follow the INT./EXT. grammar: '{scene.get('heading')}'.",
                }
            )
            continue

        key = norm_location_name(parsed["location_name"])
        loc = by_name.get(key)
        if loc is None:
            findings.append(
                {
                    "finding_type": "UNKNOWN_LOCATION",
                    "severity": "blocking",
                    "scene_number": scene_number,
                    "message": (
                        f"Scene {scene_number} references location "
                        f"'{parsed['location_name']}' which is not in the World Canon."
                    ),
                }
            )
        else:
            tod = parsed["time_of_day"]
            if tod == "NIGHT" and loc.get("night_scene_compatible") is False:
                findings.append(_incompatible_time_finding(scene_number, loc, "NIGHT"))
            elif tod == "DAY" and loc.get("day_scene_compatible") is False:
                findings.append(_incompatible_time_finding(scene_number, loc, "DAY"))

        # Rule violations are independent of location registration — a scene
        # at an unregistered location can still violate a world rule.
        if machine_rules:
            haystack = " ".join(
                [str(scene.get("heading") or ""), str(scene.get("action") or "")]
                + [str(line.get("text") or "") for line in scene.get("dialogue") or []]
            ).lower()
            for rule in machine_rules:
                for term in rule.get(FORBIDDEN_TERMS_KEY) or []:
                    if str(term).strip().lower() in haystack:
                        findings.append(
                            {
                                "finding_type": "WORLD_RULE_CONFLICT",
                                "severity": "blocking",
                                "scene_number": scene_number,
                                "message": (
                                    f"Scene {scene_number} violates world rule "
                                    f"'{(rule or {}).get('statement') or ''}' — forbidden term '{term}' present."
                                ),
                            }
                        )

    era = str(((screenplay or {}).get("content") or {}).get("timeline_era") or "").strip()
    world_era = str((world_bible or {}).get("timeline_era") or "").strip()
    if era and world_era and era.lower() != world_era.lower():
        findings.append(
            {
                "finding_type": "TIMELINE_CONFLICT",
                "severity": "blocking",
                "message": (
                    f"Screenplay timeline era '{era}' conflicts with World Canon "
                    f"timeline era '{world_era}'."
                ),
            }
        )

    if unverified_rules and not machine_rules:
        findings.append(
            {
                "finding_type": "UNVERIFIED_RULES",
                "severity": "info",
                "message": (
                    f"{len(unverified_rules)} world rule(s) carry no machine-checkable "
                    "constraint; they require human review and cannot produce "
                    "WORLD_RULE_CONFLICT findings."
                ),
            }
        )
    return findings


def _incompatible_time_finding(
    scene_number: Any, location: Dict[str, Any], time_of_day: str
) -> Dict[str, Any]:
    return {
        "finding_type": "LOCATION_CONTINUITY_CONFLICT",
        "severity": "blocking",
        "scene_number": scene_number,
        "message": (
            f"Scene {scene_number} takes place at {time_of_day} in location "
            f"'{location.get('name')}' which is not {time_of_day.lower()}-compatible."
        ),
    }


async def load_latest_artifacts_of_kind(
    service: V3ResourceService, episode_id: str, kind: str
) -> Optional[Dict[str, Any]]:
    artifacts = await service.list("episode_artifacts")
    matching = [
        a for a in artifacts if a.get("episode_id") == episode_id and a.get("kind") == kind
    ]
    if not matching:
        return None
    matching.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
    return matching[0]


async def build_world_sync_proposal(
    service: V3ResourceService,
    project_id: str,
    episode_id: str,
    proposal_id: str,
    created_at: str,
) -> Tuple[Dict[str, Any], WorldSyncLineage]:
    """Build (and persist) a world sync proposal from the locked screenplay.

    Fail closed via :func:`resolve_locked_screenplay` when there is no lock.
    """
    locked = await resolve_locked_screenplay(service, episode_id)

    story_bible = await load_latest_artifacts_of_kind(service, episode_id, STORY_BIBLE_KIND)
    screenplay = await load_latest_artifacts_of_kind(service, episode_id, SCREENPLAY_DRAFT_KIND)

    extracted = extract_locations_from_screenplay(screenplay)
    all_locations = await service.list("locations")
    project_locations = [loc for loc in all_locations if loc.get("project_id") == project_id]
    actions = diff_locations(project_locations, extracted)

    world_facts = extract_world_facts(story_bible)
    lineage = WorldSyncLineage(
        source_series_id=project_id,
        source_story_bible_artifact_id=str((story_bible or {}).get("artifact_id") or ""),
        source_screenplay_revision_id=locked.revision_id,
        source_hash=compute_content_hash(
            {
                "story_bible": (story_bible or {}).get("content"),
                "screenplay_scenes": (screenplay or {}).get("revision_id"),
                "locked": {
                    "revision_id": locked.revision_id,
                    "content_hash": locked.content_hash,
                },
            }
        ),
    )

    counts = {a: 0 for a in (ACTION_NO_CHANGE, ACTION_ADD_LOCATION, ACTION_UPDATE_PROPOSED, ACTION_CONFLICT)}
    for act in actions:
        counts[act["action"]] += 1

    proposal = {
        "proposal_id": proposal_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "domain": "world",
        "status": "PROPOSED",
        "summary": counts,
        "actions": actions,
        "world_facts": world_facts,
        "lineage": lineage.to_dict(),
        "created_at": created_at,
        "updated_at": created_at,
    }
    await service.create("world_sync_proposals", proposal_id, proposal)
    return proposal, lineage


__all__ = [
    "ACTION_ADD_LOCATION",
    "ACTION_CONFLICT",
    "ACTION_NO_CHANGE",
    "ACTION_UPDATE_PROPOSED",
    "APPLICABLE_ACTIONS",
    "ACTION_ADD_CHARACTER",
    "WorldCanonError",
    "WorldSyncLineage",
    "build_world_sync_proposal",
    "check_continuity",
    "compute_content_hash",
    "diff_locations",
    "extract_locations_from_screenplay",
    "extract_world_facts",
    "location_fingerprint",
    "load_latest_artifacts_of_kind",
    "norm_location_name",
    "parse_scene_heading",
]
