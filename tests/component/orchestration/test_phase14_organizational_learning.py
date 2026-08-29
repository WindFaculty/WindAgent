"""Phase 14 Component Tests — Organizational Learning, Multi-Agent Knowledge Sharing, Conflict Resolution, and Attribution (ban_ke_hoach_v1 §20, §21, §22, §23, §24, §25, §32, §35).

Tests:
1. Domain model immutability, fingerprint calculation, promotability checks, and serialization.
2. RuleConflictResolver: Multi-factor scoring across domain match, scope specificity, evidence, recency, and harness compatibility.
3. RuleConflictResolver: Deterministic conflict resolution producing explainable rationale and score breakdown.
4. Visibility Boundary: Enforces PRIVATE_AGENT, TASK, SESSION, ROLE, PROJECT, and GLOBAL access isolation.
5. Containment Invariant: Proves unpromoted candidate rules cannot auto-globalize across agents.
6. OrganizationalLearningService: Propose, promote, deprecate, and rollback lifecycle transitions.
7. OrganizationalLearningService: Query applicable rules with condition matching, visibility filtering, and conflict resolution.
8. YouTube Metric Attribution: Stage-separated performance attribution mapping signals to specialized agent roles.
9. Async SQL Repository: Full persistence, queries, conflict resolutions, and attributions.
10. FastAPI V2 REST Endpoints: Complete test coverage of /api/v2/organizational-learning endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
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
import windagent_storage.orm.skill_evolution_models  # noqa: F401
import windagent_storage.orm.subagent_evolution_models  # noqa: F401
import windagent_storage.orm.organizational_learning_models  # noqa: F401

from windagent_core.domain.organizational_learning import (
    AgentExecutionContext,
    ConflictResolutionRecord,
    KnowledgeVisibilityScope,
    LearnedRule,
    LearnedRuleState,
    MultiAgentAttributionRecord,
    utc_now,
)
from windagent_orchestration.learning.conflict_resolver import (
    RuleConflictResolver,
    SCOPE_SPECIFICITY_WEIGHTS,
)
from windagent_orchestration.learning.organizational_learning_service import (
    OrganizationalLearningService,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.repositories.organizational_learning_repository import (
    OrganizationalLearningRepository,
)
from windagent_api.routers.v2_organizational_learning import router as org_learning_router


# =============================================================================
# Helper Builders
# =============================================================================

def _sample_learned_rule(
    rule_id: str = "rule_test_01",
    condition: Optional[Dict[str, Any]] = None,
    recommendation: str = "Start videos with a direct 10-second prototype demo before theory.",
    domain: str = "youtube_studio",
    scope: KnowledgeVisibilityScope = KnowledgeVisibilityScope.ROLE,
    target_role: Optional[str] = "ScriptAgent",
    project_id: Optional[str] = None,
    confidence: float = 0.85,
    sample_size: int = 5,
    version: int = 1,
    state: LearnedRuleState = LearnedRuleState.PROMOTED,
    harness_version: Optional[str] = "harness_v2",
    metadata: Optional[Dict[str, Any]] = None,
) -> LearnedRule:
    return LearnedRule(
        rule_id=rule_id,
        condition=condition if condition is not None else {"topic_cluster": "AI Agent Coding", "hook_pattern": "demo_first"},
        recommendation=recommendation,
        domain=domain,
        scope=scope,
        target_role=target_role,
        project_id=project_id,
        evidence_refs=["exp_ep042", "exp_ep047"],
        metrics={"retention_30s_delta": 0.12, "ctr_delta": 0.04},
        confidence=confidence,
        sample_size=sample_size,
        version=version,
        state=state,
        harness_version=harness_version,
        created_at=utc_now(),
        metadata=metadata or {},
    )


# =============================================================================
# Test Cases
# =============================================================================

def test_learned_rule_domain_immutability_and_helpers():
    """LearnedRule must be immutable (frozen) and compute deterministic fingerprints."""
    cand_rule = _sample_learned_rule(state=LearnedRuleState.CANDIDATE)
    assert cand_rule.is_active is False
    assert cand_rule.is_promotable is True

    prom_rule = _sample_learned_rule(state=LearnedRuleState.PROMOTED)
    assert prom_rule.is_active is True
    assert prom_rule.is_promotable is False

    fp1 = prom_rule.calculate_fingerprint()
    assert isinstance(fp1, str) and len(fp1) == 64

    # Immutability check
    with pytest.raises(ValidationError):
        prom_rule.confidence = 0.99  # type: ignore

    d = prom_rule.to_dict()
    assert d["rule_id"] == "rule_test_01"
    assert d["scope"] == "role"
    assert d["state"] == "promoted"


def test_conflict_resolver_scoring_breakdown():
    """RuleConflictResolver computes transparent multi-factor scores."""
    resolver = RuleConflictResolver()
    rule = _sample_learned_rule(
        confidence=0.9,
        sample_size=10,
        scope=KnowledgeVisibilityScope.ROLE,
        harness_version="v2.0.0",
    )

    query = {"topic_cluster": "AI Agent Coding", "hook_pattern": "demo_first"}
    score, breakdown = resolver.calculate_score(
        rule=rule,
        context_query=query,
        active_harness_version="v2.0.0",
    )

    assert 0.0 <= score <= 1.0
    assert breakdown["domain_match"] == 1.0
    assert breakdown["scope_specificity"] == SCOPE_SPECIFICITY_WEIGHTS[KnowledgeVisibilityScope.ROLE]
    assert breakdown["evidence_strength"] == 0.9
    assert breakdown["harness_compatibility"] == 1.0


def test_conflict_resolver_picks_highest_scoring_rule():
    """RuleConflictResolver selects higher-evidence/specific rule and creates audit record."""
    resolver = RuleConflictResolver()

    # Rule A: Broad global rule with moderate confidence
    rule_a = _sample_learned_rule(
        rule_id="rule_global_a",
        scope=KnowledgeVisibilityScope.GLOBAL,
        confidence=0.6,
        sample_size=2,
    )

    # Rule B: Specific role rule with high sample size & confidence
    rule_b = _sample_learned_rule(
        rule_id="rule_role_b",
        scope=KnowledgeVisibilityScope.ROLE,
        confidence=0.95,
        sample_size=12,
    )

    query = {"topic_cluster": "AI Agent Coding", "hook_pattern": "demo_first"}
    winner, record = resolver.resolve_conflict(
        competing_rules=[rule_a, rule_b],
        context_query=query,
        domain="youtube_studio",
    )

    assert winner.rule_id == "rule_role_b"
    assert record.winning_rule_id == "rule_role_b"
    assert "rule_global_a" in record.competing_rule_ids
    assert "rule_role_b" in record.competing_rule_ids
    assert record.score_breakdown["rule_role_b"]["total_score"] > record.score_breakdown["rule_global_a"]["total_score"]


def test_visibility_boundary_scoping_enforcement():
    """Service enforces private agent, task, session, role, project, and global boundaries."""
    repo = None  # Mocking repo not needed for pure visibility logic
    service = OrganizationalLearningService(repository=repo)  # type: ignore

    # 1. Global Rule -> Visible to any agent context
    global_rule = _sample_learned_rule(scope=KnowledgeVisibilityScope.GLOBAL)
    ctx_agent_1 = AgentExecutionContext(agent_id="ag_1", role="ScriptAgent", project_id="proj_1")
    ctx_agent_2 = AgentExecutionContext(agent_id="ag_2", role="ThumbnailAgent", project_id="proj_2")
    assert service.is_rule_visible_to_agent(global_rule, ctx_agent_1) is True
    assert service.is_rule_visible_to_agent(global_rule, ctx_agent_2) is True

    # 2. Project Rule -> Visible only within matching project_id
    proj_rule = _sample_learned_rule(scope=KnowledgeVisibilityScope.PROJECT, project_id="proj_alpha")
    ctx_in_proj = AgentExecutionContext(agent_id="ag_1", role="ScriptAgent", project_id="proj_alpha")
    ctx_out_proj = AgentExecutionContext(agent_id="ag_2", role="ScriptAgent", project_id="proj_beta")
    assert service.is_rule_visible_to_agent(proj_rule, ctx_in_proj) is True
    assert service.is_rule_visible_to_agent(proj_rule, ctx_out_proj) is False

    # 3. Role Rule -> Visible only to agents with matching role
    role_rule = _sample_learned_rule(scope=KnowledgeVisibilityScope.ROLE, target_role="ScriptAgent")
    ctx_script = AgentExecutionContext(agent_id="ag_1", role="ScriptAgent")
    ctx_thumb = AgentExecutionContext(agent_id="ag_2", role="ThumbnailAgent")
    assert service.is_rule_visible_to_agent(role_rule, ctx_script) is True
    assert service.is_rule_visible_to_agent(role_rule, ctx_thumb) is False

    # 4. Private Agent Rule -> Visible only to creating agent_id
    private_rule = _sample_learned_rule(
        scope=KnowledgeVisibilityScope.PRIVATE_AGENT,
        metadata={"agent_id": "agent_alpha_001"},
    )
    ctx_owner = AgentExecutionContext(agent_id="agent_alpha_001", role="ScriptAgent")
    ctx_other = AgentExecutionContext(agent_id="agent_beta_002", role="ScriptAgent")
    assert service.is_rule_visible_to_agent(private_rule, ctx_owner) is True
    assert service.is_rule_visible_to_agent(private_rule, ctx_other) is False


def test_unpromoted_candidate_cannot_auto_globalize():
    """Invariant (§20): Unpromoted candidate rules cannot be seen by other agents."""
    service = OrganizationalLearningService(repository=None)  # type: ignore

    # Candidate rule proposed with GLOBAL scope
    candidate_rule = _sample_learned_rule(
        scope=KnowledgeVisibilityScope.GLOBAL,
        state=LearnedRuleState.CANDIDATE,
        metadata={"agent_id": "creator_ag_1"},
    )

    ctx_creator = AgentExecutionContext(agent_id="creator_ag_1", role="ScriptAgent")
    ctx_peer = AgentExecutionContext(agent_id="peer_ag_2", role="ScriptAgent")

    # Creator can inspect their own candidate
    assert service.is_rule_visible_to_agent(candidate_rule, ctx_creator) is True
    # Peer CANNOT see unpromoted candidate
    assert service.is_rule_visible_to_agent(candidate_rule, ctx_peer) is False


@pytest.mark.asyncio
async def test_organizational_learning_service_lifecycle_and_conflict_resolution():
    """Async service supports propose, promote, deprecate, rollback, and query resolution."""
    class InMemoryOrgRepo:
        def __init__(self):
            self.rules: Dict[str, LearnedRule] = {}
            self.resolutions: Dict[str, ConflictResolutionRecord] = {}
            self.attributions: Dict[str, MultiAgentAttributionRecord] = {}

        async def get_rule(self, rule_id: str):
            return self.rules.get(rule_id)

        async def save_rule(self, rule: LearnedRule):
            self.rules[rule.rule_id] = rule

        async def list_rules(self, **kwargs):
            return list(self.rules.values())

        async def query_active_rules(self, domain: str, **kwargs):
            return [r for r in self.rules.values() if r.domain == domain and r.is_active]

        async def get_conflict_resolution(self, res_id: str):
            return self.resolutions.get(res_id)

        async def save_conflict_resolution(self, record: ConflictResolutionRecord):
            self.resolutions[record.resolution_id] = record

        async def list_conflict_resolutions(self, **kwargs):
            return list(self.resolutions.values())

        async def get_attribution(self, attr_id: str):
            return self.attributions.get(attr_id)

        async def save_attribution(self, record: MultiAgentAttributionRecord):
            self.attributions[record.attribution_id] = record

        async def list_attributions(self, **kwargs):
            return list(self.attributions.values())

    repo = InMemoryOrgRepo()
    service = OrganizationalLearningService(repository=repo)  # type: ignore

    # 1. Propose candidate rule
    rule_v1 = await service.propose_rule(
        condition={"topic_cluster": "AI", "hook": "question"},
        recommendation="Ask rhetorical question in opening 5s.",
        domain="youtube_studio",
        scope=KnowledgeVisibilityScope.ROLE,
        target_role="ScriptAgent",
        confidence=0.7,
        sample_size=3,
    )
    assert rule_v1.state == LearnedRuleState.CANDIDATE
    assert rule_v1.version == 1

    # 2. Promote rule
    promoted_v1 = await service.promote_rule(rule_v1.rule_id, approved_by="lead_reviewer")
    assert promoted_v1.state == LearnedRuleState.PROMOTED
    assert promoted_v1.activated_at is not None

    # 3. Propose competing rule with higher evidence
    rule_v2 = await service.propose_rule(
        condition={"topic_cluster": "AI", "hook": "question"},
        recommendation="Show concrete code execution instead of rhetorical question.",
        domain="youtube_studio",
        scope=KnowledgeVisibilityScope.ROLE,
        target_role="ScriptAgent",
        confidence=0.92,
        sample_size=8,
        supersedes_id=promoted_v1.rule_id,
    )
    assert rule_v2.version == 2
    promoted_v2 = await service.promote_rule(rule_v2.rule_id, approved_by="lead_reviewer")
    assert promoted_v2.state == LearnedRuleState.PROMOTED

    # Previous version should be deprecated
    old_v1 = await repo.get_rule(promoted_v1.rule_id)
    assert old_v1 is not None and old_v1.state == LearnedRuleState.DEPRECATED

    # 4. Query applicable rules for agent context
    ctx = AgentExecutionContext(
        agent_id="ag_script_01",
        role="ScriptAgent",
        domain="youtube_studio",
        context_tags={"topic_cluster": "AI", "hook": "question"},
    )
    applicable = await service.query_applicable_rules(ctx)
    assert len(applicable) == 1
    assert applicable[0].rule_id == promoted_v2.rule_id
    assert applicable[0].recommendation == "Show concrete code execution instead of rhetorical question."

    # 5. Rollback rule v2 due to regression
    rolled_back, reactivated = await service.rollback_rule(
        rule_id=promoted_v2.rule_id,
        reason="CTR dropped in live testing",
    )
    assert rolled_back.state == LearnedRuleState.ROLLED_BACK
    assert reactivated is not None
    assert reactivated.rule_id == promoted_v1.rule_id
    assert reactivated.state == LearnedRuleState.PROMOTED


@pytest.mark.asyncio
async def test_youtube_stage_separated_metric_attribution():
    """Service maps YouTube signals to specialized roles (§21, §22)."""
    class SimpleRepo:
        def __init__(self):
            self.attributions = {}
        async def save_attribution(self, record):
            self.attributions[record.attribution_id] = record

    repo = SimpleRepo()
    service = OrganizationalLearningService(repository=repo)  # type: ignore

    metrics = {
        "impressions": 120000.0,
        "ctr": 0.085,
        "retention_30s": 0.74,
        "retention_dips": 2.0,
        "avg_view_duration": 480.0,
        "completion_rate": 0.42,
        "comments": 350.0,
        "production_retries": 1.0,
    }
    baselines = {
        "impressions": 100000.0,
        "ctr": 0.060,
        "retention_30s": 0.60,
        "retention_dips": 4.0,
        "avg_view_duration": 400.0,
        "completion_rate": 0.35,
        "comments": 200.0,
        "production_retries": 3.0,
    }

    record = await service.attribute_youtube_metrics(
        episode_id="EP042",
        metric_signals=metrics,
        baseline_signals=baselines,
    )

    assert record.episode_id == "EP042"
    assert "TopicAgent" in record.role_attributions
    assert "ThumbnailAgent" in record.role_attributions
    assert "ScriptAgent" in record.role_attributions
    assert "ProductionAgent" in record.role_attributions

    # Verify ScriptAgent attribution for 30s retention
    script_attr = record.role_attributions["ScriptAgent"]
    assert script_attr["signal"] == "retention_30s"
    assert script_attr["value"] == 0.74
    assert script_attr["baseline"] == 0.60
    assert script_attr["delta"] == 0.14
    assert script_attr["status"] == "outperforming"


@pytest.mark.asyncio
async def test_organizational_learning_async_sql_repository(component_db: DatabaseManager):
    """Async SQL repository persists and queries learned rules, conflict resolutions, and attributions."""
    async with component_db.session_factory() as session:
        repo = OrganizationalLearningRepository(session=session)

        # 1. Save learned rule
        rule = _sample_learned_rule(
            rule_id="sql_rule_01",
            scope=KnowledgeVisibilityScope.ROLE,
            target_role="ScriptAgent",
            state=LearnedRuleState.PROMOTED,
        )
        await repo.save_rule(rule)

        # 2. Fetch learned rule
        fetched = await repo.get_rule("sql_rule_01")
        assert fetched is not None
        assert fetched.rule_id == "sql_rule_01"
        assert fetched.target_role == "ScriptAgent"
        assert fetched.state == LearnedRuleState.PROMOTED

        # 3. Query active rules
        active_list = await repo.query_active_rules(domain="youtube_studio")
        assert len(active_list) >= 1
        assert any(r.rule_id == "sql_rule_01" for r in active_list)

        # 4. Save conflict resolution
        res_rec = ConflictResolutionRecord(
            resolution_id="sql_res_01",
            domain="youtube_studio",
            context_query={"topic": "ai"},
            winning_rule_id="sql_rule_01",
            competing_rule_ids=["sql_rule_01", "sql_rule_02"],
            resolution_rationale="Winner had higher sample size",
            score_breakdown={"sql_rule_01": {"total_score": 0.95}},
            resolved_at=utc_now(),
        )
        await repo.save_conflict_resolution(res_rec)

        fetched_res = await repo.get_conflict_resolution("sql_res_01")
        assert fetched_res is not None
        assert fetched_res.winning_rule_id == "sql_rule_01"

        # 5. Save attribution
        attr_rec = MultiAgentAttributionRecord(
            attribution_id="sql_attr_01",
            episode_id="EP100",
            domain="youtube_studio",
            metric_signals={"ctr": 0.09},
            role_attributions={"ThumbnailAgent": {"delta": 0.03, "status": "outperforming"}},
            created_at=utc_now(),
        )
        await repo.save_attribution(attr_rec)

        fetched_attr = await repo.get_attribution("sql_attr_01")
        assert fetched_attr is not None
        assert fetched_attr.episode_id == "EP100"


@pytest.mark.asyncio
async def test_fastapi_v2_organizational_learning_endpoints():
    """FastAPI test suite covering all /api/v2/organizational-learning REST endpoints."""
    app = FastAPI()
    app.include_router(org_learning_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Propose rule
        propose_payload = {
            "condition": {"topic_cluster": "Coding", "pacing": "fast"},
            "recommendation": "Use 3-second cuts during code setup.",
            "domain": "youtube_studio",
            "scope": "role",
            "target_role": "SceneAgent",
            "confidence": 0.88,
            "sample_size": 4,
        }
        res = await client.post("/api/v2/organizational-learning/rules", json=propose_payload)
        assert res.status_code == 201
        data = res.json()
        rule_id = data["rule_id"]
        assert data["state"] == "candidate"
        assert data["target_role"] == "SceneAgent"

        # 2. Get rule
        res_get = await client.get(f"/api/v2/organizational-learning/rules/{rule_id}")
        assert res_get.status_code == 200
        assert res_get.json()["rule_id"] == rule_id

        # 3. List rules
        res_list = await client.get("/api/v2/organizational-learning/rules?domain=youtube_studio")
        assert res_list.status_code == 200
        assert any(r["rule_id"] == rule_id for r in res_list.json())

        # 4. Promote rule
        promote_payload = {
            "approved_by": "qa_lead",
            "harness_version": "harness_v3",
        }
        res_promote = await client.post(f"/api/v2/organizational-learning/rules/{rule_id}/promote", json=promote_payload)
        assert res_promote.status_code == 200
        assert res_promote.json()["state"] == "promoted"
        assert res_promote.json()["harness_version"] == "harness_v3"

        # 5. Query applicable rules for agent
        query_payload = {
            "agent_context": {
                "agent_id": "agent_scene_99",
                "role": "SceneAgent",
                "domain": "youtube_studio",
                "context_tags": {"topic_cluster": "Coding", "pacing": "fast"},
            }
        }
        res_query = await client.post("/api/v2/organizational-learning/query", json=query_payload)
        assert res_query.status_code == 200
        matches = res_query.json()
        assert len(matches) >= 1
        assert matches[0]["rule_id"] == rule_id

        # 6. Record YouTube metric attribution
        attr_payload = {
            "episode_id": "EP099",
            "metric_signals": {"impressions": 50000.0, "ctr": 0.075, "retention_30s": 0.70},
            "baseline_signals": {"impressions": 40000.0, "ctr": 0.050, "retention_30s": 0.60},
            "domain": "youtube_studio",
        }
        res_attr = await client.post("/api/v2/organizational-learning/attributions", json=attr_payload)
        assert res_attr.status_code == 201
        attr_data = res_attr.json()
        attr_id = attr_data["attribution_id"]
        assert attr_data["episode_id"] == "EP099"

        # 7. Get attribution by ID
        res_attr_get = await client.get(f"/api/v2/organizational-learning/attributions/{attr_id}")
        assert res_attr_get.status_code == 200
        assert res_attr_get.json()["attribution_id"] == attr_id

        # 8. Deprecate rule
        res_dep = await client.post(f"/api/v2/organizational-learning/rules/{rule_id}/deprecate", json={"reason": "Testing deprecation"})
        assert res_dep.status_code == 200
        assert res_dep.json()["state"] == "deprecated"

        # 9. Rollback rule
        res_rb = await client.post(f"/api/v2/organizational-learning/rules/{rule_id}/rollback", json={"reason": "Testing rollback"})
        assert res_rb.status_code == 200
        assert res_rb.json()["rolled_back_rule"]["state"] == "rolled_back"

