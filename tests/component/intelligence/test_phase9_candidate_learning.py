"""Phase 9 Component Tests — Diagnosis & Candidate Learning (ban_ke_hoach_v1 §14, §23, §24, §27).

Tests:
1. LearningCandidate domain model immutability, states, and transition methods.
2. Hard rule (§14): 1 failure/observation -> reflection -> PROPOSED candidate (sample_size=1).
3. Candidate state transitions (PROPOSED -> ELIGIBLE -> EXPERIMENTING, REJECTED, EXPIRED).
4. Evidence and counter-evidence tracking with confidence penalties.
5. CandidateGenerator YouTube hook pattern attribution mining (§22).
6. CandidateGenerator tool failure anomaly mining.
7. EligibilityGate statistical sample size, confidence, and counter-evidence gating.
8. LearnedRule domain model immutability, deprecation, and regression rollback.
9. CandidateService coordination and lifecycle orchestration.
10. CandidateRepository async SQL persistence, batch operations, and queries.
11. API V2 candidates endpoints (/api/v2/candidates, mine, evaluate, mark-eligible, reject, expire).
12. Database schema & table metadata integrity for learning_candidates and learned_rules.
"""

from __future__ import annotations

import uuid
from typing import List, Optional
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
import windagent_storage.orm.candidate_models  # noqa: F401

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearnedRule,
    LearnedRuleState,
    LearningCandidate,
)
from windagent_core.domain.experience import Experience, ExperienceState
from windagent_intelligence.candidate.candidate_generator import CandidateGenerator
from windagent_intelligence.candidate.eligibility_gate import EligibilityGate
from windagent_intelligence.candidate.service import CandidateService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.candidate_repository import CandidateRepository
from windagent_api.routers.v2_candidates import router as candidates_router


def _new_id(prefix: str = "cand") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _sample_diagnosed_experience(
    experience_id: Optional[str] = None,
    topic: str = "AI Agent Coding",
    hook_pattern: str = "demo-first",
    retention_delta: float = 12.0,
    confidence: float = 0.85,
    tool_error: Optional[str] = None,
) -> Experience:
    exp_id = experience_id or f"exp_{uuid.uuid4().hex[:10]}"
    metrics = {
        "cost_usd": 0.015,
        "total_tokens": 1200,
        "retention_30s": 0.60 + (retention_delta / 100.0),
        "diagnosis_details": {"retention_delta_pp": retention_delta},
    }
    if tool_error:
        metrics["tool_failures"] = 1

    action = {"tool_name": "python_repl"} if tool_error else {"tool_name": "code_gen"}
    if tool_error:
        action["failed_tool"] = tool_error

    return Experience(
        experience_id=exp_id,
        execution_id=f"run_{uuid.uuid4().hex[:8]}",
        trajectory_id=f"traj_{uuid.uuid4().hex[:8]}",
        project_id="proj_yt",
        state=ExperienceState.DIAGNOSED,
        context={"topic_cluster": topic, "hook_pattern": hook_pattern, "domain": "youtube"},
        decision={"pattern": hook_pattern},
        action=action,
        result={"status": "FAILED" if tool_error else "COMPLETED", "tool_error": tool_error},
        metrics=metrics,
        evaluator_results=[
            {"dimension": "task_success", "score": 0.0 if tool_error else 0.95, "passed": tool_error is None},
            {"dimension": "safety", "score": 1.0, "passed": True},
        ],
        hypothesis=f"Pattern '{hook_pattern}' on topic '{topic}' observed delta {retention_delta:+.1f}pp",
        confidence=confidence,
    )


@pytest.fixture
async def db():
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:")
    async with mgr.engine.begin() as con:
        await con.run_sync(BaseORM.metadata.create_all)
    yield mgr
    await mgr.engine.dispose()


# ====================================================================
# 1. Domain Model Immutability & Enum Coverage
# ====================================================================

