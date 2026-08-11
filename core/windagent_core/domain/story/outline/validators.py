"""
Deterministic outline/beat validators (Plan B B5).

Duration sums/tolerance, min/max scene and beat rules, causal order,
canon references, orphan beats, and the 180-300 s envelope — all without a
provider.
"""

from __future__ import annotations

from typing import List, Optional

from windagent_core.domain.story.bibles.models import CharacterCanon, WorldBible
from windagent_core.domain.story.outline.duration import duration_issues
from windagent_core.domain.story.outline.models import (
    BEAT_ROLES,
    BeatSheet,
    EpisodeOutline,
)
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    json_pointer,
)

__all__ = [
    "validate_beat_sheet",
    "validate_episode_outline",
]

MIN_BEATS = 4
MAX_BEATS = 12
MIN_SCENES = 3
MAX_SCENES = 12


def _issue(
    code: str,
    location: str,
    evidence: str,
    severity: ValidationSeverity = ValidationSeverity.BLOCKING,
) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, location=location, evidence=evidence)


def _check_ordering(
    orders: List[int],
    location_prefix: str,
    issues: List[ValidationIssue],
) -> None:
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        issues.append(_issue(
            "ORDER_SEQUENCE", json_pointer(location_prefix),
            f"orders must be unique and strictly increasing: {orders}",
        ))
    if orders and min(orders) != 1:
        issues.append(_issue(
            "ORDER_SEQUENCE", json_pointer(location_prefix, "order"),
            f"orders must start at 1; got {min(orders)}",
        ))


def validate_beat_sheet(
    beat_sheet: BeatSheet,
    canon: Optional[CharacterCanon] = None,
    world: Optional[WorldBible] = None,
) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if not (MIN_BEATS <= len(beat_sheet.beats) <= MAX_BEATS):
        issues.append(_issue(
            "SCENE_COUNT_BOUND", json_pointer("beats"),
            f"beat count {len(beat_sheet.beats)} outside [{MIN_BEATS}, {MAX_BEATS}]",
            severity=ValidationSeverity.WARNING,
        ))
    _check_ordering([b.order for b in beat_sheet.beats], "beats", issues)

    beat_ids: List[str] = [b.beat_id.value for b in beat_sheet.beats]
    if len(beat_ids) != len(set(beat_ids)):
        issues.append(_issue("ID_UNIQUE", json_pointer("beats"), "duplicate beat ids"))

    char_ids = {c.character_id for c in canon.characters} if canon else None
    location_ids = {loc.location_id for loc in world.recurring_locations} if world else None
    for index, beat in enumerate(beat_sheet.beats):
        pointer = json_pointer("beats", index)
        if beat.role not in BEAT_ROLES:
            issues.append(_issue(
                "UNKNOWN_REF_KIND", json_pointer(pointer, "role"),
                f"unknown beat role {beat.role!r}", severity=ValidationSeverity.WARNING,
            ))
        if not beat.description.strip():
            issues.append(_issue("FIELD_EMPTY", json_pointer(pointer, "description"), f"beat {beat.beat_id} has no description"))
        if char_ids is not None:
            unknown = [c.value for c in beat.character_ids if c not in char_ids]
            if unknown:
                issues.append(_issue(
                    "REF_MISSING", json_pointer(pointer, "character_ids"),
                    f"unknown character refs: {unknown}",
                ))
        if location_ids is not None and beat.location_id not in location_ids:
            location_value = beat.location_id.value if beat.location_id is not None else None
            issues.append(_issue(
                "REF_MISSING", json_pointer(pointer, "location_id"),
                f"unknown location {location_value!r}",
            ))

    findings = duration_issues(
        total_seconds=beat_sheet.allocated_seconds,
        target_seconds=beat_sheet.total_target_seconds,
        tolerance_seconds=beat_sheet.tolerance_seconds,
        enforce_bounds=False,
    )
    issues.extend(
        _issue(f["code"], json_pointer("beats"), f["evidence"], ValidationSeverity.BLOCKING)
        for f in findings
    )
    return ValidationReport(artifact_type=beat_sheet.artifact_type, issues=issues)


