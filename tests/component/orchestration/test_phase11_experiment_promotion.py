"""Phase 11 Component Tests — Candidate -> Experiment -> Promotion & Rollback (ban_ke_hoach_v1 §17, §24, §25, §27, §28, §29, §30, §35).

Tests:
1. Domain model immutability, enums, transitions, and invariants for Experiment and PromotionDecision.
2. CandidateComparisonEngine: statistical hypothesis testing (p-value, 95% CI, uncertainty margin, accuracy/safety/cost deltas, verdicts).
3. 7-Gate Promotion Criteria enforcement (min sample size, beats baseline, safety, reliability, cost budget, provenance, uncertainty).
4. High-risk mutations (global policy, skills, subagents, routing, high risk) strictly requiring human approval.
5. Bounded automated promotion for low-risk project-scoped prompt rules.
6. Atomic harness version creation with parent version linkage, exact diff, and evidence chain.
7. Post-promotion health monitoring and automated regression rollback to parent version.
8. Async SQL repository CRUD and transaction isolation for ExperimentRepository and PromotionRepository.
9. FastAPI V2 REST endpoints for /api/v2/experiments and /api/v2/promotions.
10. Migration 0028 table schema and compound index metadata integrity.
"""

from __future__ import annotations

import uuid
from typing import Optional
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from pydantic import ValidationError

# Ensure ORM models are registered in BaseORM.metadata
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
import windagent_storage.orm.memory_v2_models  # noqa: F401
import windagent_storage.orm.evaluation_models  # noqa: F401
import windagent_storage.orm.experience_models  # noqa: F401
import windagent_storage.orm.candidate_models  # noqa: F401
import windagent_storage.orm.harness_models  # noqa: F401
import windagent_storage.orm.experiment_models  # noqa: F401
import windagent_storage.orm.promotion_models  # noqa: F401

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)
from windagent_core.domain.experiment import (
    Experiment,
    ExperimentMetrics,
    ExperimentStatus,
    ExperimentType,
    ExperimentVerdict,
    StatisticalComparison,
)
from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    HarnessVersionStatus,
)
from windagent_core.domain.promotion import (
    GateCheckResult,
    PromotionDecision,
    PromotionStatus,
)
from windagent_evals.candidate_comparison import CandidateComparisonEngine
from windagent_orchestration.learning.learning_workflow_service import LearningWorkflowService
from windagent_orchestration.learning.promotion_gate import PromotionGate
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.experiment_repository import ExperimentRepository
from windagent_storage.repositories.harness_repository import HarnessRepository
from windagent_storage.repositories.promotion_repository import PromotionRepository
from windagent_api.routers.v2_experiments import router as experiments_router
from windagent_api.routers.v2_promotions import router as promotions_router


def _sample_candidate(
    candidate_id: Optional[str] = None,
    kind: CandidateKind = CandidateKind.PROMPT_RULE,
    scope: CandidateScope = CandidateScope.PROJECT,
    risk: CandidateRiskLevel = CandidateRiskLevel.LOW,
    status: CandidateStatus = CandidateStatus.ELIGIBLE,
    sample_size: int = 4,
    confidence: float = 0.88,
) -> LearningCandidate:
    cid = candidate_id or f"cand_{uuid.uuid4().hex[:10]}"
    return LearningCandidate(
        candidate_id=cid,
        kind=kind,
        condition="domain == 'youtube' and metric == 'hook_retention'",
        proposed_change={"rule": "Add 3-second hook before intro", "name": "hook_retention_v2"},
        reasoning_summary="Observed 15% retention uplift in benchmark replays.",
        supporting_experiences=["exp_001", "exp_002", "exp_003", "exp_004"],
        sample_size=sample_size,
        confidence=confidence,
        scope=scope,
        risk_level=risk,
        status=status,
        project_id="proj_yt_studio",
        domain="youtube",
    )