def test_candidate_states_and_immutability():
    """LearningCandidate domain model enforces frozen immutability and complete enums."""
    assert {s.value for s in CandidateStatus} == {
        "proposed", "eligible", "experimenting", "promoted", "rejected", "expired"
    }
    assert {k.value for k in CandidateKind} == {
        "prompt_rule", "memory", "skill", "subagent_spec", "routing_policy"
    }
    assert {r.value for r in CandidateRiskLevel} == {"low", "medium", "high", "critical"}
    assert {sc.value for sc in CandidateScope} == {"local", "project", "global"}
    assert {rs.value for rs in LearnedRuleState} == {
        "candidate", "experimenting", "promoted", "deprecated", "rolled_back"
    }

    cand = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="topic == 'AI Coding'",
        proposed_change={"rule": "Start with live demo"},
        reasoning_summary="Higher retention observed",
        sample_size=1,
        confidence=0.75,
        status=CandidateStatus.PROPOSED,
    )
    assert cand.status == CandidateStatus.PROPOSED
    assert cand.sample_size == 1

    # Immutability validation
    with pytest.raises(ValidationError):
        cand.confidence = 0.9  # type: ignore


# ====================================================================
# 2. Hard Rule: 1 Failure / Observation -> Reflection -> Candidate
# ====================================================================

def test_hard_rule_single_failure_reflection():
    """1 failure creates a PROPOSED candidate with sample_size=1; cannot self-promote."""
    failure_exp = _sample_diagnosed_experience(
        retention_delta=-8.0,
        confidence=0.70,
        tool_error="ToolExecutionTimeout",
    )

    candidate = CandidateGenerator.generate_from_single_experience(failure_exp)

    # Invariant: single observation generates PROPOSED candidate with sample_size=1
    assert candidate.status == CandidateStatus.PROPOSED
    assert candidate.sample_size == 1
    assert candidate.supporting_experiences == [failure_exp.experience_id]
    assert candidate.assert_candidate_invariants() is True

    # Invariant: single failure CANNOT pass eligibility gate (requires sample size >= 3 for project)
    eval_res = EligibilityGate.evaluate(candidate)
    assert eval_res["eligible"] is False
    assert any("Sample size (1) is below threshold" in r for r in eval_res["reasons"])

    # Attempting to apply eligibility fails closed
    with pytest.raises(ValueError, match="below threshold"):
        EligibilityGate.apply(candidate)


# ====================================================================
# 3. Candidate State Transitions
# ====================================================================

def test_candidate_state_transitions():
    """Candidate transitions cleanly through lifecycle states with valid invariants."""
    cand = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="domain == 'youtube'",
        proposed_change={"action": "add hook"},
        reasoning_summary="High retention across samples",
        supporting_experiences=["e1", "e2", "e3"],
        sample_size=3,
        confidence=0.85,
        status=CandidateStatus.PROPOSED,
    )

    # 1. Mark eligible
    eligible = cand.mark_eligible(min_sample_size=3, min_confidence=0.65)
    assert eligible.status == CandidateStatus.ELIGIBLE
    assert eligible.candidate_id == cand.candidate_id

    # 2. Start experiment
    experimenting = eligible.start_experiment()
    assert experimenting.status == CandidateStatus.EXPERIMENTING

    # 3. Reject candidate
    rejected = cand.reject(reason="Conflicting domain requirements")
    assert rejected.status == CandidateStatus.REJECTED
    assert rejected.metadata["rejection_reason"] == "Conflicting domain requirements"

    # 4. Expire candidate
    expired = cand.expire()
    assert expired.status == CandidateStatus.EXPIRED


# ====================================================================
# 4. Evidence & Counter-Evidence Tracking
# ====================================================================

