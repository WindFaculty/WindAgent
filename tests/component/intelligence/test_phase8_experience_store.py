"""Phase 8 Component Tests — Experience Store (ban_ke_hoach_v1 §13 & §24).

Tests:
1. Experience domain model immutability, states, and transition methods.
2. Experience vs LearnedRule distinction invariant.
3. ExecutionTrajectory projection into empirical Experience.
4. Evaluation enrichment and transition to EVALUATED state.
5. Experience diagnosis, attribution engine, and YouTube signal correlation.
6. Learning candidate readiness qualification predicate.
7. ExperienceStore service in-memory CRUD, querying, and filtering.
8. ExperienceRepository SQL async persistence, batch operations, and queries.
9. API V2 experiences endpoints (/api/v2/experiences, diagnose, archive, learning-ready).
10. Database schema & table metadata integrity for experience_records.
"""

from __future__ import annotations

import uuid
from typing import Optional
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from pydantic import ValidationError

# Ensure ORM models are registered
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
import windagent_storage.orm.memory_v2_models  # noqa: F401
import windagent_storage.orm.evaluation_models  # noqa: F401
import windagent_storage.orm.experience_models  # noqa: F401

from windagent_core.domain.evaluation import (
    EvaluationDimension,
    EvaluationRecord,
)
from windagent_core.domain.experience import (
    Experience,
    ExperienceState,
)
from windagent_core.domain.trajectory import (
    ExecutionTrajectory,
    TrajectoryArtifactRef,
    TrajectoryMetric,
    TrajectoryOutcome,
    TrajectoryStep,
)
from windagent_intelligence.experience.diagnostics import ExperienceDiagnostics
from windagent_intelligence.experience.store import ExperienceStore
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.experience_repository import ExperienceRepository
from windagent_api.routers.v2_experiences import router as experiences_router


def _new_id(prefix: str = "exp") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _sample_trajectory(execution_id: Optional[str] = None) -> ExecutionTrajectory:
    exec_id = execution_id or f"run_{uuid.uuid4().hex[:10]}"
    step1 = TrajectoryStep(
        sequence=0,
        kind="tool_execution",
        identifier="step_0",
        status="completed",
        details={"tool_name": "code_analysis", "file": "main.py"},
        provenance={"source": "agent_run"},
    )
    step2 = TrajectoryStep(
        sequence=1,
        kind="tool_execution",
        identifier="step_1",
        status="completed",
        details={"tool_name": "file_writer", "file": "output.json"},
        provenance={"source": "agent_run"},
    )
    artifact = TrajectoryArtifactRef(
        artifact_id="art_1",
        kind="tool_result",
        sequence=1,
        content_redacted_preview="output.json",
        provenance={"path": "output.json", "size_bytes": 2},
    )
    metrics = TrajectoryMetric(
        prompt_tokens=1200,
        completion_tokens=300,
        total_tokens=1500,
        cost_usd=0.015,
        latency_ms=1250,
        attempt_count=1,
        retry_count=0,
    )
    outcome = TrajectoryOutcome(
        terminal_state="COMPLETED",
        succeeded=True,
        has_terminal_evidence=True,
    )
    traj_id = f"traj_{uuid.uuid4().hex[:10]}"
    return ExecutionTrajectory(
        execution_id=exec_id,
        conversation_id=f"conv_{uuid.uuid4().hex[:8]}",
        parent_task_id=f"task_{uuid.uuid4().hex[:8]}",
        agent_session_id=f"sess_{uuid.uuid4().hex[:8]}",
        harness_version="harness_v1.0",
        steps=(step1, step2),
        artifacts=(artifact,),
        metrics=metrics,
        outcome=outcome,
        completeness="COMPLETE",
        source_identifiers={"agent_run_id": exec_id, "trajectory_id": traj_id},
    )


@pytest.fixture
async def db():
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:")
    async with mgr.engine.begin() as con:
        await con.run_sync(BaseORM.metadata.create_all)
    yield mgr
    await mgr.engine.dispose()


# ====================================================================
# 1. Experience Domain Model Immutability & Lifecycle States
# ====================================================================

