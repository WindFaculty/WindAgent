"""
Evaluation report generator for WindAgent Evals (Phase 11).
Consolidates benchmark suite results into structured evaluation reports.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
from windagent_evals.benchmarks import BenchmarkResult


@dataclass
class EvaluationReport:
    """Overall evaluation report across multiple benchmark suites."""
    passed: bool
    overall_accuracy_score: float
    total_benchmarks: int
    passed_benchmarks: int
    benchmark_results: List[BenchmarkResult] = field(default_factory=list)
    summary_metrics: Dict[str, Any] = field(default_factory=dict)


class EvalReportGenerator:
    """Generates evaluation reports and checks quality thresholds."""

    def __init__(self, min_overall_score: float = 0.75) -> None:
        self.min_overall_score = min_overall_score

    def generate_report(self, benchmark_results: List[BenchmarkResult]) -> EvaluationReport:
        """Consolidates benchmark suite results into an EvaluationReport."""
        if not benchmark_results:
            return EvaluationReport(
                passed=False,
                overall_accuracy_score=0.0,
                total_benchmarks=0,
                passed_benchmarks=0,
                benchmark_results=[]
            )

        passed_benchmarks = sum(1 for b in benchmark_results if b.overall_score >= self.min_overall_score)
        total_benchmarks = len(benchmark_results)
        overall_accuracy_score = sum(b.overall_score for b in benchmark_results) / total_benchmarks

        passed = overall_accuracy_score >= self.min_overall_score and passed_benchmarks == total_benchmarks

        summary_metrics = {
            "min_score_threshold": self.min_overall_score,
            "overall_accuracy_score": overall_accuracy_score,
            "total_benchmarks": total_benchmarks,
            "passed_benchmarks": passed_benchmarks,
            "failed_benchmarks": total_benchmarks - passed_benchmarks
        }

        return EvaluationReport(
            passed=passed,
            overall_accuracy_score=overall_accuracy_score,
            total_benchmarks=total_benchmarks,
            passed_benchmarks=passed_benchmarks,
            benchmark_results=benchmark_results,
            summary_metrics=summary_metrics
        )
