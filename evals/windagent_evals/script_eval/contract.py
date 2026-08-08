"""Script Eval Phase 1 — production-script contract (schema + fail-closed validator).

Spec: test_kich_ban.md section 4. Gate SCRIPT_EVAL_CONTRACT_VALID:
  Schema validity = 100%, Reference integrity = 100%.
Hard fail on any dangling reference; empty dialogue/objective and duration
mismatch are WARNINGs (wordless episodes T12 must pass, duration gate lives
in Phase 8). Extends the plan check list with `invalid_type` (bool is not a
duration, lists must be lists).

Stdlib-only by design (evals package declares no jsonschema dep).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_SCHEMA_VERSION = "1.0.0"

TIME_OF_DAY = {
    "morning", "afternoon", "evening", "night", "dawn", "dusk", "day",
}
EMOTIONAL_STATE = {
    "neutral", "happy", "sad", "angry", "scared", "surprised", "excited",
    "tired", "calm", "curious", "frustrated", "joyful", "worried", "hopeful",
    "proud", "ashamed", "confused", "disgusted", "lonely", "loved",
}
DURATION_TOLERANCE = 0.15  # Phase 8 owns the ±15% gate; Phase 1 only reports

# data-driven required-field spec (paths like "scenes[].dialogue" in findings)
REQUIRED = {
    "root": ["project", "world_bible", "characters", "story", "scenes",
             "ending", "moral", "continuity_summary", "production_notes"],
    "project": ["title", "episode", "target_audience", "target_duration_minutes",
                "genre", "theme", "educational_goal"],
    "world_bible": ["locations"],
    "location": ["id", "name"],
    "character": ["id", "name", "age_type", "appearance", "personality",
                  "motivation", "voice_profile", "relationships"],
    "story": ["logline", "synopsis", "acts", "beats"],
    "scene": ["scene_id", "location", "time", "characters", "objective",
              "conflict", "action", "dialogue", "emotional_state",
              "continuity_state", "estimated_duration_seconds"],
    "ending": ["summary"],
    "beat": ["description"],
}

_SCENE_ID_SUFFIX = re.compile(r"(\d+)$")


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str  # ERROR (fails gate) | WARNING (flagged, review)
    path: str
    message: str


@dataclass(frozen=True)
class ContractReport:
    schema_valid: bool
    reference_integrity: bool
    findings: Tuple[Finding, ...] = field(default_factory=tuple)
    scene_count: int = 0
    character_count: int = 0
    target_seconds: Optional[float] = None
    estimated_seconds: Optional[float] = None
    duration_delta_pct: Optional[float] = None

    @property
    def valid(self) -> bool:
        return self.schema_valid and self.reference_integrity

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "WARNING"]


def _f(findings: List[Finding], check: str, severity: str, path: str, message: str) -> None:
    findings.append(Finding(check=check, severity=severity, path=path, message=message))


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _require_keys(doc: Any, keys: List[str], path: str, findings: List[Finding],
                  obj_name: str) -> bool:
    """Fail-closed structural check; returns True when doc is a usable dict."""
    if not isinstance(doc, dict):
        _f(findings, "missing_field", "ERROR", path,
           f"{obj_name} must be an object, got {type(doc).__name__}")
        return False
    for key in keys:
        if key not in doc:
            _f(findings, "missing_field", "ERROR", f"{path}.{key}",
               f"missing required field `{key}` in {obj_name}")
        elif doc[key] is None:
            _f(findings, "missing_field", "ERROR", f"{path}.{key}",
               f"field `{key}` is null in {obj_name}")
    return True


def validate_script(doc: Any) -> ContractReport:
    """Validate a production script dict against the Phase 1 contract.

    Fail-closed: any non-dict input yields schema_valid=False; dangling
    references always fail reference_integrity. Never silently passes.
    """
    findings: List[Finding] = []

    if not _require_keys(doc, REQUIRED["root"], "$", findings, "script"):
        return ContractReport(schema_valid=False, reference_integrity=False,
                              findings=tuple(findings))
    if not all(key in doc for key in REQUIRED["root"]):
        # root keys missing -> cannot evaluate anything, fail closed
        return ContractReport(schema_valid=False, reference_integrity=False,
                              findings=tuple(findings))
    project = doc["project"]
    _require_keys(project, REQUIRED["project"], "$.project", findings, "project")

    target_minutes = project.get("target_duration_minutes")
    target_seconds = None
    if isinstance(target_minutes, (int, float)) and not isinstance(target_minutes, bool):
        target_seconds = float(target_minutes) * 60.0
    else:
        _f(findings, "invalid_type", "ERROR", "$.project.target_duration_minutes",
           "must be a number of minutes")

    # ---- world bible / locations
    _require_keys(doc["world_bible"], REQUIRED["world_bible"], "$.world_bible",
                  findings, "world_bible")
    locations = doc["world_bible"].get("locations")
    location_ids: Dict[str, str] = {}
    if not isinstance(locations, list):
        _f(findings, "invalid_type", "ERROR", "$.world_bible.locations",
           "must be a list")
        locations = []
    for i, loc in enumerate(locations):
        path = f"$.world_bible.locations[{i}]"
        if _require_keys(loc, REQUIRED["location"], path, findings, "location"):
            location_ids.setdefault(loc["id"], path)

    # ---- characters
    characters = doc["characters"]
    character_ids: Dict[str, str] = {}
    if not isinstance(characters, list):
        _f(findings, "invalid_type", "ERROR", "$.characters", "must be a list")
        characters = []
    for i, ch in enumerate(characters):
        path = f"$.characters[{i}]"
        if not _require_keys(ch, REQUIRED["character"], path, findings, "character"):
            continue
        cid = ch["id"]
        if cid in character_ids:
            _f(findings, "duplicate_id", "ERROR", path,
               f"duplicate character id `{cid}`")
        character_ids.setdefault(cid, path)
    # second pass: relationships may reference characters declared later
    for i, ch in enumerate(characters):
        path = f"$.characters[{i}]"
        if not isinstance(ch, dict) or "relationships" not in ch:
            continue
        rels = ch.get("relationships", [])
        if not isinstance(rels, list):
            _f(findings, "invalid_type", "ERROR", f"{path}.relationships",
               "must be a list")
            continue
        for j, rel in enumerate(rels):
            rid = rel if isinstance(rel, str) else (
                rel.get("character_id") if isinstance(rel, dict) else None)
            if rid is None:
                _f(findings, "broken_references", "ERROR",
                   f"{path}.relationships[{j}]", "relationship must name a character_id")
            elif rid not in character_ids:
                _f(findings, "broken_references", "ERROR",
                   f"{path}.relationships[{j}]", f"references unknown character `{rid}`")

    # ---- story
    story = doc["story"]
    _require_keys(story, REQUIRED["story"], "$.story", findings, "story")
    beats = story.get("beats")
    if not isinstance(beats, list):
        _f(findings, "invalid_type", "ERROR", "$.story.beats", "must be a list")
        beats = []

    # ---- scenes
    scenes = doc["scenes"]
    if not isinstance(scenes, list):
        _f(findings, "invalid_type", "ERROR", "$.scenes", "must be a list")
        scenes = []
    scene_ids: Dict[str, str] = {}
    numeric_order: List[int] = []
    estimated_total = 0.0
    for i, scene in enumerate(scenes):
        path = f"$.scenes[{i}]"
        if not _require_keys(scene, REQUIRED["scene"], path, findings, "scene"):
            continue
        sid = scene["scene_id"]
        if sid in scene_ids:
            _f(findings, "duplicate_id", "ERROR", f"{path}.scene_id",
               f"duplicate scene_id `{sid}`")
        scene_ids.setdefault(sid, path)

        m = _SCENE_ID_SUFFIX.search(sid)
        if m:
            numeric_order.append(int(m.group(1)))
        else:
            _f(findings, "scene_ordering", "ERROR", f"{path}.scene_id",
               f"scene_id `{sid}` has no numeric suffix (SCENE_001 style)")

        scene_chars = scene.get("characters")
        if not isinstance(scene_chars, list):
            _f(findings, "invalid_type", "ERROR", f"{path}.characters",
               "must be a list of character ids")
            scene_chars = []
        for ref in scene_chars:
            if ref not in character_ids:
                _f(findings, "unknown_character", "ERROR", f"{path}.characters",
                   f"scene references unknown character `{ref}`")
        if scene.get("location") not in location_ids:
            _f(findings, "unknown_location", "ERROR", f"{path}.location",
               f"scene location `{scene.get('location')!r}` not in world_bible")

        if scene.get("time") not in TIME_OF_DAY:
            _f(findings, "invalid_enum", "ERROR", f"{path}.time",
               f"`{scene.get('time')!r}` not in TIME_OF_DAY")
        if scene.get("emotional_state") not in EMOTIONAL_STATE:
            _f(findings, "invalid_enum", "ERROR", f"{path}.emotional_state",
               f"`{scene.get('emotional_state')!r}` not in EMOTIONAL_STATE")

        duration = scene.get("estimated_duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            _f(findings, "invalid_type", "ERROR", f"{path}.estimated_duration_seconds",
               f"must be a number, got {type(duration).__name__}")
        elif duration < 0:
            _f(findings, "negative_duration", "ERROR", f"{path}.estimated_duration_seconds",
               f"negative duration {duration}")
        elif duration == 0:
            _f(findings, "zero_duration", "ERROR", f"{path}.estimated_duration_seconds",
               "zero duration")
        else:
            estimated_total += float(duration)

        if not _is_str(scene.get("dialogue")):
            _f(findings, "empty_dialogue", "WARNING", f"{path}.dialogue",
               "empty dialogue (allowed for wordless episodes, flagged for review)")
        if not _is_str(scene.get("objective")):
            _f(findings, "empty_scene_objective", "WARNING", f"{path}.objective",
               "empty scene objective")

    # ---- scene ordering: numeric suffixes must increase
    if len(numeric_order) > 1 and any(
            b <= a for a, b in zip(numeric_order, numeric_order[1:])):
        _f(findings, "scene_ordering", "ERROR", "$.scenes",
           f"scene_id order not increasing: {numeric_order}")

    # ---- beat scene references
    for j, beat in enumerate(beats):
        path = f"$.story.beats[{j}]"
        if not _require_keys(beat, REQUIRED["beat"], path, findings, "beat"):
            continue
        ref = beat.get("scene_id")
        if ref is not None and ref not in scene_ids:
            _f(findings, "broken_references", "ERROR", f"{path}.scene_id",
               f"beat references unknown scene `{ref}`")

    # ---- ending / moral / summaries
    _require_keys(doc["ending"], REQUIRED["ending"], "$.ending", findings, "ending")
    for key in ("moral", "continuity_summary", "production_notes"):
        if not _is_str(doc.get(key)):
            _f(findings, "missing_field", "ERROR", f"$.{key}",
               f"`{key}` must be a non-empty string")

    # ---- duration mismatch (reported, Phase 8 owns the gate)
    duration_delta_pct = None
    if target_seconds and estimated_total > 0:
        duration_delta_pct = (estimated_total - target_seconds) / target_seconds
        if abs(duration_delta_pct) > DURATION_TOLERANCE:
            _f(findings, "duration_mismatch", "WARNING", "$.scenes",
               f"estimated {estimated_total:.0f}s vs target {target_seconds:.0f}s "
               f"(delta {duration_delta_pct:+.1%}, tolerance ±{DURATION_TOLERANCE:.0%})")

    schema_errors = {f.check for f in findings if f.severity == "ERROR"
                     and f.check not in _REFERENCE_CHECKS}
    ref_errors = {f.check for f in findings if f.severity == "ERROR"
                  and f.check in _REFERENCE_CHECKS}
    return ContractReport(
        schema_valid=not schema_errors,
        reference_integrity=not ref_errors,
        findings=tuple(findings),
        scene_count=len(scenes),
        character_count=len(character_ids),
        target_seconds=target_seconds,
        estimated_seconds=estimated_total if estimated_total else None,
        duration_delta_pct=duration_delta_pct,
    )


_REFERENCE_CHECKS = {
    "duplicate_id", "unknown_character", "unknown_location",
    "scene_ordering", "broken_references",
}

__all__ = [
    "SCRIPT_SCHEMA_VERSION", "TIME_OF_DAY", "EMOTIONAL_STATE",
    "DURATION_TOLERANCE", "REQUIRED", "Finding", "ContractReport",
    "validate_script",
]
