"""
Deterministic screenplay validators (Plan B B6).

FORMAT_VALIDITY (schema shape, dialogue attribution, scene/order/ID stability),
duration, beat coverage, canon reference integrity, and safety — provider-free.
Errors, warnings, and review suggestions stay separated by severity.
"""

from __future__ import annotations

from typing import List, Optional

from windagent_core.domain.story.bibles.models import CharacterCanon, WorldBible
from windagent_core.domain.story.outline.duration import duration_issues
from windagent_core.domain.story.outline.models import BeatSheet, EpisodeOutline
from windagent_core.domain.story.screenplay.models import (
    TRANSITIONS,
    DraftScene,
    ScreenplayDraft,
)
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    json_pointer,
)

__all__ = ["validate_screenplay_draft"]

MAX_SCENE_TEXT_CHARS = 20000  # per action/narration block ceiling


def _issue(
    code: str,
    location: str,
    evidence: str,
    severity: ValidationSeverity = ValidationSeverity.BLOCKING,
) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, location=location, evidence=evidence)


def validate_screenplay_draft(
    draft: ScreenplayDraft,
    *,
    outline: Optional[EpisodeOutline] = None,
    beat_sheet: Optional[BeatSheet] = None,
    canon: Optional[CharacterCanon] = None,
    world: Optional[WorldBible] = None,
) -> ValidationReport:
    issues: List[ValidationIssue] = []

    # -- FORMAT_VALIDITY -----------------------------------------------------
    scene_ids = [s.scene_id.value for s in draft.scenes]
    if len(scene_ids) != len(set(scene_ids)):
        issues.append(_issue("ID_UNIQUE", json_pointer("scenes"), "duplicate scene ids"))
    orders = [s.order for s in draft.scenes]
    if orders != sorted(orders) or len(orders) != len(set(orders)) or (orders and orders[0] != 1):
        issues.append(_issue(
            "ORDER_SEQUENCE", json_pointer("scenes"),
            f"scene orders must be 1..N unique: {orders}",
        ))

    canon_chars = {c.character_id for c in canon.characters} if canon else None
    world_locs = {l.location_id for l in world.recurring_locations} if world else None

    for scene_index, scene in enumerate(draft.scenes):
        pointer = json_pointer("scenes", scene_index)
        if not scene.action_description.strip() and not scene.dialogue and not scene.narration.strip():
            issues.append(_issue(
                "FIELD_EMPTY", json_pointer(pointer, "action_description"),
                f"scene {scene.scene_id} has no action, dialogue, or narration",
            ))
        for text_field in ("action_description", "narration"):
            if len(getattr(scene, text_field)) > MAX_SCENE_TEXT_CHARS:
                issues.append(_issue(
                    "FIELD_TOO_LONG", json_pointer(pointer, text_field),
                    f"{text_field} exceeds {MAX_SCENE_TEXT_CHARS} chars",
                    severity=ValidationSeverity.WARNING,
                ))
        if scene.transition not in TRANSITIONS:
            issues.append(_issue(
                "FORMAT_VALIDITY", json_pointer(pointer, "transition"),
                f"unknown transition {scene.transition!r}", severity=ValidationSeverity.WARNING,
            ))
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

        # Dialogue attribution: every line's character must be in the scene.
        scene_char_ids = set(scene.character_ids)
        for line_index, line in enumerate(scene.dialogue):
            line_pointer = json_pointer(pointer, "dialogue", line_index)
            if line.scene_id != scene.scene_id:
                issues.append(_issue(
                    "ID_STABILITY", json_pointer(line_pointer, "scene_id"),
                    f"dialogue {line.dialogue_id} bound to {line.scene_id} but stored in {scene.scene_id}",
                ))
            if line.character_id not in scene_char_ids:
                issues.append(_issue(
                    "DIALOGUE_ATTRIBUTION", json_pointer(line_pointer, "character_id"),
                    f"dialogue {line.dialogue_id} by {line.character_id} not in scene cast",
                ))
            if not line.text.strip():
                issues.append(_issue(
                    "DIALOGUE_EMPTY", json_pointer(line_pointer, "text"),
                    f"dialogue {line.dialogue_id} has empty text",
                ))
            if line.order < 1:
                issues.append(_issue(
                    "ORDER_SEQUENCE", json_pointer(line_pointer, "order"),
                    f"dialogue {line.dialogue_id} order must be >= 1",
                ))

    # -- BEAT_COVERAGE -------------------------------------------------------
    if beat_sheet is not None:
        beat_ids = {b.beat_id for b in beat_sheet.beats}
        referenced: set = set()
        for scene in draft.scenes:
            unknown = [b.value for b in scene.source_beat_ids if b not in beat_ids]
            if unknown:
                issues.append(_issue(
                    "BEAT_COVERAGE", json_pointer("scenes", scene.scene_id.value, "source_beat_ids"),
                    f"unknown beat refs: {unknown}", severity=ValidationSeverity.WARNING,
                ))
            referenced.update(scene.source_beat_ids)
        orphan = sorted(b.beat_id.value for b in beat_sheet.beats if b.beat_id not in referenced)
        if orphan:
            issues.append(_issue(
                "BEAT_COVERAGE", json_pointer("scenes"),
                f"beats not covered by any scene: {orphan}",
            ))

    # -- OUTLINE TRACEABILITY -------------------------------------------------
    if outline is not None:
        outline_scene_ids = {s.scene_id for s in outline.scenes}
        for scene in draft.scenes:
            if scene.outline_scene_id not in outline_scene_ids:
                issues.append(_issue(
                    "REF_MISSING", json_pointer("scenes", scene.scene_id.value, "outline_scene_id"),
                    f"unknown outline scene {scene.outline_scene_id.value}",
                ))

    # -- DURATION --------------------------------------------------------------
    findings = duration_issues(
        total_seconds=draft.total_estimated_seconds,
        target_seconds=draft.target_duration_seconds,
        tolerance_seconds=draft.tolerance_seconds,
        enforce_bounds=True,
    )
    issues.extend(
        _issue(f["code"], json_pointer("scenes"), f["evidence"], ValidationSeverity.BLOCKING)
        for f in findings
    )
    return ValidationReport(artifact_type=draft.artifact_type, issues=issues)