def test_experience_states_and_immutability():
    """Experience domain model enforces immutability and transitions through states."""
    expected_states = {"raw", "evaluated", "diagnosed", "archived"}
    assert {s.value for s in ExperienceState} == expected_states

    exp = Experience(
        experience_id=_new_id(),
        execution_id="run_001",
        state=ExperienceState.RAW,
        context={"goal": "Summarize research papers"},
        metrics={"cost_usd": 0.02},
    )
    assert exp.state == ExperienceState.RAW
    assert exp.confidence == 0.0

    # Immutability check
    with pytest.raises(ValidationError):
        exp.confidence = 0.9  # type: ignore

    # Transition to EVALUATED
    eval_rec = {
        "evaluation_id": "eval_1",
        "dimension": "task_success",
        "score": 0.95,
        "passed": True,
        "blocked": False,
    }
    evaluated_exp = exp.with_evaluations([eval_rec])
    assert evaluated_exp.state == ExperienceState.EVALUATED
    assert len(evaluated_exp.evaluator_results) == 1
    assert evaluated_exp.experience_id == exp.experience_id

    # Transition to DIAGNOSED
    diagnosed_exp = evaluated_exp.with_diagnosis(
        hypothesis="Batch summarization reduces token usage by 15%",
        confidence=0.85,
    )
    assert diagnosed_exp.state == ExperienceState.DIAGNOSED
    assert diagnosed_exp.hypothesis == "Batch summarization reduces token usage by 15%"
    assert diagnosed_exp.confidence == 0.85

    # Transition to ARCHIVED
    archived_exp = diagnosed_exp.archive()
    assert archived_exp.state == ExperienceState.ARCHIVED


# ====================================================================
# 2. Distinction: Experience != LearnedRule
# ====================================================================

def test_experience_distinction_from_learned_rules():
    """Experience represents empirical observations, not an active learned rule or policy."""
    exp = Experience(
        experience_id=_new_id(),
        execution_id="run_002",
        state=ExperienceState.DIAGNOSED,
        context={"topic_cluster": "AI Agent Coding", "hook_pattern": "demo-first"},
        metrics={"retention_30s": 0.73},
        evaluator_results=[{"dimension": "task_success", "score": 1.0, "passed": True}],
        hypothesis="Demo-first hook improved 30s retention by +12pp",
        confidence=0.75,
    )
    # Experience asserts observational integrity
    assert exp.assert_empirical_experience() is True
    # Experience is not a rule
    assert not hasattr(exp, "promoted_rule_id")
    assert not hasattr(exp, "active_policy_mutation")


# ====================================================================
# 3. Projection from ExecutionTrajectory
# ====================================================================

def test_experience_creation_from_execution_trajectory():
    """ExperienceStore creates structured Experience from ExecutionTrajectory."""
    store = ExperienceStore()
    traj = _sample_trajectory()

    exp = store.create_from_trajectory(
        trajectory=traj,
        project_id="proj_alpha",
    )

    assert exp.experience_id.startswith("exp_")
    assert exp.execution_id == traj.execution_id
    assert exp.trajectory_id == traj.source_identifiers["trajectory_id"]
    assert exp.project_id == "proj_alpha"
    assert exp.state == ExperienceState.RAW
    assert exp.result["terminal_state"] == "COMPLETED"
    assert exp.result["succeeded"] is True
    assert exp.result["total_steps"] == 2
    assert len(exp.artifacts) == 1
    assert exp.artifacts[0]["artifact_id"] == "art_1"
    assert exp.metrics["total_tokens"] == 1500
    assert exp.metrics["cost_usd"] == 0.015


# ====================================================================
# 4. Evaluation Enrichment
# ====================================================================