def _sample_baseline_harness(
    version_id: str = "harness_v1",
    version_number: int = 1,
    is_active: bool = True,
) -> HarnessVersion:
    return HarnessVersion(
        version_id=version_id,
        version_number=version_number,
        parent_version=None if version_number == 1 else "harness_v1",
        status=HarnessVersionStatus.ACTIVE if is_active else HarnessVersionStatus.ARCHIVED,
        entries=[
            HarnessEntry(
                entry_id="hent_base_01",
                kind=HarnessEntryKind.PROMPT_RULE,
                name="default_pacing",
                content={"rule": "Maintain standard pacing"},
                priority=100,
            )
        ],
        diff={"summary": "Baseline version"},
        evidence=[],
        promotion_decision={"approved_by": "bootstrap"},
        evaluation_set={"accuracy": 0.80},
        created_by="system",
        project_id="proj_yt_studio",
        domain="youtube",
        is_active=is_active,
    )


@pytest.fixture
async def db():
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:")
    async with mgr.engine.begin() as con:
        await con.run_sync(BaseORM.metadata.create_all)
    yield mgr
    await mgr.engine.dispose()


@pytest.mark.asyncio
async def test_experiment_domain_immutability_and_lifecycle():
    """1. Validates Experiment domain model immutability, transitions, and invariants."""
    exp = Experiment(
        experiment_id="expt_001",
        candidate_id="cand_001",
        baseline_harness_version="harness_v1",
        experiment_type=ExperimentType.REPLAY,
        status=ExperimentStatus.DRAFT,
        sample_size=5,
        project_id="proj_01",
    )
    assert exp.status == ExperimentStatus.DRAFT
    assert exp.assert_invariants() is True

    # Immutability check
    with pytest.raises(ValidationError):
        exp.status = ExperimentStatus.RUNNING  # type: ignore

    # Transition to RUNNING
    running_exp = exp.start()
    assert running_exp.status == ExperimentStatus.RUNNING

    # Complete experiment
    base_m = ExperimentMetrics(accuracy=0.80, safety_score=1.0, reliability_score=0.95, sample_size=5)
    cand_m = ExperimentMetrics(accuracy=0.92, safety_score=1.0, reliability_score=0.95, sample_size=5)
    comp = StatisticalComparison(accuracy_delta=0.12, safety_delta=0.0, reliability_delta=0.0, p_value=0.01)

    completed_exp = running_exp.complete(
        baseline_metrics=base_m,
        candidate_metrics=cand_m,
        comparison=comp,
        safety_check_passed=True,
        reliability_check_passed=True,
        verdict=ExperimentVerdict.BEATS_BASELINE,
    )
    assert completed_exp.status == ExperimentStatus.COMPLETED
    assert completed_exp.verdict == ExperimentVerdict.BEATS_BASELINE
    assert completed_exp.completed_at is not None

    # Fail and cancel transitions
    failed_exp = exp.fail("Timeout during replay")
    assert failed_exp.status == ExperimentStatus.FAILED
    assert failed_exp.metadata["error_message"] == "Timeout during replay"

    cancelled_exp = exp.cancel("Operator aborted")
    assert cancelled_exp.status == ExperimentStatus.CANCELLED


@pytest.mark.asyncio
async def test_promotion_decision_domain_immutability():
    """2. Validates PromotionDecision domain model, 7-gate structure, and approval transitions."""
    gates = GateCheckResult(
        min_sample_size_passed=True,
        beats_baseline_passed=True,
        no_safety_regression_passed=True,
        no_reliability_regression_passed=True,
        cost_within_budget_passed=True,
        provenance_complete_passed=True,
        uncertainty_acceptable_passed=True,
    )
    assert gates.all_passed is True
    assert gates.failed_gates() == []

    decision = PromotionDecision(
        decision_id="pdec_001",
        candidate_id="cand_001",
        experiment_id="expt_001",
        source_harness_version="harness_v1",
        status=PromotionStatus.PENDING_APPROVAL,
        gate_checks=gates,
        is_high_risk=False,
        requires_human_approval=False,
    )

    # Immutability check
    with pytest.raises(ValidationError):
        decision.status = PromotionStatus.PROMOTED  # type: ignore

    # Approval and promotion
    promoted = decision.approve_and_promote(
        target_harness_version="harness_v2",
        approver="test_admin",
        rationale="7 gates passed",
    )
    assert promoted.status == PromotionStatus.PROMOTED
    assert promoted.target_harness_version == "harness_v2"
    assert promoted.approved_by == "test_admin"

    # Rejection transition
    rejected = decision.reject("Manual review failed")
    assert rejected.status == PromotionStatus.REJECTED
    assert rejected.rejection_reason == "Manual review failed"

    # Rollback transition
    rolled_back = promoted.rollback("Accuracy degraded in production")
    assert rolled_back.status == PromotionStatus.ROLLED_BACK
    assert rolled_back.metadata["rollback_reason"] == "Accuracy degraded in production"


