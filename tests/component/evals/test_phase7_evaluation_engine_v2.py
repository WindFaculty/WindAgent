"""Phase 7 Component Tests — Evaluation Engine V2 (ban_ke_hoach_v1 §12).

Tests:
1. All 11 Evaluation Dimensions defined and complete.
2. EvaluationRecord domain model validation, immutability, and evidence enforcement.
3. Fail-closed behavior on missing execution evidence across all 11 dimension graders.
4. Valid execution grading across all 11 dimensions with accurate metric scores.
5. Safety grader strict zero-tolerance enforcement.
6. EvaluationEngineV2 full trajectory projection and evaluation from ExecutionTrajectory.
7. EvaluationEngineV2 fail-closed handling on incomplete trajectory.
8. BaselineComparison, 95% confidence intervals, and regression threshold gating.
9. EvaluationRepository async SQL CRUD, batch saving, and baseline aggregate queries.
10. API V2 evals endpoints (/api/v2/evals/dimensions and /api/v2/evals/compare).
"""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

# Ensure ORM models are registered
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
import windagent_storage.orm.memory_v2_models  # noqa: F401
import windagent_storage.orm.evaluation_models  # noqa: F401

from windagent_core.domain.evaluation import (
    BaselineComparison,
    EvaluationDimension,
    EvaluationRecord,
)
from windagent_core.domain.trajectory import (
    ExecutionTrajectory,
    TrajectoryArtifactRef,
    TrajectoryMetric,
    TrajectoryOutcome,
    TrajectoryStep,
)
from windagent_evals.datasets import EvalTestCase
from windagent_evals.engine import EvaluationEngineV2
from windagent_evals.graders import (
    ArtifactQualityGrader,
    ContextEfficiencyGrader,
    CostEfficiencyGrader,
    DelegationEfficiencyGrader,
    LatencyGrader,
    ModelRoutingGrader,
    RegressionGrader,
    ReliabilityGrader,
    SafetyGrader,
    TaskSuccessGrader,
    ToolCorrectnessGrader,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.evaluation_repository import EvaluationRepository
from windagent_api.routers.v2_evals import router as evals_router


def _new_id(prefix: str = "eval") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def db():
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:")
    async with mgr.engine.begin() as con:
        await con.run_sync(BaseORM.metadata.create_all)
    yield mgr
    await mgr.engine.dispose()


# ====================================================================
# 1. 11 Evaluation Dimensions Completeness
# ====================================================================

def test_evaluation_dimensions_complete():
    """All 11 evaluation dimensions specified in ban_ke_hoach_v1 §12 must exist."""
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
    assert expected_dimensions == actual_dimensions
    assert len(EvaluationDimension) == 11


# ====================================================================
# 2. EvaluationRecord Domain Model Validation & Immutability
# ====================================================================

def test_evaluation_record_immutability_and_evidence():
    rec = EvaluationRecord(
        evaluation_id=_new_id(),
        execution_id="exec_100",
        trajectory_id="traj_100",
        evaluator_version="2.0.0",
        dimension=EvaluationDimension.TASK_SUCCESS,
        metric_name="task_completion_rate",
        score=0.95,
        threshold=0.7,
        confidence=0.98,
        evidence_refs=["exec:exec_100", "step:step_1"],
        passed=True,
        blocked=False,
    )
    assert rec.has_evidence() is True
    assert rec.passed is True
    assert rec.score == 0.95

    # Test immutability
    with pytest.raises(Exception):
        rec.score = 0.5  # type: ignore

    # Test blocked record has no valid evidence
    blocked_rec = EvaluationRecord(
        evaluation_id=_new_id(),
        execution_id="exec_101",
        trajectory_id="traj_101",
        dimension=EvaluationDimension.SAFETY,
        metric_name="safety_compliance_rate",
        score=0.0,
        threshold=1.0,
        confidence=1.0,
        evidence_refs=[],
        passed=False,
        blocked=True,
    )
    assert blocked_rec.has_evidence() is False


# ====================================================================
# 3. Fail-Closed Behavior Across All 11 Graders
# ====================================================================

def test_all_graders_fail_closed_without_execution():
    """All graders must return blocked=True, score=0.0, passed=False when execution is missing."""
    test_case_no_exec = EvalTestCase(
        id="tc_missing",
        domain="testing",
        prompt="Execute task",
        expected_output="Result",
        execution_id=None,
    )
    graders = [
        TaskSuccessGrader(),
        ArtifactQualityGrader(),
        ToolCorrectnessGrader(),
        SafetyGrader(),
        CostEfficiencyGrader(),
        LatencyGrader(),
        ReliabilityGrader(),
        ModelRoutingGrader(),
        ContextEfficiencyGrader(),
        DelegationEfficiencyGrader(),
        RegressionGrader(),
    ]
    empty_payload = {}

    for grader in graders:
        result = grader.grade(test_case_no_exec, empty_payload)
        assert result.blocked is True, f"{grader.name} did not fail closed on missing execution"
        assert result.passed is False, f"{grader.name} passed without execution evidence"
        assert result.score == 0.0, f"{grader.name} gave non-zero score without execution"


# ====================================================================
# 4. Valid Execution Grading Across Dimensions
# ====================================================================

def test_dimensional_graders_with_valid_execution():
    tc = EvalTestCase(
        id="tc_01",
        domain="video_production",
        prompt="Generate video script",
        expected_output="Final Script",
        execution_id="exec_valid_01",
        expected_tools=["research_tool", "draft_tool"],
        max_cost_usd=0.05,
        max_latency_sec=10.0,
        allowed_models=["gpt-4o", "gemini-pro"],
        metadata={"max_prompt_tokens": 5000, "max_delegation_depth": 3},
    )

    valid_exec = {
        "execution_id": "exec_valid_01",
        "output": "Here is the Final Script for scene 1",
        "used_tools": ["research_tool", "draft_tool"],
        "artifacts": [{"artifact_id": "art_1", "kind": "script", "content_redacted_preview": "scene text"}],
        "outcome": {"succeeded": True, "terminal_state": "COMPLETED"},
        "cost_usd": 0.02,
        "latency_sec": 4.5,
        "retry_count": 0,
        "crash_count": 0,
        "has_recovered": False,
        "model": "gpt-4o",
        "prompt_tokens": 1500,
        "delegation_depth": 1,
        "child_runs_count": 2,
        "child_failures": 0,
        "candidate_score": 0.92,
        "baseline_score": 0.88,
        "policy_violations": [],
        "leaked_secrets": [],
    }

    # 1. TaskSuccess
    res_task = TaskSuccessGrader().grade(tc, valid_exec)
    assert res_task.passed is True
    assert res_task.score >= 0.9

    # 2. ArtifactQuality
    res_art = ArtifactQualityGrader().grade(tc, valid_exec)
    assert res_art.passed is True
    assert res_art.score >= 0.75

    # 3. ToolCorrectness
    res_tool = ToolCorrectnessGrader().grade(tc, valid_exec)
    assert res_tool.passed is True
    assert res_tool.score == 1.0

    # 4. Safety
    res_safe = SafetyGrader().grade(tc, valid_exec)
    assert res_safe.passed is True
    assert res_safe.score == 1.0

    # 5. Cost
    res_cost = CostEfficiencyGrader().grade(tc, valid_exec)
    assert res_cost.passed is True
    assert res_cost.score == 1.0

    # 6. Latency
    res_lat = LatencyGrader().grade(tc, valid_exec)
    assert res_lat.passed is True
    assert res_lat.score == 1.0

    # 7. Reliability
    res_rel = ReliabilityGrader().grade(tc, valid_exec)
    assert res_rel.passed is True
    assert res_rel.score == 1.0

    # 8. ModelRouting
    res_mr = ModelRoutingGrader().grade(tc, valid_exec)
    assert res_mr.passed is True
    assert res_mr.score == 1.0

    # 9. ContextEfficiency
    res_ctx = ContextEfficiencyGrader().grade(tc, valid_exec)
    assert res_ctx.passed is True
    assert res_ctx.score == 1.0

    # 10. DelegationEfficiency
    res_del = DelegationEfficiencyGrader().grade(tc, valid_exec)
    assert res_del.passed is True
    assert res_del.score == 1.0

    # 11. Regression
    res_reg = RegressionGrader().grade(tc, valid_exec)
    assert res_reg.passed is True
    assert res_reg.score == 1.0


# ====================================================================
# 5. Safety Grader Zero Tolerance
# ====================================================================

def test_safety_grader_zero_tolerance():
    tc = EvalTestCase(id="tc_sec", domain="sec", prompt="Run", expected_output="ok", execution_id="exec_sec")

    # Case with leaked secret
    bad_exec_secret = {
        "execution_id": "exec_sec",
        "output": "ok",
        "leaked_secrets": ["sk-proj-1234567890"],
        "policy_violations": [],
    }
    res_secret = SafetyGrader().grade(tc, bad_exec_secret)
    assert res_secret.passed is False
    assert res_secret.score == 0.0

    # Case with policy violation
    bad_exec_policy = {
        "execution_id": "exec_sec",
        "output": "ok",
        "leaked_secrets": [],
        "policy_violations": ["Unauthorized filesystem escape"],
    }
    res_pol = SafetyGrader().grade(tc, bad_exec_policy)
    assert res_pol.passed is False
    assert res_pol.score == 0.0


# ====================================================================
# 6. EvaluationEngineV2 Trajectory Projection
# ====================================================================

def test_evaluation_engine_v2_from_execution_trajectory():
    engine = EvaluationEngineV2(evaluator_version="2.0.0")

    step1 = TrajectoryStep(
        sequence=0,
        kind="tool_execution",
        identifier="tool_step_01",
        status="SUCCESS",
        details={"tool_name": "search_db", "args": {"q": "sample"}},
    )
    step2 = TrajectoryStep(
        sequence=1,
        kind="agent_turn",
        identifier="turn_step_02",
        status="COMPLETED",
        details={"content": "Found the required record and processed successfully."},
    )
    art1 = TrajectoryArtifactRef(
        artifact_id="art_doc_01",
        kind="tool_result",
        content_redacted_preview="Processed JSON data payload",
    )
    metric = TrajectoryMetric(
        prompt_tokens=400,
        completion_tokens=150,
        total_tokens=550,
        latency_ms=1200,
        cost_usd=0.005,
        retry_count=0,
    )
    outcome = TrajectoryOutcome(
        terminal_state="COMPLETED",
        succeeded=True,
        has_terminal_evidence=True,
    )

    trajectory = ExecutionTrajectory(
        execution_id="exec_full_001",
        completeness="COMPLETE",
        agent_type="gpt-4o",
        harness_version="1.0.0",
        steps=(step1, step2),
        artifacts=(art1,),
        metrics=metric,
        outcome=outcome,
    )

    records = engine.evaluate_trajectory(trajectory)
    assert len(records) >= 10

    # Check that all records have valid execution_id, trajectory_id, and evidence
    for r in records:
        assert r.execution_id == "exec_full_001"
        assert r.trajectory_id == "exec_full_001"
        assert r.evaluator_version == "2.0.0"
        assert r.blocked is False
        assert r.has_evidence() is True


def test_evaluation_engine_v2_incomplete_trajectory_fail_closed():
    engine = EvaluationEngineV2()
    empty_traj = ExecutionTrajectory(
        execution_id="exec_inc_001",
        completeness="INCOMPLETE",
        incomplete_reasons=("Crash before turn 0",),
        steps=(),
    )
    records = engine.evaluate_trajectory(empty_traj)
    assert len(records) > 0
    for r in records:
        assert r.blocked is True
        assert r.score == 0.0
        assert r.passed is False


# ====================================================================
# 7. Baseline Comparison & Regression Detection
# ====================================================================

def test_baseline_comparison_and_confidence_intervals():
    engine = EvaluationEngineV2(default_regression_threshold=0.05)

    # Candidate records: 2 runs with slightly varying scores
    cand_records = [
        EvaluationRecord(
            evaluation_id=_new_id(),
            execution_id="cand_1",
            trajectory_id="cand_1",
            dimension=EvaluationDimension.TASK_SUCCESS,
            metric_name="task_completion_rate",
            score=0.95,
            threshold=0.7,
            evidence_refs=["exec:cand_1"],
            passed=True,
            blocked=False,
        ),
        EvaluationRecord(
            evaluation_id=_new_id(),
            execution_id="cand_2",
            trajectory_id="cand_2",
            dimension=EvaluationDimension.TASK_SUCCESS,
            metric_name="task_completion_rate",
            score=0.91,
            threshold=0.7,
            evidence_refs=["exec:cand_2"],
            passed=True,
            blocked=False,
        ),
        EvaluationRecord(
            evaluation_id=_new_id(),
            execution_id="cand_1",
            trajectory_id="cand_1",
            dimension=EvaluationDimension.SAFETY,
            metric_name="safety_compliance_rate",
            score=1.0,
            threshold=1.0,
            evidence_refs=["exec:cand_1"],
            passed=True,
            blocked=False,
        ),
    ]

    baseline_scores = {
        "task_completion_rate": 0.88,
        "safety_compliance_rate": 1.0,
    }

    comp: BaselineComparison = engine.compare_with_baseline(
        candidate_records=cand_records,
        baseline_records=baseline_scores,
        candidate_id="cand_v2",
        baseline_id="prod_baseline_v1",
    )

    assert comp.passed is True
    assert comp.regression_detected is False
    assert comp.composite_delta >= 0.0
    assert "task_completion_rate" in comp.confidence_intervals


def test_baseline_comparison_flags_regression():
    engine = EvaluationEngineV2(default_regression_threshold=0.05)

    cand_records = [
        EvaluationRecord(
            evaluation_id=_new_id(),
            execution_id="cand_reg",
            trajectory_id="cand_reg",
            dimension=EvaluationDimension.TASK_SUCCESS,
            metric_name="task_completion_rate",
            score=0.70,  # Dropped from 0.90 (delta = -0.20 > -0.05)
            threshold=0.7,
            evidence_refs=["exec:cand_reg"],
            passed=True,
            blocked=False,
        ),
    ]
    baseline_scores = {"task_completion_rate": 0.90}

    comp = engine.compare_with_baseline(
        candidate_records=cand_records,
        baseline_records=baseline_scores,
        candidate_id="cand_reg",
        baseline_id="prod_base",
    )
    assert comp.regression_detected is True
    assert comp.passed is False


# ====================================================================
# 8. EvaluationRepository SQL CRUD & Baseline Aggregates
# ====================================================================

@pytest.mark.asyncio
async def test_evaluation_repository_sql_crud(db: DatabaseManager):
    async with db.session_factory() as session:
        repo = EvaluationRepository(session)

        rec1 = EvaluationRecord(
            evaluation_id=_new_id(),
            execution_id="exec_sql_1",
            trajectory_id="traj_sql_1",
            evaluator_version="2.0.0",
            harness_version="harness_v1",
            dimension=EvaluationDimension.TASK_SUCCESS,
            metric_name="task_completion_rate",
            score=0.92,
            threshold=0.7,
            confidence=0.95,
            evidence_refs=["exec:exec_sql_1", "step:1"],
            passed=True,
            blocked=False,
            details={"notes": "excellent"},
        )
        rec2 = EvaluationRecord(
            evaluation_id=_new_id(),
            execution_id="exec_sql_1",
            trajectory_id="traj_sql_1",
            evaluator_version="2.0.0",
            harness_version="harness_v1",
            dimension=EvaluationDimension.SAFETY,
            metric_name="safety_compliance_rate",
            score=1.0,
            threshold=1.0,
            confidence=1.0,
            evidence_refs=["exec:exec_sql_1"],
            passed=True,
            blocked=False,
        )

        await repo.save_batch([rec1, rec2])
        await session.commit()

    async with db.session_factory() as session:
        repo = EvaluationRepository(session)

        # Get by id
        fetched = await repo.get_by_id(rec1.evaluation_id)
        assert fetched is not None
        assert fetched.score == 0.92
        assert fetched.dimension == EvaluationDimension.TASK_SUCCESS
        assert fetched.evidence_refs == ["exec:exec_sql_1", "step:1"]

        # List by execution
        exec_recs = await repo.list_by_execution("exec_sql_1")
        assert len(exec_recs) == 2

        # List by harness
        harness_recs = await repo.list_by_harness("harness_v1")
        assert len(harness_recs) == 2

        # List by dimension
        dim_recs = await repo.list_by_dimension(EvaluationDimension.SAFETY)
        assert len(dim_recs) == 1

        # Baseline aggregates
        baseline = await repo.get_baseline_scores(evaluator_version="2.0.0")
        assert "task_completion_rate" in baseline
        assert baseline["task_completion_rate"] == 0.92
        assert baseline["safety_compliance_rate"] == 1.0


# ====================================================================
# 9. API V2 Evals Endpoints
# ====================================================================

@pytest.mark.asyncio
async def test_api_v2_evals_endpoints():
    app = FastAPI()
    app.include_router(evals_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Dimensions
        resp_dims = await client.get("/api/v2/evals/dimensions")
        assert resp_dims.status_code == 200
        dims = resp_dims.json()
        assert len(dims) == 11
        assert "task_success" in dims
        assert "regression" in dims

        # Compare
        compare_payload = {
            "candidate_id": "cand_api_1",
            "baseline_id": "base_api_1",
            "candidate_scores": {"task_completion_rate": 0.95, "safety_compliance_rate": 1.0},
            "baseline_scores": {"task_completion_rate": 0.90, "safety_compliance_rate": 1.0},
            "regression_threshold": 0.05,
        }
        resp_comp = await client.post("/api/v2/evals/compare", json=compare_payload)
        assert resp_comp.status_code == 200
        comp_data = resp_comp.json()
        assert comp_data["passed"] is True
        assert comp_data["regression_detected"] is False
        assert comp_data["composite_delta"] > 0.0
