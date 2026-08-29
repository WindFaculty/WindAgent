"""Experiment Domain Models (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Defines Experiment, ExperimentStatus, ExperimentVerdict, ExperimentType,
metric comparisons, statistical confidence, and lifecycle transitions.

Invariants:
- All domain records are immutable (frozen).
- Experiments evaluate candidate modifications against baseline harnesses on datasets or replays.
- Experiments compute statistical significance, safety compliance, reliability metrics, and cost deltas.
- Only completed experiments with valid verdicts can be submitted to the Promotion Gate.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExperimentStatus(str, Enum):
    """Lifecycle states of an experiment."""
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentVerdict(str, Enum):
    """Evaluation verdict comparing candidate to baseline."""
    BEATS_BASELINE = "beats_baseline"
    TIE = "tie"
    INFERIOR = "inferior"
    INCONCLUSIVE = "inconclusive"
    UNSAFE = "unsafe"


class ExperimentType(str, Enum):
    """Execution modality of the experiment."""
    REPLAY = "replay"
    BENCHMARK = "benchmark"
    A_B_SHADOW = "a_b_shadow"
    LIVE_TEST = "live_test"


class ExperimentMetrics(BaseModel):
    """Statistical metric summary for a baseline or candidate run."""
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Task accuracy / win rate [0.0, 1.0].")
    safety_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Safety compliance score [0.0, 1.0].")
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Reliability score [0.0, 1.0].")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Mean task latency in milliseconds.")
    cost_usd: float = Field(default=0.0, ge=0.0, description="Total execution cost in USD.")
    sample_size: int = Field(default=1, ge=1, description="Number of evaluated samples/episodes.")
    error_count: int = Field(default=0, ge=0, description="Total errors encountered.")
    custom_metrics: Dict[str, Any] = Field(default_factory=dict, description="Domain-specific metrics (e.g. retention).")

    model_config = ConfigDict(frozen=True, extra="forbid")


class StatisticalComparison(BaseModel):
    """Statistical comparison results between candidate and baseline."""
    accuracy_delta: float = Field(default=0.0, description="candidate.accuracy - baseline.accuracy.")
    safety_delta: float = Field(default=0.0, description="candidate.safety_score - baseline.safety_score.")
    reliability_delta: float = Field(default=0.0, description="candidate.reliability_score - baseline.reliability_score.")
    cost_delta: float = Field(default=0.0, description="candidate.cost_usd - baseline.cost_usd.")
    latency_delta_ms: float = Field(default=0.0, description="candidate.latency_ms - baseline.latency_ms.")
    p_value: float = Field(default=1.0, ge=0.0, le=1.0, description="Statistical significance p-value.")
    confidence_interval: List[float] = Field(
        default_factory=lambda: [0.0, 0.0],
        description="95% confidence interval [lower, upper] for accuracy delta.",
    )
    uncertainty_margin: float = Field(default=0.0, ge=0.0, description="Evaluator uncertainty margin.")
    is_statistically_significant: bool = Field(default=False, description="Whether p_value < alpha (e.g. 0.05).")

    model_config = ConfigDict(frozen=True, extra="forbid")


class Experiment(BaseModel):
    """Immutable domain entity representing an empirical experiment.

    Compares a candidate mutation against a baseline harness version across
    a dataset or replay series.
    """
    experiment_id: str = Field(description="Unique experiment identifier (e.g. 'expt_...').")
    candidate_id: str = Field(description="Associated LearningCandidate ID.")
    baseline_harness_version: str = Field(description="HarnessVersion ID serving as baseline control.")
    experiment_type: ExperimentType = Field(
        default=ExperimentType.REPLAY,
        description="Execution modality (replay, benchmark, A/B).",
    )
    status: ExperimentStatus = Field(
        default=ExperimentStatus.DRAFT,
        description="Current experiment status.",
    )
    dataset_id: Optional[str] = Field(default=None, description="Evaluation dataset or benchmark ID.")
    sample_size: int = Field(default=1, ge=1, description="Number of evaluated samples.")

    baseline_metrics: Optional[ExperimentMetrics] = Field(
        default=None,
        description="Aggregated performance metrics for baseline harness.",
    )
    candidate_metrics: Optional[ExperimentMetrics] = Field(
        default=None,
        description="Aggregated performance metrics for candidate harness.",
    )
    comparison: Optional[StatisticalComparison] = Field(
        default=None,
        description="Calculated statistical comparison.",
    )

    safety_check_passed: bool = Field(default=False, description="Whether safety regression checks passed.")
    reliability_check_passed: bool = Field(default=False, description="Whether reliability checks passed.")
    verdict: ExperimentVerdict = Field(
        default=ExperimentVerdict.INCONCLUSIVE,
        description="Final evaluation verdict.",
    )

    project_id: Optional[str] = Field(default=None, description="Project scope ID.")
    domain: Optional[str] = Field(default=None, description="Domain classification (e.g. 'youtube', 'coding').")
    created_by: str = Field(default="system", description="Author or service creating the experiment.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata.")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last updated timestamp in UTC.")
    completed_at: Optional[datetime] = Field(default=None, description="Completion timestamp in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def start(self) -> Experiment:
        """Transitions experiment to RUNNING state."""
        if self.status not in (ExperimentStatus.DRAFT, ExperimentStatus.RUNNING):
            raise ValueError(f"Cannot start experiment {self.experiment_id} from status {self.status.value}")

        return self.model_copy(
            update={
                "status": ExperimentStatus.RUNNING,
                "updated_at": utc_now(),
            }
        )

    def complete(
        self,
        baseline_metrics: ExperimentMetrics,
        candidate_metrics: ExperimentMetrics,
        comparison: StatisticalComparison,
        safety_check_passed: bool,
        reliability_check_passed: bool,
        verdict: ExperimentVerdict,
    ) -> Experiment:
        """Completes experiment with full comparison metrics and verdict."""
        if self.status not in (ExperimentStatus.DRAFT, ExperimentStatus.RUNNING):
            raise ValueError(f"Cannot complete experiment {self.experiment_id} from status {self.status.value}")

        now = utc_now()
        return self.model_copy(
            update={
                "status": ExperimentStatus.COMPLETED,
                "sample_size": candidate_metrics.sample_size,
                "baseline_metrics": baseline_metrics,
                "candidate_metrics": candidate_metrics,
                "comparison": comparison,
                "safety_check_passed": safety_check_passed,
                "reliability_check_passed": reliability_check_passed,
                "verdict": verdict,
                "completed_at": now,
                "updated_at": now,
            }
        )

    def fail(self, error_message: str) -> Experiment:
        """Transitions experiment to FAILED state."""
        meta = dict(self.metadata)
        meta["error_message"] = error_message
        now = utc_now()

        return self.model_copy(
            update={
                "status": ExperimentStatus.FAILED,
                "metadata": meta,
                "completed_at": now,
                "updated_at": now,
            }
        )

    def cancel(self, reason: str = "User cancelled") -> Experiment:
        """Transitions experiment to CANCELLED state."""
        meta = dict(self.metadata)
        meta["cancel_reason"] = reason
        now = utc_now()

        return self.model_copy(
            update={
                "status": ExperimentStatus.CANCELLED,
                "metadata": meta,
                "completed_at": now,
                "updated_at": now,
            }
        )

    def assert_invariants(self) -> bool:
        """Validates domain invariants for experiments."""
        if not self.experiment_id or not self.experiment_id.strip():
            raise ValueError("Experiment ID cannot be empty.")
        if not self.candidate_id or not self.candidate_id.strip():
            raise ValueError("Candidate ID cannot be empty.")
        if not self.baseline_harness_version or not self.baseline_harness_version.strip():
            raise ValueError("Baseline harness version cannot be empty.")
        if self.sample_size < 1:
            raise ValueError(f"Sample size must be >= 1, got {self.sample_size}")
        return True


def compute_statistical_comparison(
    baseline: ExperimentMetrics,
    candidate: ExperimentMetrics,
    significance_alpha: float = 0.05,
    min_win_margin: float = 0.02,
    max_allowed_cost_delta: float = 0.50,
    max_uncertainty_margin: float = 0.45,
) -> Tuple[StatisticalComparison, bool, bool, ExperimentVerdict]:
    """Computes two-sample statistical comparison, safety/reliability checks, and verdict."""
    acc_delta = round(candidate.accuracy - baseline.accuracy, 4)
    safety_delta = round(candidate.safety_score - baseline.safety_score, 4)
    reliability_delta = round(candidate.reliability_score - baseline.reliability_score, 4)
    cost_delta = round(candidate.cost_usd - baseline.cost_usd, 4)
    latency_delta = round(candidate.latency_ms - baseline.latency_ms, 2)

    n1 = max(1, baseline.sample_size)
    n2 = max(1, candidate.sample_size)

    p1 = max(0.01, min(0.99, baseline.accuracy))
    p2 = max(0.01, min(0.99, candidate.accuracy))
    se = math.sqrt((p1 * (1 - p1) / n1) + (p2 * (1 - p2) / n2))

    z_crit = 1.96
    ci_lower = round(acc_delta - (z_crit * se), 4)
    ci_upper = round(acc_delta + (z_crit * se), 4)
    uncertainty = round(1.0 / math.sqrt(n1 + n2), 4)

    if se > 0:
        z_score = abs(acc_delta) / se
        p_val = round(2.0 * (1.0 - 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))), 4)
    else:
        p_val = 1.0

    is_significant = (p_val < significance_alpha) and (abs(acc_delta) >= min_win_margin)

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

    safety_passed = (candidate.safety_score >= baseline.safety_score) and (candidate.safety_score >= 0.95)
    reliability_passed = (
        (candidate.reliability_score >= baseline.reliability_score - 0.05)
        and (candidate.reliability_score >= 0.85)
    )
    cost_ok = cost_delta <= max_allowed_cost_delta
    uncertainty_ok = uncertainty <= max_uncertainty_margin

    if not safety_passed:
        verdict = ExperimentVerdict.UNSAFE
    elif not uncertainty_ok or (n2 < 2):
        verdict = ExperimentVerdict.INCONCLUSIVE
    elif acc_delta >= min_win_margin and reliability_passed and cost_ok:
        verdict = ExperimentVerdict.BEATS_BASELINE
    elif abs(acc_delta) < min_win_margin and reliability_passed and cost_ok:
        verdict = ExperimentVerdict.TIE
    elif acc_delta < -min_win_margin or not reliability_passed or not cost_ok:
        verdict = ExperimentVerdict.INFERIOR
    else:
        verdict = ExperimentVerdict.INCONCLUSIVE

    return comparison, safety_passed, reliability_passed, verdict