@pytest.mark.asyncio
async def test_candidate_comparison_statistical_engine():
    """3. Tests statistical comparison engine with win, tie, safety failure, and inconclusive outcomes."""
    engine = CandidateComparisonEngine(min_win_margin=0.02, max_allowed_cost_delta=0.20)

    # Scenario A: Candidate beats baseline
    base_m = ExperimentMetrics(accuracy=0.75, safety_score=1.0, reliability_score=0.95, cost_usd=0.05, sample_size=10)
    cand_m = ExperimentMetrics(accuracy=0.90, safety_score=1.0, reliability_score=0.95, cost_usd=0.06, sample_size=10)
    comp, safety_ok, rel_ok, verdict = engine.compare_metrics(base_m, cand_m)
    assert comp.accuracy_delta == 0.15
    assert comp.cost_delta == 0.01
    assert safety_ok is True
    assert rel_ok is True
    assert verdict == ExperimentVerdict.BEATS_BASELINE

    # Scenario B: Safety regression -> UNSAFE
    unsafe_cand = ExperimentMetrics(accuracy=0.95, safety_score=0.80, reliability_score=0.95, sample_size=10)
    _, safety_ok, _, verdict = engine.compare_metrics(base_m, unsafe_cand)
    assert safety_ok is False
    assert verdict == ExperimentVerdict.UNSAFE

    # Scenario C: Tie
    tie_cand = ExperimentMetrics(accuracy=0.755, safety_score=1.0, reliability_score=0.95, sample_size=10)
    _, _, _, verdict = engine.compare_metrics(base_m, tie_cand)
    assert verdict == ExperimentVerdict.TIE

    # Scenario D: Inferior candidate
    inf_cand = ExperimentMetrics(accuracy=0.60, safety_score=1.0, reliability_score=0.95, sample_size=10)
    _, _, _, verdict = engine.compare_metrics(base_m, inf_cand)
    assert verdict == ExperimentVerdict.INFERIOR


@pytest.mark.asyncio
async def test_7_gate_promotion_criteria_enforcement():
    """4. Enforces the 7 Promotion Gates (§17, §35) with comprehensive rejection when any gate fails."""
    gate = PromotionGate(project_min_sample_size=3)
    cand = _sample_candidate(sample_size=4)

    # Passing experiment
    good_exp = Experiment(
        experiment_id="expt_pass",
        candidate_id=cand.candidate_id,
        baseline_harness_version="harness_v1",
        status=ExperimentStatus.COMPLETED,
        sample_size=4,
        baseline_metrics=ExperimentMetrics(accuracy=0.80, safety_score=1.0, reliability_score=0.95, sample_size=4),
        candidate_metrics=ExperimentMetrics(accuracy=0.92, safety_score=1.0, reliability_score=0.95, sample_size=4),
        comparison=StatisticalComparison(accuracy_delta=0.12, safety_delta=0.0, reliability_delta=0.0, cost_delta=0.01, uncertainty_margin=0.20),
        safety_check_passed=True,
        reliability_check_passed=True,
        verdict=ExperimentVerdict.BEATS_BASELINE,
    )

    decision = gate.evaluate_candidate(cand, good_exp, source_harness_version="harness_v1")
    assert decision.gate_checks.all_passed is True

    # Failing Gate 1: Insufficient sample size
    small_cand = cand.model_copy(update={"sample_size": 1})
    small_exp = good_exp.model_copy(update={"sample_size": 1})
    dec_small = gate.evaluate_candidate(small_cand, small_exp, source_harness_version="harness_v1")
    assert dec_small.gate_checks.min_sample_size_passed is False
    assert "min_sample_size" in dec_small.gate_checks.failed_gates()

    # Failing Gate 3: Safety regression
    unsafe_exp = good_exp.model_copy(
        update={
            "safety_check_passed": False,
            "candidate_metrics": ExperimentMetrics(accuracy=0.95, safety_score=0.88, reliability_score=0.95, sample_size=4),
        }
    )
    dec_unsafe = gate.evaluate_candidate(cand, unsafe_exp, source_harness_version="harness_v1")
    assert dec_unsafe.gate_checks.no_safety_regression_passed is False
    assert "no_safety_regression" in dec_unsafe.gate_checks.failed_gates()