def test_candidate_evidence_and_counter_evidence():
    """Candidate supports dynamic evidence accumulation and counter-evidence confidence penalties."""
    cand = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="hook == 'demo'",
        proposed_change={"remedy": "show demo"},
        reasoning_summary="Demo shows good hook",
        supporting_experiences=["exp_1"],
        sample_size=1,
        confidence=0.70,
        status=CandidateStatus.PROPOSED,
    )

    # Add positive evidence
    cand_ev2 = cand.with_evidence("exp_2", new_confidence=0.80)
    assert cand_ev2.sample_size == 2
    assert "exp_2" in cand_ev2.supporting_experiences
    assert cand_ev2.confidence == 0.80

    # Add counter-evidence
    cand_counter = cand_ev2.with_counter_evidence("exp_bad", penalty=0.15)
    assert cand_counter.sample_size == 3
    assert "exp_bad" in cand_counter.counter_evidence
    assert cand_counter.confidence == pytest.approx(0.65, 0.01)


# ====================================================================
# 5. YouTube Hook Pattern Attribution Mining (§22)
# ====================================================================

def test_candidate_miner_youtube_hook_attribution():
    """CandidateGenerator mines YouTube hook patterns and calculates cluster confidence and counter-evidence."""
    exps: List[Experience] = [
        _sample_diagnosed_experience(topic="AI Coding", hook_pattern="demo-first", retention_delta=12.0, confidence=0.85),
        _sample_diagnosed_experience(topic="AI Coding", hook_pattern="demo-first", retention_delta=8.0, confidence=0.80),
        _sample_diagnosed_experience(topic="AI Coding", hook_pattern="demo-first", retention_delta=-4.0, confidence=0.60),  # counter
        _sample_diagnosed_experience(topic="Cooking", hook_pattern="story-first", retention_delta=15.0, confidence=0.90),
        _sample_diagnosed_experience(topic="Cooking", hook_pattern="story-first", retention_delta=10.0, confidence=0.85),
    ]

    mined_candidates = CandidateGenerator.mine_candidates_from_experiences(exps, min_cluster_size=2)
    assert len(mined_candidates) == 2

    ai_cand = next(c for c in mined_candidates if "AI Coding" in c.condition)
    assert ai_cand.domain == "youtube"
    assert len(ai_cand.supporting_experiences) == 2
    assert len(ai_cand.counter_evidence) == 1
    assert ai_cand.sample_size == 3
    assert ai_cand.status == CandidateStatus.PROPOSED
    assert ai_cand.risk_level == CandidateRiskLevel.LOW

    # AI Coding candidate satisfies project eligibility
    eligible = EligibilityGate.apply(ai_cand, min_sample_size=2, min_confidence=0.6)
    assert eligible.status == CandidateStatus.ELIGIBLE


# ====================================================================
# 6. Tool Failure Anomaly Mining
# ====================================================================

def test_candidate_miner_tool_failure_anomalies():
    """CandidateGenerator identifies recurring tool failures and creates corrective candidates."""
    exps: List[Experience] = [
        _sample_diagnosed_experience(confidence=0.75, tool_error="bash_tool"),
        _sample_diagnosed_experience(confidence=0.80, tool_error="bash_tool"),
    ]

    mined = CandidateGenerator.mine_candidates_from_experiences(exps, min_cluster_size=2)
    assert len(mined) == 1

    tool_cand = mined[0]
    assert "bash_tool" in tool_cand.condition
    assert tool_cand.sample_size == 2
    assert tool_cand.kind == CandidateKind.PROMPT_RULE
    assert tool_cand.domain == "tool_execution"


# ====================================================================
# 7. Eligibility Gate Risk & Scope Thresholds
# ====================================================================

