"""
Evaluation benchmarks, model output scoring, regression suites for WindAgent (Phase 11).
"""

from windagent_evals.datasets import EvalTestCase, BenchmarkDataset, get_default_benchmark_datasets
from windagent_evals.graders import (
    GradingResult, Grader, AccuracyGrader, ToolSelectionGrader,
    CostEfficiencyGrader, SafetyGrader, ModelRoutingGrader
)
from windagent_evals.benchmarks import BenchmarkResult, BenchmarkRunner
from windagent_evals.replay import RecordedEvent, ReplayExecutionRecord, ReplayEngine
from windagent_evals.reports import EvaluationReport, EvalReportGenerator

__all__ = [
    "EvalTestCase",
    "BenchmarkDataset",
    "get_default_benchmark_datasets",
    "GradingResult",
    "Grader",
    "AccuracyGrader",
    "ToolSelectionGrader",
    "CostEfficiencyGrader",
    "SafetyGrader",
    "ModelRoutingGrader",
    "BenchmarkResult",
    "BenchmarkRunner",
    "RecordedEvent",
    "ReplayExecutionRecord",
    "ReplayEngine",
    "EvaluationReport",
    "EvalReportGenerator",
]

__version__ = "0.3.0"