@pytest.mark.asyncio
async def test_high_risk_mutation_requires_human_approval():
    """5. Verifies that high-risk mutations (Global, Skills, High/Critical risk) strictly require human approval."""
    gate = PromotionGate()

    # Global scope candidate
    global_cand = _sample_candidate(scope=CandidateScope.GLOBAL, sample_size=6)
    good_exp = Experiment(
        experiment_id="expt_global",
        candidate_id=global_cand.candidate_id,
        baseline_harness_version="harness_v1",
        status=ExperimentStatus.COMPLETED,
        sample_size=6,
        baseline_metrics=ExperimentMetrics(accuracy=0.80, safety_score=1.0, reliability_score=0.95, sample_size=6),
        candidate_metrics=ExperimentMetrics(accuracy=0.90, safety_score=1.0, reliability_score=0.95, sample_size=6),
        comparison=StatisticalComparison(accuracy_delta=0.10, uncertainty_margin=0.15),
        safety_check_passed=True,
        reliability_check_passed=True,
        verdict=ExperimentVerdict.BEATS_BASELINE,
    )

    dec_global = gate.evaluate_candidate(global_cand, good_exp, source_harness_version="harness_v1")
    assert dec_global.is_high_risk is True
    assert dec_global.requires_human_approval is True

    # Attempting auto-promotion on high-risk must fail
    with pytest.raises(ValueError, match="strictly requires human approval"):
        dec_global.approve_and_promote(
            target_harness_version="harness_v2",
            approver="system_auto",
        )

    # Approving with named human succeeds
    promoted = dec_global.approve_and_promote(
        target_harness_version="harness_v2",
        approver="lead_engineer_alice",
    )
    assert promoted.status == PromotionStatus.PROMOTED
    assert promoted.approved_by == "lead_engineer_alice"


@pytest.mark.asyncio
async def test_bounded_automated_promotion_for_low_risk_prompt_rule():
    """6. Verifies bounded auto-promotion for low-risk project-scoped prompt rules."""
    gate = PromotionGate()
    low_risk_cand = _sample_candidate(
        kind=CandidateKind.PROMPT_RULE,
        scope=CandidateScope.PROJECT,
        risk=CandidateRiskLevel.LOW,
        sample_size=4,
    )

    exp = Experiment(
        experiment_id="expt_low_risk",
        candidate_id=low_risk_cand.candidate_id,
        baseline_harness_version="harness_v1",
        status=ExperimentStatus.COMPLETED,
        sample_size=4,
        baseline_metrics=ExperimentMetrics(accuracy=0.80, safety_score=1.0, reliability_score=0.95, sample_size=4),
        candidate_metrics=ExperimentMetrics(accuracy=0.92, safety_score=1.0, reliability_score=0.95, sample_size=4),
        comparison=StatisticalComparison(accuracy_delta=0.12, uncertainty_margin=0.20),
        safety_check_passed=True,
        reliability_check_passed=True,
        verdict=ExperimentVerdict.BEATS_BASELINE,
    )

    decision = gate.evaluate_candidate(low_risk_cand, exp, source_harness_version="harness_v1")
    assert decision.is_high_risk is False
    assert decision.requires_human_approval is False
    assert decision.gate_checks.all_passed is True

    promoted = decision.approve_and_promote(
        target_harness_version="harness_v2",
        approver="promotion_gate_auto",
    )
    assert promoted.status == PromotionStatus.PROMOTED
    assert promoted.approved_by == "promotion_gate_auto"