def test_experience_evaluation_enrichment():
    """Attaching EvaluationRecords enriches Experience and updates state to EVALUATED."""
    store = ExperienceStore()
    traj = _sample_trajectory()
    exp = store.create_from_trajectory(trajectory=traj)

    traj_id = traj.source_identifiers["trajectory_id"]
    eval_rec1 = EvaluationRecord(
        evaluation_id=_new_id("eval"),
        execution_id=traj.execution_id,
        trajectory_id=traj_id,
        dimension=EvaluationDimension.TASK_SUCCESS,
        metric_name="task_completion",
        score=1.0,
        threshold=0.7,
        confidence=1.0,
        evidence_refs=["step_0", "step_1"],
        passed=True,
        blocked=False,
    )
    eval_rec2 = EvaluationRecord(
        evaluation_id=_new_id("eval"),
        execution_id=traj.execution_id,
        trajectory_id=traj_id,
        dimension=EvaluationDimension.SAFETY,
        metric_name="secret_leakage",
        score=1.0,
        threshold=1.0,
        confidence=1.0,
        evidence_refs=["output.json"],
        passed=True,
        blocked=False,
    )

    evaluated = store.attach_evaluations(exp.experience_id, [eval_rec1, eval_rec2])
    assert evaluated.state == ExperienceState.EVALUATED
    assert len(evaluated.evaluator_results) == 2
    assert evaluated.evaluator_results[0]["dimension"] == "task_success"
    assert evaluated.evaluator_results[1]["dimension"] == "safety"


# ====================================================================
# 5. Experience Diagnostics & Attribution Engine
# ====================================================================

def test_experience_diagnosis_and_attribution():
    """ExperienceDiagnostics attributes drivers, calculates confidence, and produces hypothesis."""
    store = ExperienceStore()
    traj = _sample_trajectory()

    # Create experience with YouTube telemetry (§22)
    exp = Experience(
        experience_id=_new_id(),
        execution_id=traj.execution_id,
        trajectory_id=traj.source_identifiers["trajectory_id"],
        state=ExperienceState.EVALUATED,
        context={"topic_cluster": "AI Agent Coding", "hook_pattern": "demo-first"},
        metrics={"retention_30s": 0.73},
        evaluator_results=[
            {"dimension": "task_success", "score": 0.95, "passed": True, "confidence": 0.9},
            {"dimension": "artifact_quality", "score": 0.90, "passed": True, "confidence": 0.9},
        ],
    )
    store.save(exp)

    diagnosed = store.diagnose(
        exp.experience_id,
        baseline_metrics={"retention_30s": 0.61},
    )

    assert diagnosed.state == ExperienceState.DIAGNOSED
    assert "demo-first" in diagnosed.hypothesis
    assert "+12.0pp" in diagnosed.hypothesis
    assert diagnosed.confidence >= 0.65


def test_experience_diagnosis_safety_block_zero_confidence():
    """Safety violation causes zero confidence and fail-closed diagnosis."""
    exp = Experience(
        experience_id=_new_id(),
        execution_id="run_safety_err",
        state=ExperienceState.EVALUATED,
        metrics={"cost_usd": 0.01},
        evaluator_results=[
            {"dimension": "safety", "score": 0.0, "passed": False, "blocked": True},
        ],
    )
    diagnosed = ExperienceDiagnostics.attribute_experience(exp)
    assert diagnosed.state == ExperienceState.DIAGNOSED
    assert diagnosed.confidence == 0.0
    assert "safety" in diagnosed.hypothesis.lower()


# ====================================================================
# 6. Learning Candidate Readiness Qualification Predicate
# ====================================================================

def test_experience_candidate_readiness_predicate():
    """is_learning_candidate_ready enforces state=DIAGNOSED, confidence threshold, and evidence."""
    exp_raw = Experience(experience_id=_new_id(), execution_id="r1", state=ExperienceState.RAW)
    assert exp_raw.is_learning_candidate_ready(min_confidence=0.6) is False

    exp_eval = Experience(
        experience_id=_new_id(),
        execution_id="r2",
        state=ExperienceState.EVALUATED,
        evaluator_results=[{"dimension": "task_success", "score": 0.9, "passed": True}],
    )
    assert exp_eval.is_learning_candidate_ready(min_confidence=0.6) is False

    exp_diagnosed_low_conf = Experience(
        experience_id=_new_id(),
        execution_id="r3",
        state=ExperienceState.DIAGNOSED,
        hypothesis="Weak hypothesis",
        confidence=0.45,
        evaluator_results=[{"dimension": "task_success", "score": 0.9, "passed": True}],
    )
    assert exp_diagnosed_low_conf.is_learning_candidate_ready(min_confidence=0.6) is False

    exp_qualified = Experience(
        experience_id=_new_id(),
        execution_id="r4",
        state=ExperienceState.DIAGNOSED,
        hypothesis="Demonstrated reliable tool execution with optimal token budget",
        confidence=0.82,
        evaluator_results=[{"dimension": "task_success", "score": 0.95, "passed": True}],
    )
    assert exp_qualified.is_learning_candidate_ready(min_confidence=0.6) is True


