"""
Deterministic Story validation primitives (Plan B B1).

Finding shape is frozen by the B0 taxonomy:
``code`` (stable machine code), ``severity`` (INFO/WARNING/BLOCKING),
``location`` (JSON-pointer / model path), ``evidence``, ``remediation``,
``source`` (deterministic reviewer / model reviewer / human), optional
``dimension`` (quality dimension from the B0 taxonomy).

Severity semantics:
- INFO      — observation only; never blocks.
- WARNING   — approvable only if ApprovalPolicy permits warnings.
- BLOCKING  — must fix before lock; produces a RevisionProposal.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ValidationSeverity",
    "ValidationSource",
    "ValidationIssue",
    "ValidationReport",
    "json_pointer",
    "VALIDATION_CODE_CATALOG",
    "register_validation_code",
    "validation_codes_for",
]

JSON_POINTER_ROOT = ""


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class ValidationSource(str, Enum):
    DETERMINISTIC = "deterministic"
    MODEL = "model"
    HUMAN = "human"


class ValidationIssue(BaseModel):
    """A single deterministic validation finding (frozen shape)."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    severity: ValidationSeverity = ValidationSeverity.WARNING
    location: str = Field(default=JSON_POINTER_ROOT)  # JSON pointer / model path
    evidence: str = ""
    remediation: str = ""
    source: ValidationSource = ValidationSource.DETERMINISTIC
    dimension: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class ValidationReport(BaseModel):
    """Deterministic validation outcome for one artifact family."""

    model_config = ConfigDict(frozen=True)

    artifact_type: str
    issues: List[ValidationIssue] = Field(default_factory=list)

    def blocking(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.BLOCKING]

    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.INFO]

    def is_pass(self, *, allow_warnings: bool = False) -> bool:
        if self.blocking():
            return False
        if self.warnings() and not allow_warnings:
            return False
        return True

    def summary(self) -> Dict[str, Any]:
        counts = {
            "blocking": len(self.blocking()),
            "warnings": len(self.warnings()),
            "info": len(self.infos()),
        }
        return {
            "artifact_type": self.artifact_type,
            "pass": self.is_pass(),
            "counts": counts,
            "codes": sorted({i.code for i in self.issues}),
        }

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        return ValidationReport(
            artifact_type=self.artifact_type,
            issues=[*self.issues, *other.issues],
        )


def json_pointer(*parts: Any) -> str:
    """Build a JSON pointer from path parts (RFC 6901 escaping)."""
    if not parts:
        return JSON_POINTER_ROOT
    escaped = [str(p).replace("~", "~0").replace("/", "~1") for p in parts]
    return "/" + "/".join(escaped)


# ---------------------------------------------------------------------------
# Validation-code catalog (frozen B0 taxonomy + B1 artifact codes)
# ---------------------------------------------------------------------------
# Each entry: dimension, default severity, human description. Codes are stable
# machine codes; translated labels never replace them (C contract invariant 3).

VALIDATION_CODE_CATALOG: Dict[str, Dict[str, Any]] = {}


def register_validation_code(
    code: str,
    *,
    dimension: str,
    severity: ValidationSeverity,
    description: str,
) -> None:
    if code in VALIDATION_CODE_CATALOG:
        raise ValueError(f"duplicate validation code registration: {code}")
    VALIDATION_CODE_CATALOG[code] = {
        "code": code,
        "dimension": dimension,
        "default_severity": severity.value,
        "description": description,
    }


def validation_codes_for(*codes: str) -> List[Dict[str, Any]]:
    unknown = [c for c in codes if c not in VALIDATION_CODE_CATALOG]
    if unknown:
        raise KeyError(f"unknown validation codes: {unknown}")
    return [VALIDATION_CODE_CATALOG[c] for c in codes]