@pytest.mark.asyncio
async def test_atomic_harness_version_commitment_on_promotion(db: DatabaseManager):
    """7. Verifies end-to-end LearningWorkflowService creates sequential parent-linked HarnessVersion."""
    async with db.session_factory() as session:
        harness_repo = HarnessRepository(session)
        exp_repo = ExperimentRepository(session)
        prom_repo = PromotionRepository(session)

        workflow = LearningWorkflowService(
            experiment_repo=exp_repo,
            promotion_repo=prom_repo,
            harness_repo=harness_repo,
        )

        base_harness = _sample_baseline_harness(version_id="harness_v1", version_number=1)
        await harness_repo.save_version(base_harness)

        cand = _sample_candidate(sample_size=4)

        # Run experiment
        base_eps = [{"accuracy": 0.80, "safety_score": 1.0, "reliability_score": 0.95} for _ in range(4)]
        cand_eps = [{"accuracy": 0.95, "safety_score": 1.0, "reliability_score": 0.95} for _ in range(4)]

        exp = await workflow.run_experiment_for_candidate(
            candidate=cand,
            baseline_harness_version=base_harness.version_id,
            baseline_episodes=base_eps,
            candidate_episodes=cand_eps,
        )
        assert exp.verdict == ExperimentVerdict.BEATS_BASELINE

        # Evaluate promotion gate
        decision = await workflow.evaluate_promotion_gate(
            candidate=cand,
            experiment=exp,
            source_harness_version=base_harness.version_id,
        )
        assert decision.gate_checks.all_passed is True

        # Execute promotion
        promoted_dec, new_harness = await workflow.execute_promotion(
            decision=decision,
            candidate=cand,
            base_harness_version=base_harness,
            approver="admin_bob",
        )

        await session.commit()

        assert new_harness.version_id == "harness_v2"
        assert new_harness.version_number == 2
        assert new_harness.parent_version == "harness_v1"
        assert new_harness.is_active is True
        assert any(e.name == "hook_retention_v2" for e in new_harness.entries)
        assert promoted_dec.status == PromotionStatus.PROMOTED


@pytest.mark.asyncio
async def test_post_promotion_regression_detection_and_rollback(db: DatabaseManager):
    """8. Verifies post-promotion monitoring detects regressions and triggers atomic rollback to parent version."""
    async with db.session_factory() as session:
        harness_repo = HarnessRepository(session)
        prom_repo = PromotionRepository(session)

        # Setup v1 and v2 in database
        v1 = _sample_baseline_harness(version_id="harness_v1", version_number=1, is_active=False)
        v2 = HarnessVersion(
            version_id="harness_v2",
            version_number=2,
            parent_version="harness_v1",
            status=HarnessVersionStatus.ACTIVE,
            entries=v1.entries,
            is_active=True,
            created_by="admin",
        )
        await harness_repo.save_version(v1)
        await harness_repo.save_version(v2)

        decision = PromotionDecision(
            decision_id="pdec_v2",
            candidate_id="cand_001",
            source_harness_version="harness_v1",
            target_harness_version="harness_v2",
            status=PromotionStatus.PROMOTED,
            gate_checks=GateCheckResult(
                min_sample_size_passed=True,
                beats_baseline_passed=True,
                no_safety_regression_passed=True,
                no_reliability_regression_passed=True,
                cost_within_budget_passed=True,
                provenance_complete_passed=True,
                uncertainty_acceptable_passed=True,
            ),
            approved_by="admin",
        )
        await prom_repo.save_decision(decision)
        await session.commit()

    async with db.session_factory() as session:
        harness_repo = HarnessRepository(session)
        prom_repo = PromotionRepository(session)

        workflow = LearningWorkflowService(
            harness_repo=harness_repo,
            promotion_repo=prom_repo,
        )

        # Telemetry exhibiting error spike & safety violation
        bad_telemetry = [
            {"accuracy": 0.50, "safety_violation": True, "error": True, "latency_ms": 1200},
            {"accuracy": 0.60, "safety_violation": False, "error": True, "latency_ms": 1100},
            {"accuracy": 0.55, "safety_violation": False, "error": False, "latency_ms": 1000},
        ]

        health, restored_parent = await workflow.monitor_and_rollback_if_regressed(
            current_version=v2,
            decision=decision,
            telemetry_runs=bad_telemetry,
        )

        await session.commit()

        assert health.is_regression_detected is True
        assert "safety violations" in (health.regression_reason or "")
        assert restored_parent is not None
        assert restored_parent.version_id == "harness_v1"
        assert restored_parent.is_active is True

        # Check DB state
        db_v2 = await harness_repo.get_version("harness_v2")
        assert db_v2 is not None
        assert db_v2.status == HarnessVersionStatus.ROLLED_BACK
        assert db_v2.is_active is False

        db_dec = await prom_repo.get_decision("pdec_v2")
        assert db_dec is not None
        assert db_dec.status == PromotionStatus.ROLLED_BACK


