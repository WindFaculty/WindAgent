"""Application view models and durable row types for the Quality module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EvaluationRunRow:
    run_id: str
    execution_id: str
    dataset_id: str | None
    evaluator_version: str
    status: str
    composite_score: float
    passed: bool
    metadata_json: str
    optimistic_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EvaluationRecordRow:
    evaluation_id: str
    run_id: str
    execution_id: str
    dimension: str
    metric_name: str
    score: float
    threshold: float
    confidence: float
    evidence_refs_json: str
    passed: bool
    blocked: bool
    details_json: str
    evaluator_version: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class QualityDatasetRow:
    dataset_id: str
    name: str
    domain: str
    description: str
    version: str
    metadata_json: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TestCaseRow:
    case_id: str
    dataset_id: str
    name: str
    dimension: str
    input_payload_json: str
    expected_output_json: str
    tags_json: str
    criteria_json: str
    metadata_json: str


@dataclass(frozen=True, slots=True)
class VerificationReportRow:
    report_id: str
    suite_id: str
    target_id: str
    overall_status: str
    passed_gates_json: str
    failed_gates_json: str
    blocked_gates_json: str
    gate_results_json: str
    blocker_reasons_json: str
    recommendations_json: str
    duration_ms: float
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BaselineComparisonRow:
    comparison_id: str
    candidate_id: str
    baseline_id: str
    evaluator_version: str
    composite_candidate_score: float
    composite_baseline_score: float
    composite_delta: float
    regression_detected: bool
    passed: bool
    metric_deltas_json: str
    metadata_json: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# View DTOs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EvaluationRecordView:
    evaluation_id: str
    run_id: str
    execution_id: str
    dimension: str
    metric_name: str
    score: float
    threshold: float
    confidence: float
    evidence_refs: list[str]
    passed: bool
    blocked: bool
    details: dict[str, Any]
    evaluator_version: str
    created_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "run_id": self.run_id,
            "execution_id": self.execution_id,
            "dimension": self.dimension,
            "metric_name": self.metric_name,
            "score": self.score,
            "threshold": self.threshold,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "passed": self.passed,
            "blocked": self.blocked,
            "details": self.details,
            "evaluator_version": self.evaluator_version,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class EvaluationRunView:
    run_id: str
    execution_id: str
    dataset_id: str | None
    evaluator_version: str
    status: str
    composite_score: float
    passed: bool
    records: list[EvaluationRecordView]
    metadata: dict[str, Any]
    optimistic_version: int
    created_at: str
    updated_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "execution_id": self.execution_id,
            "dataset_id": self.dataset_id,
            "evaluator_version": self.evaluator_version,
            "status": self.status,
            "composite_score": self.composite_score,
            "passed": self.passed,
            "records": [r.to_payload() for r in self.records],
            "metadata": self.metadata,
            "optimistic_version": self.optimistic_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class TestCaseView:
    case_id: str
    dataset_id: str
    name: str
    dimension: str
    input_payload: dict[str, Any]
    expected_output: dict[str, Any]
    tags: list[str]
    criteria: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "dataset_id": self.dataset_id,
            "name": self.name,
            "dimension": self.dimension,
            "input_payload": self.input_payload,
            "expected_output": self.expected_output,
            "tags": self.tags,
            "criteria": self.criteria,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class DatasetView:
    dataset_id: str
    name: str
    domain: str
    description: str
    version: str
    test_cases: list[TestCaseView]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "version": self.version,
            "test_cases": [c.to_payload() for c in self.test_cases],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class VerificationReportView:
    report_id: str
    suite_id: str
    target_id: str
    overall_status: str
    passed_gates: list[str]
    failed_gates: list[str]
    blocked_gates: list[str]
    gate_results: list[dict[str, Any]]
    blocker_reasons: list[str]
    recommendations: list[str]
    duration_ms: float
    created_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "suite_id": self.suite_id,
            "target_id": self.target_id,
            "overall_status": self.overall_status,
            "passed_gates": self.passed_gates,
            "failed_gates": self.failed_gates,
            "blocked_gates": self.blocked_gates,
            "gate_results": self.gate_results,
            "blocker_reasons": self.blocker_reasons,
            "recommendations": self.recommendations,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class BaselineComparisonView:
    comparison_id: str
    candidate_id: str
    baseline_id: str
    evaluator_version: str
    composite_candidate_score: float
    composite_baseline_score: float
    composite_delta: float
    regression_detected: bool
    passed: bool
    metric_deltas: list[dict[str, Any]]
    created_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "evaluator_version": self.evaluator_version,
            "composite_candidate_score": self.composite_candidate_score,
            "composite_baseline_score": self.composite_baseline_score,
            "composite_delta": self.composite_delta,
            "regression_detected": self.regression_detected,
            "passed": self.passed,
            "metric_deltas": self.metric_deltas,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class QualitySummaryView:
    total_evaluations: int
    completed_evaluations: int
    failed_evaluations: int
    blocked_evaluations: int
    average_composite_score: float
    total_datasets: int
    total_verification_reports: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "total_evaluations": self.total_evaluations,
            "completed_evaluations": self.completed_evaluations,
            "failed_evaluations": self.failed_evaluations,
            "blocked_evaluations": self.blocked_evaluations,
            "average_composite_score": self.average_composite_score,
            "total_datasets": self.total_datasets,
            "total_verification_reports": self.total_verification_reports,
        }