def test_eligibility_gate_scope_and_risk_thresholds():
    """EligibilityGate validates scope thresholds (local=2, project=3, global=5) and safety invariants."""
    # Project candidate with sample size 2 fails default project threshold (3)
    cand_proj = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="cond",
        proposed_change={"k": "v"},
        reasoning_summary="summary",
        supporting_experiences=["e1", "e2"],
        sample_size=2,
        confidence=0.85,
        scope=CandidateScope.PROJECT,
    )
    eval_proj = EligibilityGate.evaluate(cand_proj)
    assert eval_proj["eligible"] is False

    # Global candidate requires sample size >= 5 and confidence >= 0.80
    cand_global = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="cond",
        proposed_change={"k": "v"},
        reasoning_summary="summary",
        supporting_experiences=["e1", "e2", "e3", "e4", "e5"],
        sample_size=5,
        confidence=0.88,
        scope=CandidateScope.GLOBAL,
        risk_level=CandidateRiskLevel.HIGH,
    )
    eval_global = EligibilityGate.evaluate(cand_global)
    assert eval_global["eligible"] is True

    # Zero-tolerance safety violation check
    cand_unsafe = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="cond",
        proposed_change={"k": "v"},
        reasoning_summary="Bypass security and disable policy checks for performance",
        supporting_experiences=["e1", "e2", "e3"],
        sample_size=3,
        confidence=0.90,
    )
    eval_unsafe = EligibilityGate.evaluate(cand_unsafe)
    assert eval_unsafe["eligible"] is False
    assert any("Zero-tolerance safety" in r for r in eval_unsafe["reasons"])


# ====================================================================
# 8. LearnedRule Domain Model Lifecycle & Rollback
# ====================================================================

def test_learned_rule_lifecycle_and_rollback():
    """LearnedRule domain model supports deprecation and regression rollback."""
    rule = LearnedRule(
        rule_id=_new_id("rule"),
        condition="topic == 'AI Coding'",
        recommendation="Use demo-first hook pattern",
        domain="youtube",
        scope=CandidateScope.PROJECT,
        evidence_refs=["cand_1", "exp_1", "exp_2"],
        confidence=0.88,
        sample_size=5,
        harness_version="harness_v2.0",
        version=1,
        state=LearnedRuleState.PROMOTED,
    )
    assert rule.state == LearnedRuleState.PROMOTED

    # Rollback upon regression
    rolled_back = rule.rollback(reason="Detected 30s retention dip in follow-up experiments")
    assert rolled_back.state == LearnedRuleState.ROLLED_BACK
    assert rolled_back.metrics["rollback_reason"] == "Detected 30s retention dip in follow-up experiments"
    assert "rolled_back_at" in rolled_back.metrics

    # Deprecation
    deprecated = rule.deprecate(reason="Superceded by rule_2")
    assert deprecated.state == LearnedRuleState.DEPRECATED
    assert deprecated.metrics["deprecation_reason"] == "Superceded by rule_2"


# ====================================================================
# 9. CandidateService Coordination
# ====================================================================

@pytest.mark.asyncio
async def test_candidate_service_coordination():
    """CandidateService coordinates candidate generation, mining, and state transitions."""
    service = CandidateService()
    exp1 = _sample_diagnosed_experience(retention_delta=10.0, confidence=0.85)
    exp2 = _sample_diagnosed_experience(retention_delta=12.0, confidence=0.90)

    # 1. Generate from single experience
    cand_single = await service.generate_from_experience(exp1)
    assert cand_single.status == CandidateStatus.PROPOSED
    assert cand_single.sample_size == 1

    # 2. Mine from multiple experiences
    mined_list = await service.mine_from_experiences([exp1, exp2], min_cluster_size=2)
    assert len(mined_list) == 1
    cand_mined = mined_list[0]
    assert cand_mined.sample_size == 2

    # 3. Transition to eligible
    eligible = await service.mark_eligible(cand_mined, min_sample_size=2, min_confidence=0.65)
    assert eligible.status == CandidateStatus.ELIGIBLE

    # 4. Reject and expire
    rejected = await service.reject_candidate(cand_single, reason="Single sample not generalizable")
    assert rejected.status == CandidateStatus.REJECTED

    expired = await service.expire_candidate(eligible)
    assert expired.status == CandidateStatus.EXPIRED


# ====================================================================
# 10. CandidateRepository Async SQL Persistence
# ====================================================================