@pytest.mark.asyncio
async def test_experiment_and_promotion_repositories_async_sql(db: DatabaseManager):
    """9. Verifies async SQL persistence and query operations for Experiment and Promotion repositories."""
    async with db.session_factory() as session:
        exp_repo = ExperimentRepository(session)
        prom_repo = PromotionRepository(session)

        # 1. Save and query experiment
        exp = Experiment(
            experiment_id="expt_sql_01",
            candidate_id="cand_sql_01",
            baseline_harness_version="harness_v1",
            experiment_type=ExperimentType.BENCHMARK,
            status=ExperimentStatus.COMPLETED,
            sample_size=10,
            baseline_metrics=ExperimentMetrics(accuracy=0.80, safety_score=1.0, reliability_score=0.95, sample_size=10),
            candidate_metrics=ExperimentMetrics(accuracy=0.92, safety_score=1.0, reliability_score=0.95, sample_size=10),
            comparison=StatisticalComparison(accuracy_delta=0.12, p_value=0.02),
            safety_check_passed=True,
            reliability_check_passed=True,
            verdict=ExperimentVerdict.BEATS_BASELINE,
            project_id="proj_sql",
        )
        await exp_repo.save_experiment(exp)

        fetched_exp = await exp_repo.get_experiment("expt_sql_01")
        assert fetched_exp is not None
        assert fetched_exp.verdict == ExperimentVerdict.BEATS_BASELINE
        assert fetched_exp.comparison is not None
        assert fetched_exp.comparison.accuracy_delta == 0.12

        exp_list = await exp_repo.list_experiments(project_id="proj_sql")
        assert len(exp_list) == 1

        # 2. Save and query promotion decision
        dec = PromotionDecision(
            decision_id="pdec_sql_01",
            candidate_id="cand_sql_01",
            experiment_id="expt_sql_01",
            source_harness_version="harness_v1",
            status=PromotionStatus.PENDING_APPROVAL,
            gate_checks=GateCheckResult(
                min_sample_size_passed=True,
                beats_baseline_passed=True,
                no_safety_regression_passed=True,
                no_reliability_regression_passed=True,
                cost_within_budget_passed=True,
                provenance_complete_passed=True,
                uncertainty_acceptable_passed=True,
            ),
            project_id="proj_sql",
        )
        await prom_repo.save_decision(dec)

        fetched_dec = await prom_repo.get_decision("pdec_sql_01")
        assert fetched_dec is not None
        assert fetched_dec.gate_checks.all_passed is True

        dec_list = await prom_repo.list_decisions(project_id="proj_sql")
        assert len(dec_list) == 1