def _seed_catalog() -> None:
    seed: List[tuple[str, str, ValidationSeverity, str]] = [
        # Cross-cutting (B0 taxonomy)
        ("AGE_FIT", "AGE_FIT", ValidationSeverity.WARNING, "Content/lexicon/theme appropriate to the age band."),
        ("SAFETY_PROHIBITED", "SAFETY", ValidationSeverity.BLOCKING, "Prohibited content detected; artifact fails closed."),
        ("SAFETY_AGE_UNSUITABLE", "SAFETY", ValidationSeverity.BLOCKING, "Content unsuitable for the declared audience band."),
        ("BRIEF_ADHERENCE", "BRIEF_ADHERENCE", ValidationSeverity.WARNING, "Theme/tone/constraints/language coverage vs normalized brief."),
        ("DURATION_FIT", "DURATION_FIT", ValidationSeverity.WARNING, "Estimated duration fits the configured target budget."),
        ("CANON_REFERENCE_INTEGRITY", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.BLOCKING, "Every ID traces to bibles/canon; no free-form names alone."),
        ("WORLD_RULE_COMPLIANCE", "WORLD_RULE_COMPLIANCE", ValidationSeverity.WARNING, "World-rule consistency; conflicts surfaced, never auto-mutated."),
        ("LANGUAGE_CONSISTENCY", "LANGUAGE_CONSISTENCY", ValidationSeverity.WARNING, "Single language/register across the artifact."),
        ("CAUSAL_ORDER", "CAUSAL_ORDER", ValidationSeverity.WARNING, "Beat/scene causal and temporal order."),
        ("BEAT_COVERAGE", "BEAT_COVERAGE", ValidationSeverity.BLOCKING, "Outline/screenplay covers every beat."),
        ("FORMAT_VALIDITY", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Structured schema validity incl. dialogue attribution and scene/order/ID stability."),
        ("CONTINUITY", "CONTINUITY", ValidationSeverity.WARNING, "Cross-scene continuity."),
        # B1 artifact-shape codes
        ("IDEA_COUNT", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Candidate set holds exactly 3-5 distinct candidates."),
        ("IDEA_DUPLICATE", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Duplicate candidate IDs or near-duplicate titles."),
        ("IDEA_REQUIRED_FIELD", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Required idea field missing/empty."),
        ("ID_UNIQUE", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Duplicate stable ID within an artifact."),
        ("ID_STABILITY", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Scene/beat/dialogue ordering or ID stability violated."),
        ("REF_MISSING", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.BLOCKING, "Reference points to a missing canon/artifact ID."),
        ("RELATIONSHIP_CYCLE", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.WARNING, "Relationship cycle detected in canon."),
        ("DUPLICATE_NAME", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.WARNING, "Distinct IDs share a display name."),
        ("BEAT_ORPHAN", "BEAT_COVERAGE", ValidationSeverity.WARNING, "Beat is not referenced by any outline scene."),
        ("SCENE_ORPHAN", "BEAT_COVERAGE", ValidationSeverity.WARNING, "Outline scene references an unknown beat."),
        ("DIALOGUE_ATTRIBUTION", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Dialogue references a character not present in the scene."),
        ("DIALOGUE_EMPTY", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Dialogue text empty."),
        ("DURATION_SUM", "DURATION_FIT", ValidationSeverity.BLOCKING, "Sum of scene/beat seconds outside the configured tolerance."),
        ("DURATION_BOUND", "DURATION_FIT", ValidationSeverity.BLOCKING, "Total planned duration outside the 180-300 second envelope."),
        ("ORDER_SEQUENCE", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Order values must be unique and start at 1."),
        ("FIELD_EMPTY", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Required field is empty."),
        ("FIELD_TOO_LONG", "FORMAT_VALIDITY", ValidationSeverity.WARNING, "Field exceeds the documented maximum length."),
        ("UNKNOWN_REF_KIND", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.WARNING, "Reference kind is not part of the frozen vocabulary."),
        ("REVIEW_VERDICT", "NARRATIVE_QUALITY", ValidationSeverity.BLOCKING, "Review verdict inconsistent with findings (blocking findings present but PASS)."),
        ("REVISION_STALE", "NARRATIVE_QUALITY", ValidationSeverity.BLOCKING, "Revision proposal references findings not present in the reviewed report."),
        ("REVISION_BUDGET", "NARRATIVE_QUALITY", ValidationSeverity.BLOCKING, "Revision iteration budget exhausted; iteration_exhausted terminal state."),
        ("DIFF_MISMATCH", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Diff summary does not match the actual change list."),
        ("MANIFEST_MISSING_REF", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.BLOCKING, "Locked package manifest misses a required lineage artifact."),
        ("MANIFEST_HASH", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.BLOCKING, "Manifest entry hash is not a 64-char SHA-256 hex digest."),
        ("MANIFEST_DUPLICATE", "CANON_REFERENCE_INTEGRITY", ValidationSeverity.BLOCKING, "Manifest lists the same artifact more than once."),
        ("LOCK_STATE", "FORMAT_VALIDITY", ValidationSeverity.BLOCKING, "Receipt/package state not READY_FOR_PRODUCTION."),
        ("SCENE_COUNT_BOUND", "DURATION_FIT", ValidationSeverity.WARNING, "Scene count outside the configured min/max band."),
    ]
    for code, dimension, severity, description in seed:
        VALIDATION_CODE_CATALOG[code] = {
            "code": code,
            "dimension": dimension,
            "default_severity": severity.value,
            "description": description,
        }


_seed_catalog()
