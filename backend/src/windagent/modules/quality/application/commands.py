"""Command definitions for the Quality bounded context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from windagent.platform.commands import Command

from .models import (
    BaselineComparisonView,
    DatasetView,
    EvaluationRecordView,
    EvaluationRunView,
    TestCaseView,
    VerificationReportView,
)


@dataclass(frozen=True, slots=True)
class CreateEvaluationDataset(Command[DatasetView]):
    """Create a new benchmark dataset."""

    name: str
    domain: str
    dataset_id: str | None = None
    description: str = ""
    version: str = "1.0.0"
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AddDatasetTestCase(Command[TestCaseView]):
    """Add a test case to a benchmark dataset."""

    dataset_id: str
    name: str
    input_payload: Mapping[str, Any]
    expected_output: Mapping[str, Any] | None = None
    dimension: str = "task_success"
    case_id: str | None = None
    tags: tuple[str, ...] = ()
    criteria: tuple[dict[str, Any], ...] = ()
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class StartEvaluationRun(Command[EvaluationRunView]):
    """Start an evaluation run on an execution."""

    execution_id: str
    dataset_id: str | None = None
    evaluator_version: str = "2.0.0"
    run_id: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RecordEvaluationMetric(Command[EvaluationRecordView]):
    """Record a single evaluated metric on an active evaluation run."""

    run_id: str
    dimension: str
    metric_name: str
    score: float
    threshold: float = 0.7
    confidence: float = 1.0
    evidence_refs: tuple[str, ...] = ()
    details: Mapping[str, Any] | None = None
    blocked: bool = False
    evaluation_id: str | None = None


@dataclass(frozen=True, slots=True)
class FinalizeEvaluationRun(Command[EvaluationRunView]):
    """Finalize an evaluation run and compute composite score."""

    run_id: str


@dataclass(frozen=True, slots=True)
class ExecuteDatasetEvaluation(Command[EvaluationRunView]):
    """Execute automated evaluation of an execution run against all test cases in a dataset."""

    execution_id: str
    dataset_id: str
    grader_type: str = "exact_match"
    evaluator_version: str = "2.0.0"


@dataclass(frozen=True, slots=True)
class RunVerificationSuite(Command[VerificationReportView]):
    """Run a suite of verification gates against a target."""

    suite_id: str
    target_id: str
    gate_checks: tuple[dict[str, Any], ...]  # List of gate configs/contexts


@dataclass(frozen=True, slots=True)
class CompareBaseline(Command[BaselineComparisonView]):
    """Compare candidate metrics against a baseline run or model."""

    candidate_id: str
    baseline_id: str
    candidate_metrics: Mapping[str, tuple[str, float]]  # metric_name -> (dimension_str, score)
    baseline_metrics: Mapping[str, tuple[str, float]]
    regression_threshold: float = 0.05
    min_composite_pass_score: float = 0.7
