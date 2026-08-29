"""Evaluation Engine V2 (Phase 7 — ban_ke_hoach_v1 §12).

Multi-dimensional graders, trajectory evaluation, fail-closed grading,
candidate-baseline comparisons, and report generation for WindAgent.
"""

from windagent_core.domain.evaluation import (
    BaselineComparison,
    EvaluationDimension,
    EvaluationRecord,
    MetricDelta,
)
from windagent_core.version import PRODUCT_VERSION
from windagent_evals.benchmarks import BenchmarkResult, BenchmarkRunner
from windagent_evals.datasets import (
    BenchmarkDataset,
    EvalTestCase,
    compute_dataset_checksum,
    get_default_benchmark_datasets,
)
from windagent_evals.engine import EvaluationEngineV2
from windagent_evals.graders import (
    AccuracyGrader,
    ArtifactQualityGrader,
    ContextEfficiencyGrader,
    CostEfficiencyGrader,
    CostGrader,
    DelegationEfficiencyGrader,
    Grader,
    GradingResult,
    LatencyGrader,
    ModelRoutingGrader,
    RegressionGrader,
    ReliabilityGrader,
    SafetyGrader,
    TaskSuccessGrader,
    ToolCorrectnessGrader,
    ToolSelectionGrader,
)
from windagent_evals.replay import (
    RecordedEvent,
    ReplayEngine,
    ReplayExecutionRecord,
    ReplayParityResult,
)
from windagent_evals.candidate_comparison import CandidateComparisonEngine
from windagent_evals.reports import EvalReportGenerator, EvaluationReport
from windagent_evals.skill_evaluator import SkillEvaluator, SkillTestCase
from windagent_evals.subagent_evaluator import SubagentEvaluator, SubagentTestCase

__all__ = [
    "EvaluationDimension",
    "EvaluationRecord",
    "MetricDelta",
    "BaselineComparison",
    "EvaluationEngineV2",
    "EvalTestCase",
    "BenchmarkDataset",
    "get_default_benchmark_datasets",
    "compute_dataset_checksum",
    "GradingResult",
    "Grader",
    "TaskSuccessGrader",
    "AccuracyGrader",
    "ArtifactQualityGrader",
    "ToolCorrectnessGrader",
    "ToolSelectionGrader",
    "SafetyGrader",
    "CostEfficiencyGrader",
    "CostGrader",
    "LatencyGrader",
    "ReliabilityGrader",
    "ModelRoutingGrader",
    "ContextEfficiencyGrader",
    "DelegationEfficiencyGrader",
    "RegressionGrader",
    "BenchmarkResult",
    "BenchmarkRunner",
    "RecordedEvent",
    "ReplayExecutionRecord",
    "ReplayEngine",
    "ReplayParityResult",
    "EvaluationReport",
    "EvalReportGenerator",
    "CandidateComparisonEngine",
    "SkillEvaluator",
    "SkillTestCase",
    "SubagentEvaluator",
    "SubagentTestCase",
]

__version__ = PRODUCT_VERSION