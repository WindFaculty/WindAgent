"""Promotion Decision & Rollback Domain Models (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Defines PromotionDecision, PromotionStatus, GateCheckResult, PostPromotionHealth,
and the domain invariants for safe candidate promotion and regression rollback.

Invariants:
- All domain records are immutable (frozen).
- Promotion Gate (§17, §35) enforces 7 mandatory checks before promotion:
  1. Minimum sample size reached (Local >= 2, Project >= 3, Global >= 5).
  2. Candidate beats or matches baseline performance without regression.
  3. No safety regression (zero critical safety violations).
  4. No reliability regression (error rate within tolerance).
  5. Cost delta within acceptable budget margin.
  6. Evidence provenance complete (valid supporting experience and evaluation links).
  7. Evaluator uncertainty acceptable (uncertainty margin <= tolerance).
- High-risk mutations (global policy, executable skill, permissions, security rules)
  STRICTLY require human approval (`requires_human_approval=True`, `approved_by` required).
- Low-risk project-local prompt rules may undergo bounded automatic promotion if all 7 gates pass.
- Rollback invariant: detected regression in post-promotion monitoring triggers atomic rollback
  to the parent harness version and marks PromotionDecision as ROLLED_BACK.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PromotionStatus(str, Enum):
    """Lifecycle states of a promotion decision."""
    PENDING_APPROVAL = "pending_approval"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class GateCheckResult(BaseModel):
    """Structured evaluation record for the 7 Promotion Gates (§17, §35)."""
    min_sample_size_passed: bool = Field(
        default=False,
        description="Gate 1: Observed sample size >= scope threshold.",
    )
    beats_baseline_passed: bool = Field(
        default=False,
        description="Gate 2: Candidate accuracy / win rate >= baseline.",
    )
    no_safety_regression_passed: bool = Field(
        default=False,
        description="Gate 3: Zero safety violations and safety_score >= baseline.",
    )
    no_reliability_regression_passed: bool = Field(
        default=False,
        description="Gate 4: Reliability score >= baseline and error rate within tolerance.",
    )
    cost_within_budget_passed: bool = Field(
        default=False,
        description="Gate 5: Cost delta <= budget tolerance.",
    )
    provenance_complete_passed: bool = Field(
        default=False,
        description="Gate 6: Evidence IDs and provenance chain are complete and valid.",
    )
    uncertainty_acceptable_passed: bool = Field(
        default=False,
        description="Gate 7: Evaluator uncertainty margin <= maximum acceptable threshold.",
    )

    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed numeric and diagnostic payloads for each gate check.",
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    @property
    def all_passed(self) -> bool:
        """Returns True if all 7 mandatory gates pass."""
        return (
            self.min_sample_size_passed
            and self.beats_baseline_passed
            and self.no_safety_regression_passed
            and self.no_reliability_regression_passed
            and self.cost_within_budget_passed
            and self.provenance_complete_passed
            and self.uncertainty_acceptable_passed
        )

    def failed_gates(self) -> List[str]:
        """Returns list of gate names that failed."""
        failed = []
        if not self.min_sample_size_passed:
            failed.append("min_sample_size")
        if not self.beats_baseline_passed:
            failed.append("beats_baseline")
        if not self.no_safety_regression_passed:
            failed.append("no_safety_regression")
        if not self.no_reliability_regression_passed:
            failed.append("no_reliability_regression")
        if not self.cost_within_budget_passed:
            failed.append("cost_within_budget")
        if not self.provenance_complete_passed:
            failed.append("provenance_complete")
        if not self.uncertainty_acceptable_passed:
            failed.append("uncertainty_acceptable")
        return failed


class PostPromotionHealth(BaseModel):
    """Telemetry and health metrics observed after promoting a harness version."""
    version_id: str = Field(description="Promoted HarnessVersion ID being monitored.")
    observed_runs: int = Field(default=0, ge=0, description="Total execution runs observed.")
    error_count: int = Field(default=0, ge=0, description="Total errors observed in production.")
    safety_violations: int = Field(default=0, ge=0, description="Total safety violations observed.")
    avg_accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Mean task accuracy.")
    avg_latency_ms: float = Field(default=0.0, ge=0.0, description="Mean latency in ms.")
    is_regression_detected: bool = Field(default=False, description="Whether regression thresholds are breached.")
    regression_reason: Optional[str] = Field(default=None, description="Diagnostic reason if regression detected.")
    last_checked_at: datetime = Field(default_factory=utc_now, description="Timestamp of latest health check.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class PromotionDecision(BaseModel):
    """Immutable domain entity recording a promotion evaluation and decision.

    Links candidate, experiment, source/target harness versions, gate check results,
    human approval signatures, and rollback records.
    """
    decision_id: str = Field(description="Unique promotion decision identifier (e.g. 'pdec_...').")
    candidate_id: str = Field(description="Associated LearningCandidate ID.")
    experiment_id: Optional[str] = Field(default=None, description="Associated Experiment ID if evaluated.")
    source_harness_version: str = Field(description="Parent / baseline HarnessVersion ID.")
    target_harness_version: Optional[str] = Field(
        default=None,
        description="Newly created HarnessVersion ID upon promotion.",
    )

    status: PromotionStatus = Field(
        default=PromotionStatus.PENDING_APPROVAL,
        description="Current promotion lifecycle status.",
    )
    gate_checks: GateCheckResult = Field(
        default_factory=GateCheckResult,
        description="7-gate evaluation results.",
    )

    is_high_risk: bool = Field(
        default=False,
        description="Whether this mutation modifies global policy, executable skill, permissions, or security rules.",
    )
    requires_human_approval: bool = Field(
        default=False,
        description="Whether human authorization is required before committing to active harness.",
    )
    approved_by: Optional[str] = Field(
        default=None,
        description="Identity of human or automated authority approving promotion.",
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when promotion was approved.",
    )

    rejection_reason: Optional[str] = Field(default=None, description="Reason if rejected.")
    decision_rationale: str = Field(
        default="",
        description="Comprehensive rationale explaining the promotion or rejection decision.",
    )

    project_id: Optional[str] = Field(default=None, description="Project scope ID.")
    domain: Optional[str] = Field(default=None, description="Domain classification (e.g. 'youtube', 'coding').")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata.")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last updated timestamp in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def approve_and_promote(
        self,
        target_harness_version: str,
        approver: str,
        rationale: str = "Promotion gate passed and approved.",
    ) -> PromotionDecision:
        """Approves and promotes candidate into target harness version."""
        if not self.gate_checks.all_passed:
            failed = ", ".join(self.gate_checks.failed_gates())
            raise ValueError(f"Cannot promote decision {self.decision_id}: failed gates [{failed}]")

        if self.requires_human_approval and (not approver or approver == "system_auto"):
            raise ValueError(
                f"High-risk promotion {self.decision_id} strictly requires human approval, got approver '{approver}'"
            )

        now = utc_now()
        return self.model_copy(
            update={
                "status": PromotionStatus.PROMOTED,
                "target_harness_version": target_harness_version,
                "approved_by": approver,
                "approved_at": now,
                "decision_rationale": rationale,
                "updated_at": now,
            }
        )

    def reject(self, reason: str) -> PromotionDecision:
        """Rejects promotion proposal."""
        if not reason or not reason.strip():
            raise ValueError("Rejection reason cannot be empty.")

        now = utc_now()
        return self.model_copy(
            update={
                "status": PromotionStatus.REJECTED,
                "rejection_reason": reason.strip(),
                "decision_rationale": f"Rejected: {reason.strip()}",
                "updated_at": now,
            }
        )

    def rollback(self, reason: str) -> PromotionDecision:
        """Transitions promotion decision to ROLLED_BACK status due to post-promotion regression."""
        if not reason or not reason.strip():
            raise ValueError("Rollback reason cannot be empty.")

        meta = dict(self.metadata)
        meta["rollback_reason"] = reason.strip()
        meta["rolled_back_at"] = utc_now().isoformat()
        now = utc_now()

        return self.model_copy(
            update={
                "status": PromotionStatus.ROLLED_BACK,
                "metadata": meta,
                "updated_at": now,
            }
        )

    def assert_invariants(self) -> bool:
        """Validates domain invariants for promotion decisions."""
        if not self.decision_id or not self.decision_id.strip():
            raise ValueError("Decision ID cannot be empty.")
        if not self.candidate_id or not self.candidate_id.strip():
            raise ValueError("Candidate ID cannot be empty.")
        if not self.source_harness_version or not self.source_harness_version.strip():
            raise ValueError("Source harness version cannot be empty.")
        return True

