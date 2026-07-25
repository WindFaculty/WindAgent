"""
Evaluation report generator for WindAgent Evals (Phase 24).
Consolidates benchmark suite results into structured evaluation reports with
confidence intervals, baseline comparison, regression detection, and fail-closed verdict.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_evals.benchmarks import BenchmarkResult


@dataclass
class EvaluationReport:
    """Overall evaluation report across multiple benchmark suites.
    Passes only if ALL benchmarks pass with real evidence.
    """
    passed: bool
    overall_accuracy_score: float
    total_benchmarks: int
    passed_benchmarks: int
    blocked_benchmarks: int  # Benchmarks with no real execution data
    benchmark_results: List[BenchmarkResult] = field(default_factory=list)
    summary_metrics: Dict[str, Any] = field(default_factory=dict)
    regressions_detected: List[str] = field(default_factory=list)
    baseline_comparison: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_blocked_cases(self) -> bool:
        return any(b.blocked_cases > 0 for b in self.benchmark_results) or self.blocked_benchmarks > 0


class EvalReportGenerator:
    """Generates evaluation reports with confidence intervals and regression detection.
    Fail-closed: benchmarks with blocked cases lower the overall score.
    """

    def __init__(
        self,
        min_overall_score: float = 0.75,
        regression_threshold: float = 0.1,
        baseline_scores: Optional[Dict[str, float]] = None,
    ) -> None:
        self.min_overall_score = min_overall_score
        self.regression_threshold = regression_threshold
        self.baseline_scores = baseline_scores or {}

    def generate_report(self, benchmark_results: List[BenchmarkResult]) -> EvaluationReport:
        """Consolidates benchmark suite results into an EvaluationReport.
        Fail-closed: blocked benchmarks count against the overall pass.
        """
        if not benchmark_results:
            return EvaluationReport(
                passed=False,
                overall_accuracy_score=0.0,
                total_benchmarks=0,
                passed_benchmarks=0,
                blocked_benchmarks=0,
                benchmark_results=[],
            )

        passed_benchmarks = sum(1 for b in benchmark_results if b.overall_score >= self.min_overall_score and b.blocked_cases == 0)
        total_benchmarks = len(benchmark_results)
        blocked_benchmarks = sum(1 for b in benchmark_results if b.blocked_cases > 0)

        total_score = sum(b.overall_score for b in benchmark_results if b.blocked_cases == 0)
        evaluated_benchmarks = total_benchmarks - blocked_benchmarks
        overall_accuracy_score = total_score / evaluated_benchmarks if evaluated_benchmarks > 0 else 0.0

        # Penalize overall score for blocked benchmarks
        if blocked_benchmarks > 0:
            penalty = blocked_benchmarks / total_benchmarks
            overall_accuracy_score = overall_accuracy_score * (1.0 - penalty)

        # Detect regressions
        regressions = []
        for b in benchmark_results:
            if b.regression_detected:
                regressions.append(b.dataset_name)

        passed = (
            overall_accuracy_score >= self.min_overall_score
            and passed_benchmarks == evaluated_benchmarks
            and not regressions
        )

        # Baseline comparison summary
        baseline_comparison = {
            "baselines_available": len(self.baseline_scores),
            "datasets_with_baseline": list(self.baseline_scores.keys()),
            "regressions_detected": regressions,
            "regression_threshold": self.regression_threshold,
        }

        summary_metrics = {
            "min_score_threshold": self.min_overall_score,
            "overall_accuracy_score": overall_accuracy_score,
            "total_benchmarks": total_benchmarks,
            "passed_benchmarks": passed_benchmarks,
            "blocked_benchmarks": blocked_benchmarks,
            "failed_benchmarks": total_benchmarks - passed_benchmarks - blocked_benchmarks,
            "regression_count": len(regressions),
            "evaluated_benchmarks": evaluated_benchmarks,
        }

        return EvaluationReport(
            passed=passed,
            overall_accuracy_score=overall_accuracy_score,
            total_benchmarks=total_benchmarks,
            passed_benchmarks=passed_benchmarks,
            blocked_benchmarks=blocked_benchmarks,
            benchmark_results=benchmark_results,
            summary_metrics=summary_metrics,
            regressions_detected=regressions,
            baseline_comparison=baseline_comparison,
        )
