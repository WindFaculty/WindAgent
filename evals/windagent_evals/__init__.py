"""
Evaluation benchmarks, model output scoring, regression suites for WindAgent (Phase 24).
Fail-closed: no synthetic execution fallback, execution_id required for all cases.
"""

from windagent_evals.datasets import EvalTestCase, BenchmarkDataset, get_default_benchmark_datasets, compute_dataset_checksum
from windagent_evals.graders import (
    GradingResult, Grader, AccuracyGrader, ToolSelectionGrader,
    CostEfficiencyGrader, SafetyGrader, ModelRoutingGrader,
)
from windagent_evals.benchmarks import BenchmarkResult, BenchmarkRunner
from windagent_evals.replay import RecordedEvent, ReplayExecutionRecord, ReplayEngine, ReplayParityResult
from windagent_evals.reports import EvaluationReport, EvalReportGenerator

__all__ = [
    "EvalTestCase",
    "BenchmarkDataset",
    "get_default_benchmark_datasets",
    "compute_dataset_checksum",
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
    "ReplayParityResult",
    "EvaluationReport",
    "EvalReportGenerator",
]

__version__ = "0.4.0"
