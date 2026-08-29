"""Skill Evolution Domain Models (Phase 12 — ban_ke_hoach_v1 §18, §24, §25, §29, §35).

Defines the core SkillVersion, SkillCandidate, SkillEvaluationResult, SkillSecurityAuditResult,
and SkillPromotionDecision entities, lifecycle states, security gates, and transition helpers.

Invariants:
- All domain records are immutable (frozen).
- Executable skills != Harness Skill Reference:
  - Harness Skill Reference (HarnessEntryKind.SKILL_REF) merely routes / describes capability in prompt context.
  - Executable Skill actually installs/executes code/manifest in runtime and requires rigorous validation.
- Executable Skill security boundary (§18, §29):
  - Must pass static AST scan (zero forbidden calls: eval, exec, compile, __import__, unsafe subprocess/os.system).
  - Must pass secret detection (zero exposed credentials/keys).
  - Must pass dependency resolution (required tools and workflows must exist).
  - Must pass permission audit (permissions cannot exceed allowed host capability policies).
- High-Risk Governance (§18, §35):
  - Any executable code change or elevated permission strictly requires human approval (approved_by).
  - Safe, prompt-template-only skills with standard permissions may undergo bounded automated promotion.
- Rollback invariant (§18, §35):
  - Post-promotion regressions trigger atomic rollback to parent SkillVersion.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SkillCandidateStatus(str, Enum):
    """Lifecycle states of a proposed skill candidate."""
    PROPOSED = "proposed"
    ELIGIBLE = "eligible"
    AUDITED = "audited"
    EVALUATED = "evaluated"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SkillVersionStatus(str, Enum):
    """Lifecycle states of a versioned skill."""
    DRAFT = "draft"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class SkillPromotionStatus(str, Enum):
    """Lifecycle states of a skill promotion decision."""
    PENDING_APPROVAL = "pending_approval"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class SkillRiskLevel(str, Enum):
    """Risk assessment classification for skill mutations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SkillSecurityAuditResult(BaseModel):
    """Structured security audit and static analysis findings for a skill candidate (§18, §29)."""
    passed: bool = Field(default=False, description="Overall security audit verdict.")
    ast_scan_passed: bool = Field(default=False, description="AST check passed with 0 dangerous nodes.")
    permission_audit_passed: bool = Field(default=False, description="Permissions within host allowlist.")
    dependency_validation_passed: bool = Field(default=False, description="Declared tools and workflows exist.")
    secret_scan_passed: bool = Field(default=False, description="Zero detected hardcoded secrets/keys.")
    violations: List[str] = Field(default_factory=list, description="List of identified security violations.")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Computed risk score in [0.0, 1.0].")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed diagnostic payload.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    @property
    def is_safe(self) -> bool:
        return (
            self.passed
            and self.ast_scan_passed
            and self.permission_audit_passed
            and self.dependency_validation_passed
            and self.secret_scan_passed
            and len(self.violations) == 0
        )