@pytest.mark.asyncio
async def test_candidate_repository_sql_crud(db):
    """CandidateRepository async SQL persistence, batch saving, querying, and rule operations."""
    cand1 = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.PROMPT_RULE,
        condition="topic == 'AI Coding'",
        proposed_change={"rule": "Start with live demo"},
        reasoning_summary="Observed high retention",
        supporting_experiences=["exp_1", "exp_2", "exp_3"],
        counter_evidence=["exp_bad"],
        sample_size=4,
        confidence=0.82,
        scope=CandidateScope.PROJECT,
        risk_level=CandidateRiskLevel.LOW,
        status=CandidateStatus.PROPOSED,
        project_id="proj_sql",
        domain="youtube",
    )
    cand2 = LearningCandidate(
        candidate_id=_new_id(),
        kind=CandidateKind.SKILL,
        condition="tool == 'bash'",
        proposed_change={"check": "sanitize"},
        reasoning_summary="Prevent syntax error",
        sample_size=2,
        confidence=0.75,
        scope=CandidateScope.LOCAL,
        status=CandidateStatus.ELIGIBLE,
        project_id="proj_sql",
        domain="tool_execution",
    )

    rule1 = LearnedRule(
        rule_id=_new_id("rule"),
        condition="topic == 'AI Coding'",
        recommendation="Use live demo hook",
        domain="youtube",
        scope=CandidateScope.PROJECT,
        confidence=0.88,
        sample_size=5,
        state=LearnedRuleState.PROMOTED,
    )

    async with db.session_factory() as session:
        repo = CandidateRepository(session)
        await repo.save(cand1)
        await repo.save_batch([cand2])
        await repo.save_rule(rule1)
        await session.commit()

    async with db.session_factory() as session:
        repo = CandidateRepository(session)

        # Get candidate by ID
        fetched1 = await repo.get_by_id(cand1.candidate_id)
        assert fetched1 is not None
        assert fetched1.candidate_id == cand1.candidate_id
        assert fetched1.kind == CandidateKind.PROMPT_RULE
        assert fetched1.condition == "topic == 'AI Coding'"
        assert fetched1.confidence == 0.82
        assert len(fetched1.supporting_experiences) == 3
        assert len(fetched1.counter_evidence) == 1

        # List candidates with filter
        proj_candidates = await repo.list_candidates(project_id="proj_sql")
        assert len(proj_candidates) == 2

        eligible_candidates = await repo.list_candidates(status=CandidateStatus.ELIGIBLE)
        assert len(eligible_candidates) == 1
        assert eligible_candidates[0].candidate_id == cand2.candidate_id

        # Update candidate status
        updated = await repo.update_status(
            candidate_id=cand1.candidate_id,
            new_status=CandidateStatus.ELIGIBLE,
            metadata_update={"promoted_at": "2026-08-29"},
        )
        assert updated is not None
        assert updated.status == CandidateStatus.ELIGIBLE
        assert updated.metadata["promoted_at"] == "2026-08-29"
        await session.commit()

        # Get and list learned rules
        fetched_rule = await repo.get_rule_by_id(rule1.rule_id)
        assert fetched_rule is not None
        assert fetched_rule.rule_id == rule1.rule_id
        assert fetched_rule.state == LearnedRuleState.PROMOTED

        rules_list = await repo.list_rules(domain="youtube")
        assert len(rules_list) == 1

        # Delete operations
        assert await repo.delete_candidate(cand2.candidate_id) is True
        assert await repo.delete_rule(rule1.rule_id) is True
        await session.commit()

        assert await repo.get_by_id(cand2.candidate_id) is None
        assert await repo.get_rule_by_id(rule1.rule_id) is None


# ====================================================================
# 11. API V2 Candidates Endpoints
# ====================================================================

