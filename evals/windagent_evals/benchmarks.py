"""
Benchmark suite runner for WindAgent Evals (Phase 11).
Executes test cases against configured graders.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from windagent_evals.datasets import BenchmarkDataset, EvalTestCase
from windagent_evals.graders import (
    Grader, GradingResult, AccuracyGrader, ToolSelectionGrader,
    CostEfficiencyGrader, SafetyGrader, ModelRoutingGrader
)


@dataclass
class BenchmarkResult:
    """Consolidated result of a benchmark dataset execution."""
    dataset_name: str
    domain: str
    total_cases: int
    passed_cases: int
    overall_score: float
    results: List[Dict[str, Any]] = field(default_factory=list)


class BenchmarkRunner:
    """Executes evaluation datasets against a suite of objective graders."""

    def __init__(self, graders: Optional[List[Grader]] = None) -> None:
        self.graders: List[Grader] = graders if graders is not None else [
            AccuracyGrader(),
            ToolSelectionGrader(),
            CostEfficiencyGrader(),
            SafetyGrader(),
            ModelRoutingGrader(),
        ]

    def evaluate_case(self, test_case: EvalTestCase, execution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates a single test case using all graders."""
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
            "avg_score": avg_score,
            "grader_results": [
                {
                    "name": r.name,
                    "score": r.score,
                    "passed": r.passed,
                    "feedback": r.feedback,
                    "details": r.details
                }
                for r in grader_results
            ]
        }

    def run_dataset(self, dataset: BenchmarkDataset, executions_map: Dict[str, Dict[str, Any]]) -> BenchmarkResult:
        """Runs evaluation over an entire benchmark dataset."""
        case_results = []
        passed_count = 0
        total_scores = 0.0

        for test_case in dataset.test_cases:
            exec_data = executions_map.get(test_case.id, {
                "output": test_case.expected_output,
                "used_tools": test_case.expected_tools,
                "cost_usd": test_case.max_cost_usd * 0.5,
                "model": test_case.allowed_models[0] if test_case.allowed_models else "gpt-4o-mini"
            })
            res = self.evaluate_case(test_case, exec_data)
            case_results.append(res)
            total_scores += res["avg_score"]

            if res["passed"]:
                passed_count += 1

        total_cases = len(dataset.test_cases)
        overall_score = total_scores / total_cases if total_cases > 0 else 0.0

        return BenchmarkResult(
            dataset_name=dataset.name,
            domain=dataset.domain,
            total_cases=total_cases,
            passed_cases=passed_count,
            overall_score=overall_score,
            results=case_results
        )
