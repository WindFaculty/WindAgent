"""Parity tests verifying behavioral consistency with legacy WindAgent evals & verification."""

import pytest
from windagent.kernel.ids import EntityId
from windagent.modules.quality.domain.evals import (
    EvaluationDimension,
    EvaluationRunAggregate,
)
from windagent.modules.quality.domain.regression import BaselineComparison


def test_11_evaluation_dimensions_parity() -> None:
    """Verify all 11 canonical evaluation dimensions from legacy ban_ke_hoach_v1 §12 are present."""
    expected_dimensions = {
        "task_success",
        "artifact_quality",
        "tool_correctness",
        "safety",
        "cost",
        "latency",
        "reliability",
        "model_routing",
        "context_efficiency",
        "delegation_efficiency",
        "regression",
    }
    actual_dimensions = {d.value for d in EvaluationDimension}
    assert actual_dimensions == expected_dimensions


def test_fail_closed_missing_evidence_parity() -> None:
    """Verify fail-closed invariant: missing evidence MUST cause blocked=True and score=0.0."""
    agg = EvaluationRunAggregate.create(
        run_id=EntityId.generate(),
        execution_id="exec_parity",
    )
    agg.start()

    # In legacy evals: missing evidence -> blocked=True, score=0.0, passed=False
    rec = agg.record_metric(
        evaluation_id="ev_p1",
        dimension=EvaluationDimension.TASK_SUCCESS,
        metric_name="task_success_rate",
        score=0.99,  # High score, but NO evidence
        threshold=0.70,
        evidence_refs=(),
    )

    assert rec.blocked is True
    assert rec.score == 0.0
    assert rec.passed is False


def test_baseline_delta_regression_parity() -> None:
    """Verify regression detection formula: delta < -regression_threshold -> regression=True."""
    cand = {"score": (EvaluationDimension.TASK_SUCCESS, 0.70)}
    base = {"score": (EvaluationDimension.TASK_SUCCESS, 0.80)}

    # Delta is -0.10. With threshold 0.05, this MUST trigger regression
    comp = BaselineComparison.compare(
        comparison_id="cmp_parity",
        candidate_id="cand_1",
        baseline_id="base_1",
        candidate_metrics=cand,
        baseline_metrics=base,
        regression_threshold=0.05,
    )

    assert comp.composite_delta == pytest.approx(-0.10, abs=1e-4)
    assert comp.regression_detected is True
    assert comp.passed is False