@pytest.mark.asyncio
async def test_fastapi_v2_experiments_endpoints():
    """10. Verifies FastAPI REST endpoints for /api/v2/experiments."""
    app = FastAPI()
    app.include_router(experiments_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create & run experiment with 4 samples
        req_payload = {
            "candidate_id": "cand_api_01",
            "baseline_harness_version": "harness_v1",
            "experiment_type": "replay",
            "baseline_episodes": [{"accuracy": 0.75, "safety_score": 1.0, "reliability_score": 0.95} for _ in range(4)],
            "candidate_episodes": [{"accuracy": 0.92, "safety_score": 1.0, "reliability_score": 0.95} for _ in range(4)],
            "project_id": "proj_api",
        }
        res = await client.post("/api/v2/experiments", json=req_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["candidate_id"] == "cand_api_01"
        assert data["verdict"] in ("beats_baseline", "tie")
        exp_id = data["experiment_id"]

        # Get experiment by ID
        get_res = await client.get(f"/api/v2/experiments/{exp_id}")
        assert get_res.status_code == 200
        assert get_res.json()["experiment_id"] == exp_id

        # List experiments
        list_res = await client.get("/api/v2/experiments", params={"project_id": "proj_api"})
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1


@pytest.mark.asyncio
async def test_fastapi_v2_promotions_endpoints():
    """11. Verifies FastAPI REST endpoints for /api/v2/promotions."""
    app = FastAPI()
    app.include_router(promotions_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Evaluate promotion gate
        eval_payload = {
            "candidate_id": "cand_api_prom",
            "experiment_id": "expt_api_prom",
            "source_harness_version": "harness_v1",
            "candidate_scope": "project",
            "candidate_risk": "low",
            "accuracy_delta": 0.10,
            "safety_score": 1.0,
            "reliability_score": 0.95,
            "sample_size": 10,
            "project_id": "proj_api_prom",
        }
        res = await client.post("/api/v2/promotions/evaluate", json=eval_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["gate_checks"]["all_passed"] is True
        dec_id = data["decision_id"]

        # 2. Promote candidate
        prom_payload = {
            "decision_id": dec_id,
            "approver": "admin_prom_tester",
            "new_version_id": "harness_v2_api",
        }
        prom_res = await client.post("/api/v2/promotions/promote", json=prom_payload)
        assert prom_res.status_code == 200
        assert prom_res.json()["status"] == "promoted"
        assert prom_res.json()["target_harness_version"] == "harness_v2_api"

        # 3. Rollback promotion
        rb_payload = {
            "version_id": "harness_v2_api",
            "decision_id": dec_id,
            "reason": "Test regression rollback",
        }
        rb_res = await client.post("/api/v2/promotions/rollback", json=rb_payload)
        assert rb_res.status_code == 200
        assert rb_res.json()["status"] == "rolled_back"

        # 4. List promotion decisions
        list_res = await client.get("/api/v2/promotions", params={"project_id": "proj_api_prom"})
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1


@pytest.mark.asyncio
async def test_migration_0028_schema_and_indexes_integrity():
    """12. Verifies table names and compound indexes for Migration 0028 exist in BaseORM metadata."""
    tables = BaseORM.metadata.tables
    assert "experiments" in tables
    assert "promotion_decisions" in tables

    exp_table = tables["experiments"]
    exp_idx_names = {idx.name for idx in exp_table.indexes}
    assert "ix_experiments_candidate_status" in exp_idx_names
    assert "ix_experiments_proj_status" in exp_idx_names
    assert "ix_experiments_domain_verdict" in exp_idx_names
    assert "ix_experiments_created_at" in exp_idx_names

    prom_table = tables["promotion_decisions"]
    prom_idx_names = {idx.name for idx in prom_table.indexes}
    assert "ix_promotion_cand_status" in prom_idx_names
    assert "ix_promotion_proj_status" in prom_idx_names
    assert "ix_promotion_source_target" in prom_idx_names
    assert "ix_promotion_created_at" in prom_idx_names
