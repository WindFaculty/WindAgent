"""Promotion Gate Evaluator (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Enforces the 7 Promotion Gates before committing candidate modifications into active harness versions:
1. Minimum sample size reached (Local >= 2, Project >= 3, Global >= 5).
2. Candidate beats or ties baseline performance without quality degradation.
3. Zero safety regressions (safety score maintained, 0 critical safety faults).
4. Zero reliability regressions (error rate within tolerance).
5. Cost delta within allocated budget limits.
6. Evidence provenance complete (supporting experiences and reasoning valid).
7. Evaluator uncertainty margin within acceptable tolerance.

Enforces High-Risk vs Low-Risk governance:
- High-risk (Global scope, Executable Skills, Subagents, Routing, High/Critical Risk) -> requires human approval.
- Low-risk (Project/Local Prompt Rules, Low Risk) -> eligible for bounded automated promotion.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)
from windagent_core.domain.experiment import (
    Experiment,
    ExperimentStatus,
    ExperimentVerdict,
)
from windagent_core.domain.promotion import (
    GateCheckResult,
    PromotionDecision,
    PromotionStatus,
)

logger = logging.getLogger("windagent.orchestration.learning.promotion_gate")


class PromotionGate:
    """Evaluates candidate experiments against the 7 mandatory promotion gates."""

    def __init__(
        self,
        local_min_sample_size: int = 2,
        project_min_sample_size: int = 3,
        global_min_sample_size: int = 5,
        max_cost_delta: float = 0.50,
        max_uncertainty: float = 0.45,
    ) -> None:
        self.local_min_sample_size = local_min_sample_size
        self.project_min_sample_size = project_min_sample_size
        self.global_min_sample_size = global_min_sample_size
        self.max_cost_delta = max_cost_delta
        self.max_uncertainty = max_uncertainty

    def evaluate_candidate(
        self,
        candidate: LearningCandidate,
        experiment: Experiment,
        source_harness_version: str,
        decision_id: Optional[str] = None,
    ) -> PromotionDecision:
        """Evaluates experiment results and candidate metadata against all 7 promotion gates.

        Returns an immutable PromotionDecision.
        """
        if experiment.status != ExperimentStatus.COMPLETED:
            raise ValueError(
                f"Experiment {experiment.experiment_id} must be COMPLETED, currently {experiment.status.value}"
            )

        # 1. Gate 1: Minimum sample size
        required_samples = self._get_required_sample_size(candidate.scope)
        observed_samples = max(candidate.sample_size, experiment.sample_size)
        min_sample_passed = observed_samples >= required_samples

        # 2. Gate 2: Beats baseline
        comp = experiment.comparison
        beats_baseline_passed = (
            experiment.verdict in (ExperimentVerdict.BEATS_BASELINE, ExperimentVerdict.TIE)
            and (comp.accuracy_delta >= -0.01 if comp else False)
        )

        # 3. Gate 3: No safety regression
        cand_metrics = experiment.candidate_metrics
        base_metrics = experiment.baseline_metrics
        no_safety_passed = (
            experiment.safety_check_passed
            and (cand_metrics is not None and cand_metrics.safety_score >= 0.95)
            and (
                cand_metrics is not None
                and base_metrics is not None
                and cand_metrics.safety_score >= base_metrics.safety_score
            )
        )

        # 4. Gate 4: No reliability regression
        no_rel_passed = (
            experiment.reliability_check_passed
            and (cand_metrics is not None and cand_metrics.reliability_score >= 0.85)
            and (
                cand_metrics is not None
                and base_metrics is not None
                and cand_metrics.reliability_score >= base_metrics.reliability_score - 0.05
            )
        )

        # 5. Gate 5: Cost within budget
        cost_delta = comp.cost_delta if comp else 0.0
        cost_ok_passed = cost_delta <= self.max_cost_delta

        # 6. Gate 6: Provenance complete
        provenance_passed = (
            len(candidate.supporting_experiences) >= 1
            and bool(candidate.condition and candidate.condition.strip())
            and bool(candidate.reasoning_summary and candidate.reasoning_summary.strip())
            and candidate.status in (CandidateStatus.ELIGIBLE, CandidateStatus.EXPERIMENTING)
        )

        # 7. Gate 7: Evaluator uncertainty acceptable
        uncertainty = comp.uncertainty_margin if comp else 1.0
        uncertainty_passed = uncertainty <= self.max_uncertainty

        gate_checks = GateCheckResult(
            min_sample_size_passed=min_sample_passed,
            beats_baseline_passed=beats_baseline_passed,
            no_safety_regression_passed=no_safety_passed,
            no_reliability_regression_passed=no_rel_passed,
            cost_within_budget_passed=cost_ok_passed,
            provenance_complete_passed=provenance_passed,
            uncertainty_acceptable_passed=uncertainty_passed,
            details={
                "required_sample_size": required_samples,
                "observed_sample_size": observed_samples,
                "accuracy_delta": comp.accuracy_delta if comp else 0.0,
                "safety_delta": comp.safety_delta if comp else 0.0,
                "reliability_delta": comp.reliability_delta if comp else 0.0,
                "cost_delta": cost_delta,
                "uncertainty_margin": uncertainty,
                "experiment_verdict": experiment.verdict.value,
            },
        )

        # Determine High-Risk classification
        is_high_risk, requires_human = self._classify_risk(candidate)

        initial_status = PromotionStatus.PENDING_APPROVAL
        rationale_parts = []
        if gate_checks.all_passed:
            rationale_parts.append("All 7 promotion gates passed successfully.")
            if requires_human:
                rationale_parts.append("High-risk mutation: requires human review and authorization.")
            else:
                rationale_parts.append("Low-risk project rule: eligible for automated promotion.")
        else:
            failed = ", ".join(gate_checks.failed_gates())
            rationale_parts.append(f"Failed gates: [{failed}].")

        dec_id = decision_id or f"pdec_{uuid.uuid4().hex[:12]}"
        return PromotionDecision(
            decision_id=dec_id,
            candidate_id=candidate.candidate_id,
            experiment_id=experiment.experiment_id,
            source_harness_version=source_harness_version,
            target_harness_version=None,
            status=initial_status,
            gate_checks=gate_checks,
            is_high_risk=is_high_risk,
            requires_human_approval=requires_human,
            approved_by=None,
            approved_at=None,
            rejection_reason=None if gate_checks.all_passed else f"Gate checks failed: {failed}",
            decision_rationale=" ".join(rationale_parts),
            project_id=candidate.project_id,
            domain=candidate.domain,
            metadata={"candidate_kind": candidate.kind.value, "candidate_scope": candidate.scope.value},
        )

    def _get_required_sample_size(self, scope: CandidateScope) -> int:
        if scope == CandidateScope.LOCAL:
            return self.local_min_sample_size
        elif scope == CandidateScope.PROJECT:
            return self.project_min_sample_size
        else:
            return self.global_min_sample_size

    def _classify_risk(self, candidate: LearningCandidate) -> tuple[bool, bool]:
        """Returns (is_high_risk, requires_human_approval)."""
        is_high_risk = (
            candidate.risk_level in (CandidateRiskLevel.HIGH, CandidateRiskLevel.CRITICAL)
            or candidate.scope == CandidateScope.GLOBAL
            or candidate.kind in (CandidateKind.SKILL, CandidateKind.SUBAGENT_SPEC, CandidateKind.ROUTING_POLICY)
        )
        requires_human = is_high_risk
        return is_high_risk, requires_human
