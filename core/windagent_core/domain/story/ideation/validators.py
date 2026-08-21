"""
Deterministic ideation validators (Plan B B1/B3).

Uniqueness, count boundaries, age/safety constraints, and brief adherence are
checked without any provider. Validation returns a typed ``ValidationReport``;
invalid content is a typed failure, never silently accepted (rule 1).
"""

from __future__ import annotations

from typing import List

from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
    IdeaCandidateSet,
    SelectedIdea,
)
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    ValidationSource,
    json_pointer,
)

__all__ = [
    "validate_creative_brief",
    "validate_idea_candidate_set",
    "validate_selected_idea",
]


def _prohibited_hit(text: str, prohibited: List[str]) -> List[str]:
    lowered = text.lower()
    return [p for p in prohibited if p and p.lower() in lowered]


def validate_creative_brief(brief: CreativeBrief) -> ValidationReport:
    issues: List[ValidationIssue] = []
    if not brief.title.strip():
        issues.append(_issue("FIELD_EMPTY", "title", "Brief title must not be empty."))
    if brief.target_duration_seconds <= 0:
        issues.append(_issue("FIELD_EMPTY", "target_duration_seconds", "Target duration must be positive."))
    if brief.audience_min_age > brief.audience_max_age:
        issues.append(_issue(
            "FIELD_EMPTY", "audience_min_age",
            f"audience_min_age ({brief.audience_min_age}) > audience_max_age ({brief.audience_max_age}).",
        ))
    if not brief.language.strip():
        issues.append(_issue("FIELD_EMPTY", "language", "Language must be set."))
    if brief.prohibited_content:
        for text_field, value in (("title", brief.title), ("logline", brief.logline)):
            hits = _prohibited_hit(value, brief.prohibited_content)
            if hits:
                issues.append(ValidationIssue(
                    code="SAFETY_PROHIBITED",
                    severity=ValidationSeverity.BLOCKING,
                    location=json_pointer(text_field),
                    evidence=f"prohibited terms: {hits}",
                    remediation="Remove prohibited terms from the brief.",
                ))
    return ValidationReport(artifact_type=brief.artifact_type, issues=issues)


def validate_idea_candidate_set(
    candidate_set: IdeaCandidateSet,
    brief: CreativeBrief | None = None,
    *,
    require_evaluated: bool = False,
) -> ValidationReport:
    issues: List[ValidationIssue] = []

    if require_evaluated and not candidate_set.evaluated:
        issues.append(ValidationIssue(
            code="IDEA_REQUIRED_FIELD",
            severity=ValidationSeverity.BLOCKING,
            location=json_pointer("evaluated"),
            evidence="evaluated=false",
            remediation="Run studio.story.idea.evaluate before selection.",
        ))

    if not candidate_set.distinct_ids:
        ids = [c.candidate_id for c in candidate_set.candidates]
        dup = {i for i in ids if ids.count(i) > 1}
        issues.append(ValidationIssue(
            code="IDEA_DUPLICATE",
            severity=ValidationSeverity.BLOCKING,
            location=json_pointer("candidates"),
            evidence=f"duplicate candidate_ids: {sorted(dup)}",
            remediation="Give every candidate a unique stable ID.",
        ))

    titles = [c.title.strip().lower() for c in candidate_set.candidates]
    if len(titles) != len(set(titles)):
        issues.append(ValidationIssue(
            code="IDEA_DUPLICATE",
            severity=ValidationSeverity.BLOCKING,
            location=json_pointer("candidates", "title"),
            evidence="two candidates share a title",
            remediation="Make candidate titles distinct.",
        ))

    for index, candidate in enumerate(candidate_set.candidates):
        pointer = json_pointer("candidates", index)
        if not candidate.title.strip():
            issues.append(ValidationIssue(
                code="IDEA_REQUIRED_FIELD",
                severity=ValidationSeverity.BLOCKING,
                location=json_pointer(pointer, "title"),
                evidence=f"candidate {candidate.candidate_id} has empty title",
            ))
        if not candidate.safety_ok:
            issues.append(ValidationIssue(
                code="SAFETY_PROHIBITED",
                severity=ValidationSeverity.BLOCKING,
                location=json_pointer(pointer, "safety_ok"),
                evidence=f"candidate {candidate.candidate_id} flagged unsafe",
                remediation="Replace or drop the candidate; never auto-select a fallback.",
            ))
        if candidate.age_fit < 0.5:
            issues.append(ValidationIssue(
                code="SAFETY_AGE_UNSUITABLE",
                severity=ValidationSeverity.BLOCKING,
                location=json_pointer(pointer, "age_fit"),
                evidence=f"age_fit={candidate.age_fit}",
                remediation="Rewrite for the declared audience band.",
            ))
        if brief is not None:
            for text_field in ("title", "summary", "premise", "logline"):
                value = getattr(candidate, text_field) or ""
                hits = _prohibited_hit(value, brief.prohibited_content)
                if hits:
                    issues.append(ValidationIssue(
                        code="SAFETY_PROHIBITED",
                        severity=ValidationSeverity.BLOCKING,
                        location=json_pointer(pointer, text_field),
                        evidence=f"prohibited terms: {hits}",
                        remediation="Remove prohibited content from the candidate.",
                    ))

    return ValidationReport(artifact_type=candidate_set.artifact_type, issues=issues)


def validate_selected_idea(
    selected: "SelectedIdea",
    candidate_set: "IdeaCandidateSet | None" = None,
) -> ValidationReport:
    from windagent_core.domain.story.ideation.scoring import SELECTION_POLICIES

    issues: List[ValidationIssue] = []
    if selected.selection_policy not in SELECTION_POLICIES:
        issues.append(ValidationIssue(
            code="POLICY_UNKNOWN",
            severity=ValidationSeverity.BLOCKING,
            location=json_pointer("selection_policy"),
            evidence=f"policy {selected.selection_policy!r} not in {SELECTION_POLICIES}",
            remediation="Use a frozen selection policy value.",
        ))
    if candidate_set is not None and selected.candidate_id not in {c.candidate_id for c in candidate_set.candidates}:
        issues.append(ValidationIssue(
            code="REF_MISSING",
            severity=ValidationSeverity.BLOCKING,
            location=json_pointer("candidate_id"),
            evidence=f"candidate {selected.candidate_id} not in source set {selected.source_set_id}",
            remediation="Select only from the current IdeaCandidateSet and exact hash.",
        ))
    if not selected.rationale.strip():
        issues.append(ValidationIssue(
            code="FIELD_EMPTY", severity=ValidationSeverity.WARNING,
            location=json_pointer("rationale"),
            evidence="selection rationale missing",
        ))
    return ValidationReport(artifact_type=SelectedIdea.__name__, issues=issues)


def _issue(code: str, location: str, evidence: str) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=ValidationSeverity.BLOCKING,
        location=json_pointer(location),
        evidence=evidence,
        source=ValidationSource.DETERMINISTIC,
    )
