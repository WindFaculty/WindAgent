"""
Deterministic canon cross-validation (Plan B B4).

Referential integrity, duplicate names/IDs, relationship cycles, world-rule
conflicts, and audience/safety constraints. Findings are actionable issues —
canon is never auto-mutated (rule: actionable validation issues, not
auto-mutation).
"""

from __future__ import annotations

from typing import Dict, List

from windagent_core.domain.story.bibles.models import (
    CharacterCanon,
    RELATIONSHIP_KINDS,
    StoryBible,
    WorldBible,
)
from windagent_core.domain.story.ids import StoryCharacterId
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    json_pointer,
)

__all__ = [
    "validate_story_bible",
    "validate_world_bible",
    "validate_character_canon",
    "validate_canon_set",
]


def _issue(code: str, location: str, evidence: str, severity: ValidationSeverity = ValidationSeverity.BLOCKING) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, location=location, evidence=evidence)


def validate_story_bible(bible: StoryBible) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if not bible.premise.strip():
        issues.append(_issue("FIELD_EMPTY", json_pointer("premise"), "StoryBible premise must not be empty."))
    if not bible.arc_summary.strip():
        issues.append(_issue("FIELD_EMPTY", json_pointer("arc_summary"), "StoryBible arc_summary must not be empty."))
    if len(bible.story_rules) > 20:
        issues.append(_issue(
            "FIELD_TOO_LONG", json_pointer("story_rules"),
            f"{len(bible.story_rules)} story rules exceed the 20-rule ceiling.",
            severity=ValidationSeverity.WARNING,
        ))
    return ValidationReport(artifact_type=bible.artifact_type, issues=issues)


def validate_world_bible(world: WorldBible) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if not world.setting.strip():
        issues.append(_issue("FIELD_EMPTY", json_pointer("setting"), "WorldBible setting must not be empty."))

    seen_rules: Dict[str, str] = {}
    for index, rule in enumerate([*world.physical_rules, *world.story_rules]):
        if rule.rule_id in seen_rules:
            issues.append(_issue(
                "ID_UNIQUE", json_pointer("story_rules", index, "rule_id"),
                f"duplicate world-rule id {rule.rule_id!r} (also used by {seen_rules[rule.rule_id]})",
                severity=ValidationSeverity.BLOCKING,
            ))
        seen_rules[rule.rule_id] = f"index {index}"

    # World-rule conflict: identical statements with different rule IDs.
    statements: Dict[str, str] = {}
    for rule in [*world.physical_rules, *world.story_rules]:
        key = rule.statement.strip().lower()
        if key and key in statements and statements[key] != rule.rule_id:
            issues.append(_issue(
                "WORLD_RULE_COMPLIANCE", json_pointer("story_rules"),
                f"conflicting rule ids {statements[key]} and {rule.rule_id} share the same statement",
                severity=ValidationSeverity.WARNING,
            ))
        if key:
            statements[key] = rule.rule_id

    loc_ids = [loc.location_id for loc in world.recurring_locations]
    if len(loc_ids) != len(set(loc_ids)):
        issues.append(_issue("ID_UNIQUE", json_pointer("recurring_locations"), "duplicate location ids"))
    prop_ids = [p.prop_id for p in world.recurring_objects]
    if len(prop_ids) != len(set(prop_ids)):
        issues.append(_issue("ID_UNIQUE", json_pointer("recurring_objects"), "duplicate object ids"))
    return ValidationReport(artifact_type=world.artifact_type, issues=issues)


def validate_character_canon(canon: CharacterCanon) -> ValidationReport:
    issues: List[ValidationIssue] = []
    entries = {e.character_id: e for e in canon.characters}

    if len(entries) != len(canon.characters):
        issues.append(_issue("ID_UNIQUE", json_pointer("characters"), "duplicate character ids"))

    names: Dict[str, StoryCharacterId] = {}
    for entry in canon.characters:
        key = entry.name.strip().lower()
        if key in names:
            issues.append(_issue(
                "DUPLICATE_NAME", json_pointer("characters", entry.character_id.value, "name"),
                f"name {entry.name!r} also used by {names[key].value}",
                severity=ValidationSeverity.WARNING,
            ))
        names[key] = entry.character_id

    for index, entry in enumerate(canon.characters):
        pointer = json_pointer("characters", index)
        if not entry.name.strip():
            issues.append(_issue("FIELD_EMPTY", json_pointer(pointer, "name"), f"character {entry.character_id} has no name"))
        if entry.role not in {"protagonist", "deuteragonist", "supporting", "antagonist"}:
            issues.append(_issue(
                "UNKNOWN_REF_KIND", json_pointer(pointer, "role"),
                f"unknown role {entry.role!r}", severity=ValidationSeverity.WARNING,
            ))
        for rel_index, rel in enumerate(entry.relationships):
            rel_pointer = json_pointer(pointer, "relationships", rel_index)
            if rel.kind not in RELATIONSHIP_KINDS:
                issues.append(_issue(
                    "UNKNOWN_REF_KIND", json_pointer(rel_pointer, "kind"),
                    f"unknown relationship kind {rel.kind!r}", severity=ValidationSeverity.WARNING,
                ))
            if rel.from_id not in entries:
                issues.append(_issue(
                    "REF_MISSING", json_pointer(rel_pointer, "from_id"),
                    f"relationship from unknown character {rel.from_id.value}",
                ))
            if rel.to_id not in entries:
                issues.append(_issue(
                    "REF_MISSING", json_pointer(rel_pointer, "to_id"),
                    f"relationship to unknown character {rel.to_id.value}",
                ))
            if rel.is_self_loop:
                issues.append(_issue(
                    "RELATIONSHIP_CYCLE", json_pointer(rel_pointer),
                    f"self-loop relationship on {rel.from_id.value}",
                ))

    # Relationship cycles of length >= 2 (a->b, b->a).
    for entry in canon.characters:
        for rel in entry.relationships:
            other = entries.get(rel.to_id)
            if other is None or rel.from_id == rel.to_id:
                continue
            if any(r.to_id == rel.from_id for r in other.relationships):
                issues.append(_issue(
                    "RELATIONSHIP_CYCLE",
                    json_pointer("characters", entry.character_id.value, "relationships"),
                    f"2-cycle {rel.from_id.value} <-> {rel.to_id.value}",
                    severity=ValidationSeverity.WARNING,
                ))
    return ValidationReport(artifact_type=canon.artifact_type, issues=issues)


def validate_canon_set(
    bible: StoryBible,
    world: WorldBible,
    canon: CharacterCanon,
    *,
    audience_min_age: int = 0,
) -> ValidationReport:
    """Cross-validate the three artifacts as one consistent set (B4 gate)."""
    report = (
        validate_story_bible(bible)
        .merge(validate_world_bible(world))
        .merge(validate_character_canon(canon))
    )
    issues: List[ValidationIssue] = list(report.issues)

    if audience_min_age > 0:
        for index, entry in enumerate(canon.characters):
            if entry.age_band and entry.age_band not in ("5-8", "6-8", "5-7"):
                issues.append(ValidationIssue(
                    code="SAFETY_AGE_UNSUITABLE",
                    severity=ValidationSeverity.BLOCKING,
                    location=json_pointer("characters", index, "age_band"),
                    evidence=f"age_band {entry.age_band!r} outside audience {audience_min_age}+",
                    remediation="Align character age band with the audience.",
                ))
    return ValidationReport(artifact_type="CanonSet", issues=issues)
