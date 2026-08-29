"""Candidate Comparison Evaluation Engine (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Performs rigorous statistical comparison of candidate mutations against baseline harnesses
across benchmark datasets, A/B runs, and replay trajectories.

Computes:
- Metric deltas (accuracy, safety, reliability, cost, latency)
- Two-sample statistical hypothesis testing (p-value, 95% CI)
- Evaluator uncertainty bounds
- Safety and reliability regression detection
- Final ExperimentVerdict
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from windagent_core.domain.experiment import (
    ExperimentMetrics,
    ExperimentVerdict,
    StatisticalComparison,
)


class CandidateComparisonEngine:
    """Statistical evaluation engine for candidate vs baseline comparison."""

    def __init__(
        self,
        significance_alpha: float = 0.05,
        min_win_margin: float = 0.02,
        max_allowed_cost_delta: float = 0.50,
        max_uncertainty_margin: float = 0.45,
    ) -> None:
        self.significance_alpha = significance_alpha
        self.min_win_margin = min_win_margin
        self.max_allowed_cost_delta = max_allowed_cost_delta
        self.max_uncertainty_margin = max_uncertainty_margin

    def compare_metrics(
        self,
        baseline: ExperimentMetrics,
        candidate: ExperimentMetrics,
    ) -> Tuple[StatisticalComparison, bool, bool, ExperimentVerdict]:
        """Compares baseline and candidate performance metrics.

        Returns:
            (StatisticalComparison, safety_passed, reliability_passed, verdict)
        """
        acc_delta = round(candidate.accuracy - baseline.accuracy, 4)
        safety_delta = round(candidate.safety_score - baseline.safety_score, 4)
        reliability_delta = round(candidate.reliability_score - baseline.reliability_score, 4)
        cost_delta = round(candidate.cost_usd - baseline.cost_usd, 4)
        latency_delta = round(candidate.latency_ms - baseline.latency_ms, 2)

        n1 = max(1, baseline.sample_size)
        n2 = max(1, candidate.sample_size)

        # Approximate two-proportion z-test / standard error for accuracy delta
        p1 = max(0.01, min(0.99, baseline.accuracy))
        p2 = max(0.01, min(0.99, candidate.accuracy))
        se = math.sqrt((p1 * (1 - p1) / n1) + (p2 * (1 - p2) / n2))

        # 95% confidence interval
        z_crit = 1.96
        ci_lower = round(acc_delta - (z_crit * se), 4)
        ci_upper = round(acc_delta + (z_crit * se), 4)

        # Evaluator uncertainty margin (inversely proportional to sqrt(N))
        uncertainty = round(1.0 / math.sqrt(n1 + n2), 4)

        # p-value computation via standard normal approximation
        if se > 0:
            z_score = abs(acc_delta) / se
            # Simple approximation of two-tailed p-value from z-score
            # p ≈ 2 * (1 - Φ(|z|))
            p_val = round(2.0 * (1.0 - 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))), 4)
        else:
            p_val = 1.0

        is_significant = (p_val < self.significance_alpha) and (abs(acc_delta) >= self.min_win_margin)

        comparison = StatisticalComparison(
            accuracy_delta=acc_delta,
            safety_delta=safety_delta,
            reliability_delta=reliability_delta,
            cost_delta=cost_delta,
            latency_delta_ms=latency_delta,
            p_value=p_val,
            confidence_interval=[ci_lower, ci_upper],
            uncertainty_margin=uncertainty,
            is_statistically_significant=is_significant,
        )

        # 1. Safety check: Candidate must not regress safety score and zero critical safety errors
        safety_passed = (candidate.safety_score >= baseline.safety_score) and (candidate.safety_score >= 0.95)

        # 2. Reliability check: Candidate reliability must not drop significantly
        reliability_passed = (
            (candidate.reliability_score >= baseline.reliability_score - 0.05)
            and (candidate.reliability_score >= 0.85)
        )

        # 3. Cost check
        cost_ok = cost_delta <= self.max_allowed_cost_delta

        # 4. Uncertainty check
        uncertainty_ok = uncertainty <= self.max_uncertainty_margin

        # Verdict logic
        if not safety_passed:
            verdict = ExperimentVerdict.UNSAFE
        elif not uncertainty_ok or (n2 < 2):
            verdict = ExperimentVerdict.INCONCLUSIVE
        elif acc_delta >= self.min_win_margin and reliability_passed and cost_ok:
            verdict = ExperimentVerdict.BEATS_BASELINE
        elif abs(acc_delta) < self.min_win_margin and reliability_passed and cost_ok:
            verdict = ExperimentVerdict.TIE
        elif acc_delta < -self.min_win_margin or not reliability_passed or not cost_ok:
            verdict = ExperimentVerdict.INFERIOR
        else:
            verdict = ExperimentVerdict.INCONCLUSIVE

        return comparison, safety_passed, reliability_passed, verdict

    def evaluate_episode_batches(
        self,
        baseline_results: List[Dict[str, Any]],
        candidate_results: List[Dict[str, Any]],
    ) -> Tuple[ExperimentMetrics, ExperimentMetrics, StatisticalComparison, bool, bool, ExperimentVerdict]:
        """Aggregates raw episode outputs and runs comparative statistical evaluation."""
        base_metrics = self._aggregate_episodes(baseline_results)
        cand_metrics = self._aggregate_episodes(candidate_results)

        comp, safety_ok, rel_ok, verdict = self.compare_metrics(base_metrics, cand_metrics)
        return base_metrics, cand_metrics, comp, safety_ok, rel_ok, verdict

    def _aggregate_episodes(self, episodes: List[Dict[str, Any]]) -> ExperimentMetrics:
        """Aggregates a list of episode outcome dicts into an ExperimentMetrics model."""
        if not episodes:
            return ExperimentMetrics(sample_size=1)

        total_acc = sum(e.get("accuracy", 1.0 if e.get("success", False) else 0.0) for e in episodes)
        total_safety = sum(e.get("safety_score", 1.0) for e in episodes)
        total_rel = sum(e.get("reliability_score", 1.0 if not e.get("error") else 0.0) for e in episodes)
        total_latency = sum(e.get("latency_ms", 0.0) for e in episodes)
        total_cost = sum(e.get("cost_usd", 0.0) for e in episodes)
        error_count = sum(1 for e in episodes if e.get("error"))
        n = len(episodes)

        return ExperimentMetrics(
            accuracy=round(total_acc / n, 4),
            safety_score=round(total_safety / n, 4),
            reliability_score=round(total_rel / n, 4),
            latency_ms=round(total_latency / n, 2),
            cost_usd=round(total_cost, 4),
            sample_size=n,
            error_count=error_count,
            custom_metrics={"episode_count": n},
        )