def validate_episode_outline(
    outline: EpisodeOutline,
    beat_sheet: Optional[BeatSheet] = None,
    canon: Optional[CharacterCanon] = None,
    world: Optional[WorldBible] = None,
) -> ValidationReport:
    issues: List[ValidationIssue] = []

    if not (MIN_SCENES <= len(outline.scenes) <= MAX_SCENES):
        issues.append(_issue(
            "SCENE_COUNT_BOUND", json_pointer("scenes"),
            f"scene count {len(outline.scenes)} outside [{MIN_SCENES}, {MAX_SCENES}]",
            severity=ValidationSeverity.WARNING,
        ))
    _check_ordering([s.order for s in outline.scenes], "scenes", issues)
    scene_ids = [s.scene_id.value for s in outline.scenes]
    if len(scene_ids) != len(set(scene_ids)):
        issues.append(_issue("ID_UNIQUE", json_pointer("scenes"), "duplicate scene ids"))

    canon_chars = {c.character_id for c in canon.characters} if canon else None
    world_locs = {
        location.location_id for location in world.recurring_locations
    } if world else None

    for index, scene in enumerate(outline.scenes):
        pointer = json_pointer("scenes", index)
        if not scene.intent.strip():
            issues.append(_issue("FIELD_EMPTY", json_pointer(pointer, "intent"), f"scene {scene.scene_id} has no intent"))
        if canon_chars is not None:
            unknown = [c.value for c in scene.character_ids if c not in canon_chars]
            if unknown:
                issues.append(_issue(
                    "REF_MISSING", json_pointer(pointer, "character_ids"),
                    f"unknown character refs: {unknown}",
                ))
        if world_locs is not None and scene.location_id not in world_locs:
            issues.append(_issue(
                "REF_MISSING", json_pointer(pointer, "location_id"),
                f"unknown location {scene.location_id.value}",
            ))

    # Beat coverage: every beat referenced >= 1 scene; no unknown beat refs.
    if beat_sheet is not None:
        beat_ids = {b.beat_id for b in beat_sheet.beats}
        referenced: set = set()
        for scene in outline.scenes:
            unknown = [b.value for b in scene.beat_refs if b not in beat_ids]
            if unknown:
                issues.append(_issue(
                    "SCENE_ORPHAN", json_pointer("scenes", scene.scene_id.value, "beat_refs"),
                    f"unknown beat refs: {unknown}", severity=ValidationSeverity.WARNING,
                ))
            referenced.update(scene.beat_refs)
        orphan = sorted(b.beat_id.value for b in beat_sheet.beats if b.beat_id not in referenced)
        if orphan:
            issues.append(_issue(
                "BEAT_ORPHAN", json_pointer("beats"),
                f"beats never referenced by scenes: {orphan}",
                severity=ValidationSeverity.WARNING,
            ))

    # Causality: scene order must respect beat order (first ref of each scene).
    if beat_sheet is not None:
        beat_order = {b.beat_id: b.order for b in beat_sheet.beats}
        scene_beat_min = [
            min((beat_order[r] for r in s.beat_refs if r in beat_order), default=0)
            for s in outline.scenes
        ]
        if scene_beat_min != sorted(scene_beat_min):
            issues.append(_issue(
                "CAUSAL_ORDER", json_pointer("scenes"),
                "scene order violates beat causal order",
                severity=ValidationSeverity.WARNING,
            ))

    findings = duration_issues(
        total_seconds=outline.total_estimated_seconds,
        target_seconds=outline.target_duration_seconds,
        tolerance_seconds=outline.tolerance_seconds,
        enforce_bounds=True,
    )
    issues.extend(
        _issue(f["code"], json_pointer("scenes"), f["evidence"], ValidationSeverity.BLOCKING)
        for f in findings
    )
    return ValidationReport(artifact_type=outline.artifact_type, issues=issues)