@pytest.mark.asyncio
async def test_api_v2_candidates_endpoints():
    """FastAPI V2 candidates endpoints for proposing, mining, evaluating, and managing candidates."""
    app = FastAPI()
    app.include_router(candidates_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Propose candidate
        propose_payload = {
            "kind": "prompt_rule",
            "condition": "topic == 'Coding'",
            "proposed_change": {"action": "live demo"},
            "reasoning_summary": "High retention verified",
            "supporting_experiences": ["e1", "e2", "e3"],
            "sample_size": 3,
            "confidence": 0.85,
            "scope": "project",
            "project_id": "proj_api",
            "domain": "youtube",
        }
        res = await client.post("/api/v2/candidates", json=propose_payload)
        assert res.status_code == 201
        data = res.json()
        cand_id = data["candidate_id"]
        assert data["status"] == "proposed"
        assert data["confidence"] == 0.85

        # 2. Get candidate by ID
        get_res = await client.get(f"/api/v2/candidates/{cand_id}")
        assert get_res.status_code == 200
        assert get_res.json()["candidate_id"] == cand_id

        # 3. Evaluate candidate eligibility
        eval_res = await client.post(
            f"/api/v2/candidates/{cand_id}/evaluate",
            json={"min_sample_size": 3, "min_confidence": 0.65},
        )
        assert eval_res.status_code == 200
        assert eval_res.json()["eligible"] is True

        # 4. Mark candidate eligible
        mark_res = await client.post(
            f"/api/v2/candidates/{cand_id}/mark-eligible",
            json={"min_sample_size": 3, "min_confidence": 0.65},
        )
        assert mark_res.status_code == 200
        assert mark_res.json()["status"] == "eligible"

        # 5. List candidates with filter
        list_res = await client.get("/api/v2/candidates?status=eligible")
        assert list_res.status_code == 200
        assert len(list_res.json()) >= 1

        # 6. Mine candidates endpoint
        exp1 = _sample_diagnosed_experience(retention_delta=10.0, confidence=0.85)
        exp2 = _sample_diagnosed_experience(retention_delta=12.0, confidence=0.90)
        mine_payload = {
            "experiences": [exp1.model_dump(mode="json"), exp2.model_dump(mode="json")],
            "min_cluster_size": 2,
            "scope": "project",
        }
        mine_res = await client.post("/api/v2/candidates/mine", json=mine_payload)
        assert mine_res.status_code == 200
        assert len(mine_res.json()) >= 1

        # 7. Reject candidate
        reject_res = await client.post(
            f"/api/v2/candidates/{cand_id}/reject",
            json={"reason": "Overridden by project requirements"},
        )
        assert reject_res.status_code == 200
        assert reject_res.json()["status"] == "rejected"

        # 8. Expire candidate
        expire_res = await client.post(f"/api/v2/candidates/{cand_id}/expire")
        assert expire_res.status_code == 200
        assert expire_res.json()["status"] == "expired"


# ====================================================================
# 12. Database Schema Table Integrity
# ====================================================================

def test_candidate_tables_metadata_integrity():
    """learning_candidates and learned_rules tables and compound indexes exist in BaseORM metadata."""
    assert "learning_candidates" in BaseORM.metadata.tables
    assert "learned_rules" in BaseORM.metadata.tables

    cand_table = BaseORM.metadata.tables["learning_candidates"]
    cand_columns = {c.name for c in cand_table.columns}
    assert {
        "id", "kind", "condition", "proposed_change_json", "reasoning_summary",
        "supporting_experiences_json", "counter_evidence_json", "sample_size",
        "confidence", "scope", "risk_level", "status", "project_id", "domain",
        "metadata_json", "created_at", "updated_at",
    }.issubset(cand_columns)

    cand_indexes = {idx.name for idx in cand_table.indexes}
    assert "ix_candidate_status_conf" in cand_indexes
    assert "ix_candidate_proj_status" in cand_indexes
    assert "ix_candidate_domain_status" in cand_indexes

    rule_table = BaseORM.metadata.tables["learned_rules"]
    rule_columns = {c.name for c in rule_table.columns}
    assert {
        "id", "condition", "recommendation", "domain", "scope",
        "evidence_refs_json", "metrics_json", "confidence", "sample_size",
        "created_at", "last_validated_at", "harness_version", "version", "state",
    }.issubset(rule_columns)

    rule_indexes = {idx.name for idx in rule_table.indexes}
    assert "ix_rule_domain_state" in rule_indexes