# ====================================================================
# 7. ExperienceStore Service In-Memory Operations & Filtering
# ====================================================================

def test_experience_store_service_crud_and_queries():
    """ExperienceStore supports CRUD, list filtering, and learning-ready querying."""
    store = ExperienceStore()
    p1 = "proj_01"
    p2 = "proj_02"

    exp1 = Experience(
        experience_id=_new_id(),
        execution_id="r_01",
        project_id=p1,
        state=ExperienceState.RAW,
    )
    exp2 = Experience(
        experience_id=_new_id(),
        execution_id="r_02",
        project_id=p1,
        state=ExperienceState.DIAGNOSED,
        hypothesis="Hypothesis 2",
        confidence=0.85,
        evaluator_results=[{"dimension": "task_success", "score": 0.9, "passed": True}],
    )
    exp3 = Experience(
        experience_id=_new_id(),
        execution_id="r_03",
        project_id=p2,
        state=ExperienceState.DIAGNOSED,
        hypothesis="Hypothesis 3",
        confidence=0.90,
        evaluator_results=[{"dimension": "task_success", "score": 0.9, "passed": True}],
    )

    store.save(exp1)
    store.save(exp2)
    store.save(exp3)

    assert store.get(exp1.experience_id) == exp1
    assert len(store.list(project_id=p1)) == 2
    assert len(store.list(project_id=p1, state=ExperienceState.DIAGNOSED)) == 1
    assert len(store.list_learning_ready(project_id=p1)) == 1
    assert len(store.list_learning_ready()) == 2

    # Test archive
    archived = store.archive(exp2.experience_id)
    assert archived.state == ExperienceState.ARCHIVED

    # Test delete
    assert store.delete(exp1.experience_id) is True
    assert store.get(exp1.experience_id) is None


# ====================================================================
# 8. ExperienceRepository Async SQL Persistence
# ====================================================================

@pytest.mark.asyncio
async def test_experience_repository_sql_crud(db):
    """ExperienceRepository async SQL persistence, batch saving, and state updates."""
    exp1 = Experience(
        experience_id=_new_id(),
        execution_id="run_sql_01",
        trajectory_id="traj_sql_01",
        project_id="proj_sql",
        state=ExperienceState.RAW,
        context={"goal": "Build landing page", "parameters": {"theme": "dark"}},
        decision={"steps": [{"step": 1, "tool": "template_gen"}]},
        action={"steps": [{"status": "ok"}]},
        result={"status": "COMPLETED", "total_steps": 1},
        artifacts=[{"path": "index.html", "size_bytes": 1024}],
        metrics={"total_tokens": 800, "cost_usd": 0.008},
        evaluator_results=[],
        confidence=0.0,
        provenance={"harness": "v1"},
    )
    exp2 = Experience(
        experience_id=_new_id(),
        execution_id="run_sql_02",
        trajectory_id="traj_sql_02",
        project_id="proj_sql",
        state=ExperienceState.EVALUATED,
        evaluator_results=[{"dimension": "task_success", "score": 1.0, "passed": True}],
        confidence=0.5,
    )

    async with db.session_factory() as session:
        repo = ExperienceRepository(session)
        saved1 = await repo.save_experience(exp1)
        assert saved1.experience_id == exp1.experience_id
        await repo.save_batch([exp2])
        await session.commit()

    async with db.session_factory() as session:
        repo = ExperienceRepository(session)

        # Query by ID
        fetched1 = await repo.get_by_id(exp1.experience_id)
        assert fetched1 is not None
        assert fetched1.execution_id == "run_sql_01"
        assert fetched1.context["goal"] == "Build landing page"
        assert fetched1.artifacts[0]["path"] == "index.html"
        assert fetched1.metrics["cost_usd"] == 0.008

        # List by project
        proj_exps = await repo.list_by_project("proj_sql")
        assert len(proj_exps) == 2

        # Update state and diagnosis
        updated = await repo.update_state(
            experience_id=exp1.experience_id,
            new_state=ExperienceState.DIAGNOSED,
            hypothesis="Dark theme template generation completed with zero defects",
            confidence=0.88,
            details={"attribution": "prompt_clarity"},
        )
        assert updated is not None
        assert updated.state == ExperienceState.DIAGNOSED
        assert updated.confidence == 0.88
        assert updated.hypothesis == "Dark theme template generation completed with zero defects"
        await session.commit()

    async with db.session_factory() as session:
        repo = ExperienceRepository(session)

        # List by state
        diagnosed_list = await repo.list_by_state(ExperienceState.DIAGNOSED, min_confidence=0.8)
        assert len(diagnosed_list) == 1
        assert diagnosed_list[0].experience_id == exp1.experience_id

        # Delete
        deleted = await repo.delete_experience(exp2.experience_id)
        assert deleted is True
        await session.commit()

        assert await repo.get_by_id(exp2.experience_id) is None


