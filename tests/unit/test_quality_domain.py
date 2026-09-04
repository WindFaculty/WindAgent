"""Unit tests for Quality domain models, fail-closed evaluation records, and verification gates."""

import pytest
from windagent.kernel.ids import EntityId
from windagent.modules.quality.domain.evals import (
    EvaluationDimension,
    EvaluationRunAggregate,
    EvaluationRunStatus,
)
from windagent.modules.quality.domain.regression import BaselineComparison
from windagent.modules.quality.domain.reports import QualityReportGenerator
from windagent.modules.quality.domain.verification import (
    ExecutionEvidence,
    VerificationGateResult,
    VerificationGateType,
    VerificationStatus,
    VerificationSuiteReport,
)


def test_evaluation_record_fail_closed_invariant() -> None:
    # 1. Record without evidence is blocked and score forced to 0.0
    agg = EvaluationRunAggregate.create(
        run_id=EntityId.generate(),
        execution_id="exec_100",
    )
    agg.start()

    rec_no_ev = agg.record_metric(
        evaluation_id="ev_1",
        dimension=EvaluationDimension.SAFETY,
        metric_name="secret_leakage_free",
        score=1.0,
        threshold=0.8,
        evidence_refs=(),  # Empty evidence!
    )
    assert rec_no_ev.blocked is True
    assert rec_no_ev.passed is False
    assert rec_no_ev.score == 0.0
    assert rec_no_ev.has_evidence() is False

    # 2. Record with valid evidence passes
    rec_with_ev = agg.record_metric(
        evaluation_id="ev_2",
        dimension=EvaluationDimension.TASK_SUCCESS,
        metric_name="story_outline_generated",
        score=0.9,
        threshold=0.7,
        evidence_refs=("artifact://story/outline.md",),
    )
    assert rec_with_ev.blocked is False
    assert rec_with_ev.passed is True
    assert rec_with_ev.score == 0.9
    assert rec_with_ev.has_evidence() is True


def test_evaluation_run_aggregate_lifecycle() -> None:
    agg = EvaluationRunAggregate.create(
        run_id=EntityId.generate(),
        execution_id="exec_200",
    )
    assert agg.status == EvaluationRunStatus.PENDING

    agg.start()
    assert agg.status == EvaluationRunStatus.RUNNING

    agg.record_metric(
        evaluation_id="ev_1",
        dimension=EvaluationDimension.TASK_SUCCESS,
        metric_name="compile",
        score=1.0,
        evidence_refs=("log://step_1",),
    )
    agg.record_metric(
        evaluation_id="ev_2",
        dimension=EvaluationDimension.LATENCY,
        metric_name="latency",
        score=0.8,
        evidence_refs=("trace://span_1",),
    )

    agg.finalize()
    assert agg.status == EvaluationRunStatus.COMPLETED
    assert agg.passed is True
    assert agg.composite_score == 0.9


def test_verification_suite_report_evaluation() -> None:
    g1 = VerificationGateResult(
        gate_name="unit_tests",
        gate_type=VerificationGateType.TEST_RUNNER,
        status=VerificationStatus.PASSED,
        evidence=ExecutionEvidence(command="pytest", exit_code=0, stdout="30 passed"),
        duration_ms=120.0,
    )
    g2 = VerificationGateResult(
        gate_name="policy_check",
        gate_type=VerificationGateType.POLICY_ENGINE,
        status=VerificationStatus.PASSED,
        evidence=ExecutionEvidence(command="policy_verify", exit_code=0),
        duration_ms=15.0,
    )

    report = VerificationSuiteReport.evaluate(
        report_id="vr_100",
        suite_id="pre_deploy",
        target_id="build_456",
        gate_results=[g1, g2],
    )

    assert report.overall_status == VerificationStatus.PASSED
    assert len(report.passed_gates) == 2
    assert len(report.failed_gates) == 0
    assert len(report.blocker_reasons) == 0


def test_verification_suite_blocked_and_failed() -> None:
    g1 = VerificationGateResult(
        gate_name="unit_tests",
        gate_type=VerificationGateType.TEST_RUNNER,
        status=VerificationStatus.FAILED,
        evidence=ExecutionEvidence(command="pytest", exit_code=1, stderr="AssertionError"),
        error_message="1 test failed",
    )
    g2 = VerificationGateResult(
        gate_name="integrity",
        gate_type=VerificationGateType.INTEGRITY,
        status=VerificationStatus.BLOCKED,
        evidence=ExecutionEvidence(),
        error_message="No artifact hash provided",
    )

    report = VerificationSuiteReport.evaluate(
        report_id="vr_fail",
        suite_id="build_suite",
        target_id="build_789",
        gate_results=[g1, g2],
    )

    assert report.overall_status == VerificationStatus.BLOCKED
    assert "unit_tests" in report.failed_gates
    assert "integrity" in report.blocked_gates
    assert len(report.blocker_reasons) == 2


def test_baseline_comparison_and_regression_detection() -> None:
    cand = {
        "task_success": (EvaluationDimension.TASK_SUCCESS, 0.95),
        "latency": (EvaluationDimension.LATENCY, 0.60),  # Dropped from 0.85
        "safety": (EvaluationDimension.SAFETY, 1.00),
    }
    base = {
        "task_success": (EvaluationDimension.TASK_SUCCESS, 0.90),
        "latency": (EvaluationDimension.LATENCY, 0.85),
        "safety": (EvaluationDimension.SAFETY, 1.00),
    }

    comp = BaselineComparison.compare(
        comparison_id="cmp_1",
        candidate_id="model_v2",
        baseline_id="model_v1",
        candidate_metrics=cand,
        baseline_metrics=base,
        regression_threshold=0.05,
    )

    assert comp.regression_detected is True
    assert comp.passed is False
    assert len(comp.metric_deltas) == 3

    lat_delta = next(d for d in comp.metric_deltas if d.metric_name == "latency")
    assert lat_delta.delta == pytest.approx(-0.25, abs=1e-4)
    assert lat_delta.regression is True


def test_quality_markdown_certification_generation() -> None:
    agg = EvaluationRunAggregate.create(
        run_id=EntityId.generate(),
        execution_id="exec_999",
    )
    agg.start()
    agg.record_metric(
        evaluation_id="ev_c1",
        dimension=EvaluationDimension.TASK_SUCCESS,
        metric_name="task_success",
        score=0.95,
        evidence_refs=("step_1",),
    )
    agg.finalize()

    cert_md = QualityReportGenerator.generate_markdown_certificate(agg)
    assert "# WindAgent Quality Certification Report" in cert_md
    assert "exec_999" in cert_md
    assert "95.00%" in cert_md
    assert "PASSED" in cert_md
