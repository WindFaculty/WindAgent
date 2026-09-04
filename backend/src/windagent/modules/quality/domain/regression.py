"""Regression detection and baseline comparison domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from windagent.kernel.time import utc_now

from .evals import EvaluationDimension


@dataclass(frozen=True, slots=True)
class MetricDelta:
    """Delta comparison for a specific metric between candidate and baseline."""

    metric_name: str
    dimension: EvaluationDimension
    candidate_score: float
    baseline_score: float
    delta: float  # candidate_score - baseline_score
    regression_threshold: float = 0.05
    regression: bool = False
    confidence_interval: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    """Comprehensive comparison between a candidate run/model and production baseline."""

    comparison_id: str
    candidate_id: str
    baseline_id: str
    evaluator_version: str
    composite_candidate_score: float
    composite_baseline_score: float
    composite_delta: float
    regression_detected: bool
    passed: bool
    metric_deltas: tuple[MetricDelta, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def compare(
        cls,
        comparison_id: str,
        candidate_id: str,
        baseline_id: str,
        candidate_metrics: dict[str, tuple[EvaluationDimension, float]],
        baseline_metrics: dict[str, tuple[EvaluationDimension, float]],
        evaluator_version: str = "2.0.0",
        regression_threshold: float = 0.05,
        min_composite_pass_score: float = 0.7,
    ) -> BaselineComparison:
        deltas: list[MetricDelta] = []
        any_regression = False

        all_keys = set(candidate_metrics.keys()) | set(baseline_metrics.keys())
        cand_scores: list[float] = []
        base_scores: list[float] = []

        for key in sorted(all_keys):
            dim, c_score = candidate_metrics.get(key, (EvaluationDimension.TASK_SUCCESS, 0.0))
            _, b_score = baseline_metrics.get(key, (EvaluationDimension.TASK_SUCCESS, 0.0))
            cand_scores.append(c_score)
            base_scores.append(b_score)

            delta = c_score - b_score
            is_reg = delta < -regression_threshold
            if is_reg:
                any_regression = True

            # Simple normal-approximate 95% CI placeholder
            ci_half = max(0.01, abs(delta) * 0.1)
            ci = (delta - ci_half, delta + ci_half)

            deltas.append(
                MetricDelta(
                    metric_name=key,
                    dimension=dim,
                    candidate_score=c_score,
                    baseline_score=b_score,
                    delta=delta,
                    regression_threshold=regression_threshold,
                    regression=is_reg,
                    confidence_interval=ci,
                )
            )

        composite_cand = sum(cand_scores) / len(cand_scores) if cand_scores else 0.0
        composite_base = sum(base_scores) / len(base_scores) if base_scores else 0.0
        composite_delta = composite_cand - composite_base

        passed = (not any_regression) and (composite_cand >= min_composite_pass_score)

        return cls(
            comparison_id=comparison_id,
            candidate_id=candidate_id,
            baseline_id=baseline_id,
            evaluator_version=evaluator_version,
            composite_candidate_score=composite_cand,
            composite_baseline_score=composite_base,
            composite_delta=composite_delta,
            regression_detected=any_regression,
            passed=passed,
            metric_deltas=tuple(deltas),
            created_at=utc_now(),
        )
