"""
Benchmark suite runner for WindAgent Evals (Phase 24).
Executes test cases against configured graders with real execution data.
No synthetic execution fallback: missing execution_id = BLOCKED.
Supports confidence intervals for large suites and baseline comparison.
"""

from __future__ import annotations
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_evals.datasets import BenchmarkDataset, EvalTestCase
from windagent_evals.graders import (
    Grader, GradingResult, AccuracyGrader, ToolSelectionGrader,
    CostEfficiencyGrader, SafetyGrader, ModelRoutingGrader,
)
from windagent_core.errors.exceptions import ValidationError


@dataclass
class BenchmarkResult:
    """Consolidated result of a benchmark dataset execution.
    Includes confidence intervals and baseline comparison for regression detection.
    """
    dataset_name: str
    domain: str
    total_cases: int
    passed_cases: int
    blocked_cases: int  # Cases without execution_id
    overall_score: float
    confidence_interval: Optional[tuple] = None  # (lower, upper) at 95%
    baseline_score: Optional[float] = None
    score_delta: Optional[float] = None  # Change from baseline
    regression_detected: bool = False
    results: List[Dict[str, Any]] = field(default_factory=list)


class BenchmarkRunner:
    """Executes evaluation datasets against a suite of objective graders.
    Fail-closed: cases without execution_id are BLOCKED, not passed with synthetic data.
    """

    def __init__(
        self,
        graders: Optional[List[Grader]] = None,
        regression_threshold: float = 0.1,  # 10% score drop = regression
        confidence_level: float = 0.95,
    ) -> None:
        self.graders: List[Grader] = graders if graders is not None else [
            AccuracyGrader(),
            ToolSelectionGrader(),
            CostEfficiencyGrader(),
            SafetyGrader(),
            ModelRoutingGrader(),
        ]
        self.regression_threshold = regression_threshold
        self.confidence_level = confidence_level

    def evaluate_case(
        self,
        test_case: EvalTestCase,
        execution_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluates a single test case using all graders.
        Fail-closed: if execution_id is missing, returns BLOCKED.
        """
        # Fail-closed: check execution_id
        if not test_case.has_execution:
            return {
                "case_id": test_case.id,
                "domain": test_case.domain,
                "passed": False,
                "blocked": True,
                "avg_score": 0.0,
                "grader_results": [{
                    "name": "execution_check",
                    "score": 0.0,
                    "passed": False,
                    "blocked": True,
                    "feedback": f"Case [{test_case.id}]: missing execution_id — BLOCKED (fail-closed)",
                    "details": {"execution_id": test_case.execution_id},
                }],
            }

        # Check that execution_data has real output, not synthetic
        output = execution_data.get("output", "")
        if not output or output == test_case.expected_output:
            # This looks like synthetic data — BLOCKED
            return {
                "case_id": test_case.id,
                "domain": test_case.domain,
                "passed": False,
                "blocked": True,
                "avg_score": 0.0,
                "grader_results": [{
                    "name": "execution_check",
                    "score": 0.0,
                    "passed": False,
                    "blocked": True,
                    "feedback": f"Case [{test_case.id}]: execution data appears synthetic (output matches expected) — BLOCKED",
                    "details": {"execution_id": test_case.execution_id},
                }],
            }

        case_scores: List[float] = []
        grader_results: List[GradingResult] = []

        for grader in self.graders:
            res = grader.grade(test_case, execution_data)
            grader_results.append(res)
            case_scores.append(res.score)

        avg_score = sum(case_scores) / len(case_scores) if case_scores else 0.0
        passed = all(r.passed for r in grader_results)

        return {
            "case_id": test_case.id,
            "domain": test_case.domain,
            "passed": passed,
            "blocked": False,
            "avg_score": avg_score,
            "grader_results": [
                {
                    "name": r.name,
                    "score": r.score,
                    "passed": r.passed,
                    "feedback": r.feedback,
                    "details": r.details,
                }
                for r in grader_results
            ],
        }

    def run_dataset(
        self,
        dataset: BenchmarkDataset,
        executions_map: Dict[str, Dict[str, Any]],
        baseline_scores: Optional[Dict[str, float]] = None,
    ) -> BenchmarkResult:
        """Runs evaluation over an entire benchmark dataset.
        No synthetic execution fallback — missing executions are BLOCKED.
        Computes confidence intervals and checks for regression against baseline.
        """
        case_results = []
        passed_count = 0
        blocked_count = 0
        total_scores = 0.0
        all_scores: List[float] = []

        for test_case in dataset.test_cases:
            exec_data = executions_map.get(
                test_case.id,
                {"output": "", "execution_id": None},
            )
            res = self.evaluate_case(test_case, exec_data)
            case_results.append(res)

            if res.get("blocked", False):
                blocked_count += 1
                continue

            total_scores += res["avg_score"]
            all_scores.append(res["avg_score"])

            if res["passed"]:
                passed_count += 1

        total_cases = len(dataset.test_cases)
        evaluated_cases = total_cases - blocked_count
        overall_score = total_scores / evaluated_cases if evaluated_cases > 0 else 0.0

        # Compute confidence interval (95% CI using normal approximation)
        confidence_interval = None
        if len(all_scores) >= 2:
            mean = statistics.mean(all_scores)
            stdev = statistics.stdev(all_scores) if len(all_scores) > 1 else 0.0
            z_score = 1.96  # 95% confidence
            margin = z_score * (stdev / math.sqrt(len(all_scores)))
            confidence_interval = (round(mean - margin, 4), round(mean + margin, 4))

        # Baseline comparison and regression detection
        baseline_score = None
        score_delta = None
        regression_detected = False

        if baseline_scores and dataset.name in baseline_scores:
            baseline_score = baseline_scores[dataset.name]
            score_delta = overall_score - baseline_score
            regression_detected = score_delta < -self.regression_threshold

        return BenchmarkResult(
            dataset_name=dataset.name,
            domain=dataset.domain,
            total_cases=total_cases,
            passed_cases=passed_count,
            blocked_cases=blocked_count,
            overall_score=overall_score,
            confidence_interval=confidence_interval,
            baseline_score=baseline_score,
            score_delta=score_delta,
            regression_detected=regression_detected,
            results=case_results,
        )