class SkillEvaluationResult(BaseModel):
    """Structured functional and benchmark evaluation metrics for a skill candidate (§18)."""
    evaluation_id: str = Field(description="Unique evaluation record identifier.")
    skill_candidate_id: str = Field(description="Associated skill candidate identifier.")
    benchmark_passed: bool = Field(default=False, description="Whether benchmark evaluation succeeded.")
    test_suite_passed: bool = Field(default=False, description="Whether functional test suite passed 100%.")
    tests_run: int = Field(default=0, ge=0, description="Total functional test cases executed.")
    tests_passed: int = Field(default=0, ge=0, description="Test cases passed.")
    tests_failed: int = Field(default=0, ge=0, description="Test cases failed.")
    accuracy_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Task accuracy / success score.")
    safety_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Safety compliance score (must be >= 0.95).")
    token_efficiency_score: float = Field(default=1.0, ge=0.0, description="Token consumption ratio vs baseline.")
    cost_delta_usd: float = Field(default=0.0, description="Estimated cost delta per execution in USD.")
    latency_delta_ms: float = Field(default=0.0, description="Execution latency delta in milliseconds.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed metric payloads.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class SkillCandidate(BaseModel):
    """Immutable domain entity representing a proposed skill mutation or new skill (§18)."""
    candidate_id: str = Field(description="Unique skill candidate ID (e.g. 'skcand_...').")
    skill_id: str = Field(description="Target skill identifier (e.g. 'code_refactoring').")
    proposed_manifest: Dict[str, Any] = Field(description="Proposed SkillManifest dictionary.")
    proposed_code: Optional[str] = Field(default=None, description="Proposed Python source code if executable.")
    reasoning_summary: str = Field(description="Rationale and hypothesis behind this skill candidate.")
    supporting_experiences: List[str] = Field(default_factory=list, description="Associated experience IDs.")
    status: SkillCandidateStatus = Field(default=SkillCandidateStatus.PROPOSED, description="Current lifecycle status.")
    risk_level: SkillRiskLevel = Field(default=SkillRiskLevel.LOW, description="Assessed risk level.")
    is_executable: bool = Field(default=False, description="Whether this candidate contains executable code.")
    is_high_risk: bool = Field(default=False, description="Whether candidate requires human review.")
    security_audit: Optional[SkillSecurityAuditResult] = Field(default=None, description="Security audit report.")
    evaluation: Optional[SkillEvaluationResult] = Field(default=None, description="Evaluation benchmark report.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extension metadata.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp of proposal.")
    updated_at: datetime = Field(default_factory=utc_now, description="Timestamp of last update.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def compute_code_hash(self) -> str:
        """Computes SHA-256 hash of proposed code and manifest."""
        hasher = hashlib.sha256()
        manifest_str = json.dumps(self.proposed_manifest, sort_keys=True)
        hasher.update(manifest_str.encode("utf-8"))
        if self.proposed_code:
            hasher.update(self.proposed_code.encode("utf-8"))
        return hasher.hexdigest()

    def with_audit(self, audit: SkillSecurityAuditResult) -> SkillCandidate:
        """Transitions candidate to AUDITED state with audit findings."""
        new_status = SkillCandidateStatus.AUDITED if audit.is_safe else SkillCandidateStatus.REJECTED
        return self.model_copy(
            update={
                "security_audit": audit,
                "status": new_status,
                "updated_at": utc_now(),
            }
        )

    def with_evaluation(self, evaluation: SkillEvaluationResult) -> SkillCandidate:
        """Transitions candidate to EVALUATED state with benchmark findings."""
        passed = evaluation.benchmark_passed and evaluation.test_suite_passed and evaluation.safety_score >= 0.95
        new_status = SkillCandidateStatus.EVALUATED if passed else SkillCandidateStatus.REJECTED
        return self.model_copy(
            update={
                "evaluation": evaluation,
                "status": new_status,
                "updated_at": utc_now(),
            }
        )

    def mark_promoted(self) -> SkillCandidate:
        return self.model_copy(update={"status": SkillCandidateStatus.PROMOTED, "updated_at": utc_now()})

    def mark_rejected(self, reason: str = "") -> SkillCandidate:
        meta = dict(self.metadata)
        if reason:
            meta["rejection_reason"] = reason
        return self.model_copy(
            update={
                "status": SkillCandidateStatus.REJECTED,
                "metadata": meta,
                "updated_at": utc_now(),
            }
        )


class SkillVersion(BaseModel):
    """Immutable domain entity representing a versioned, deployed skill state (§18)."""
    version_id: str = Field(description="Unique skill version identifier (e.g. 'skver_code_refactor_v1.1.0').")
    skill_id: str = Field(description="Canonical skill identifier (e.g. 'code_refactoring').")
    version: str = Field(description="Semver version string (e.g. '1.1.0').")
    parent_version: Optional[str] = Field(default=None, description="Previous version ID if upgrade.")
    manifest: Dict[str, Any] = Field(description="Active SkillManifest specification.")
    code_hash: Optional[str] = Field(default=None, description="SHA-256 hash of executable code/package.")
    source_code: Optional[str] = Field(default=None, description="Persisted source code for reproducible rollback.")
    status: SkillVersionStatus = Field(default=SkillVersionStatus.ACTIVE, description="Lifecycle status.")
    promoted_from_candidate_id: Optional[str] = Field(default=None, description="Originating candidate ID.")
    security_audit_id: Optional[str] = Field(default=None, description="Passed security audit reference.")
    evaluation_id: Optional[str] = Field(default=None, description="Passed evaluation benchmark reference.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp created.")
    activated_at: Optional[datetime] = Field(default=None, description="Timestamp activated.")
    deprecated_at: Optional[datetime] = Field(default=None, description="Timestamp deprecated or rolled back.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def deprecate(self) -> SkillVersion:
        return self.model_copy(
            update={
                "status": SkillVersionStatus.DEPRECATED,
                "deprecated_at": utc_now(),
            }
        )

    def mark_rolled_back(self) -> SkillVersion:
        return self.model_copy(
            update={
                "status": SkillVersionStatus.ROLLED_BACK,
                "deprecated_at": utc_now(),
            }
        )


class SkillPromotionDecision(BaseModel):
    """Immutable domain entity recording the promotion decision of a SkillCandidate into a SkillVersion (§18, §35)."""
    decision_id: str = Field(description="Unique promotion decision ID (e.g. 'skprom_...').")
    candidate_id: str = Field(description="Associated skill candidate ID.")
    skill_id: str = Field(description="Target skill identifier.")
    source_version: Optional[str] = Field(default=None, description="Previous skill version before promotion.")
    target_version: str = Field(description="New skill version being promoted to (e.g. '1.2.0').")
    status: SkillPromotionStatus = Field(default=SkillPromotionStatus.PENDING_APPROVAL, description="Status.")
    security_audit_passed: bool = Field(default=False, description="Whether security audit was verified.")
    evaluation_passed: bool = Field(default=False, description="Whether evaluation benchmark was verified.")
    requires_human_approval: bool = Field(default=False, description="Whether human approval is required.")
    approved_by: Optional[str] = Field(default=None, description="Authorizer username/identity.")
    approved_at: Optional[datetime] = Field(default=None, description="Timestamp of authorization.")
    rejection_reason: Optional[str] = Field(default=None, description="Reason if rejected.")
    decision_rationale: str = Field(default="", description="Auditable reasoning for promotion/rejection.")
    created_at: datetime = Field(default_factory=utc_now, description="Decision creation timestamp.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def approve(self, approved_by: str, rationale: str = "") -> SkillPromotionDecision:
        if not approved_by or not approved_by.strip():
            raise ValueError("approved_by cannot be empty when approving a skill promotion.")
        return self.model_copy(
            update={
                "status": SkillPromotionStatus.PROMOTED,
                "approved_by": approved_by,
                "approved_at": utc_now(),
                "decision_rationale": rationale or self.decision_rationale,
                "updated_at": utc_now(),
            }
        )

    def reject(self, reason: str, rationale: str = "") -> SkillPromotionDecision:
        return self.model_copy(
            update={
                "status": SkillPromotionStatus.REJECTED,
                "rejection_reason": reason,
                "decision_rationale": rationale or self.decision_rationale,
                "updated_at": utc_now(),
            }
        )

    def mark_rolled_back(self, reason: str = "") -> SkillPromotionDecision:
        return self.model_copy(
            update={
                "status": SkillPromotionStatus.ROLLED_BACK,
                "decision_rationale": f"{self.decision_rationale} | Rolled back: {reason}" if reason else self.decision_rationale,
                "updated_at": utc_now(),
            }
        )


__all__ = [
    "SkillCandidateStatus",
    "SkillVersionStatus",
    "SkillPromotionStatus",
    "SkillRiskLevel",
    "SkillSecurityAuditResult",
    "SkillEvaluationResult",
    "SkillCandidate",
    "SkillVersion",
    "SkillPromotionDecision",
    "utc_now",
]