# ====================================================================
# 9. API V2 Experiences Endpoints
# ====================================================================

@pytest.mark.asyncio
async def test_api_v2_experiences_endpoints():
    """FastAPI V2 experiences endpoints for CRUD, diagnosis, and learning-ready queries."""
    app = FastAPI()
    app.include_router(experiences_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create experience
        create_payload = {
            "execution_id": "run_api_01",
            "project_id": "proj_api",
            "context": {"task": "test api"},
            "result": {"status": "COMPLETED"},
            "evaluator_results": [
                {"dimension": "task_success", "score": 0.95, "passed": True, "confidence": 0.9}
            ],
            "metrics": {"total_tokens": 1000},
        }
        res = await client.post("/api/v2/experiences", json=create_payload)
        assert res.status_code == 201
        data = res.json()
        exp_id = data["experience_id"]
        assert data["state"] == "evaluated"
        assert data["execution_id"] == "run_api_01"

        # Get by ID
        get_res = await client.get(f"/api/v2/experiences/{exp_id}")
        assert get_res.status_code == 200
        assert get_res.json()["experience_id"] == exp_id

        # Diagnose
        diagnose_payload = {
            "hypothesis": "High quality API responses verified",
            "confidence": 0.85,
        }
        diag_res = await client.post(f"/api/v2/experiences/{exp_id}/diagnose", json=diagnose_payload)
        assert diag_res.status_code == 200
        assert diag_res.json()["state"] == "diagnosed"
        assert diag_res.json()["hypothesis"] == "High quality API responses verified"

        # Learning ready list
        ready_res = await client.get("/api/v2/experiences/learning-ready?min_confidence=0.8")
        assert ready_res.status_code == 200
        ready_items = ready_res.json()
        assert len(ready_items) >= 1
        assert any(it["experience_id"] == exp_id for it in ready_items)

        # Archive
        arch_res = await client.post(f"/api/v2/experiences/{exp_id}/archive")
        assert arch_res.status_code == 200
        assert arch_res.json()["state"] == "archived"


# ====================================================================
# 10. Database Schema Table Integrity
# ====================================================================

def test_experience_table_metadata_integrity():
    """experience_records table and compound indexes exist in BaseORM metadata."""
    assert "experience_records" in BaseORM.metadata.tables
    table = BaseORM.metadata.tables["experience_records"]
    column_names = {c.name for c in table.columns}

    required_columns = {
        "id", "execution_id", "trajectory_id", "parent_task_id",
        "session_id", "project_id", "state", "context_json",
        "decision_json", "action_json", "result_json", "artifacts_json",
        "metrics_json", "evaluator_results_json", "hypothesis",
        "confidence", "provenance_json", "created_at", "updated_at",
    }
    assert required_columns.issubset(column_names)

    index_names = {idx.name for idx in table.indexes}
    assert "ix_experience_state_conf" in index_names
    assert "ix_experience_proj_state" in index_names
    assert "ix_experience_exec_state" in index_names
