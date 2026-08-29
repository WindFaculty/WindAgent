"""API V2 Organizational Learning & Knowledge Sharing Router (Phase 14 — ban_ke_hoach_v1 §20, §21, §22, §23, §24, §25, §32, §35).

Endpoints for learned rule proposals, scoped rule queries, multi-factor conflict resolution,
rule promotions/rollbacks, and multi-agent YouTube performance metric attribution.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now
from windagent_core.domain.organizational_learning import (
    AgentExecutionContext,
    ConflictResolutionRecord,
    KnowledgeVisibilityScope,
    LearnedRule,
    LearnedRuleState,
    MultiAgentAttributionRecord,
)
from windagent_orchestration.learning.conflict_resolver import RuleConflictResolver
from windagent_orchestration.learning.organizational_learning_service import (
    YOUTUBE_SIGNAL_ROLE_MAP,
)

router = APIRouter(prefix="/api/v2/organizational-learning", tags=["Organizational Learning V2"])

# Ephemeral state for isolated API tests and standalone in-memory routing
_ephemeral_rules: Dict[str, LearnedRule] = {}
_ephemeral_conflict_resolutions: Dict[str, ConflictResolutionRecord] = {}
_ephemeral_attributions: Dict[str, MultiAgentAttributionRecord] = {}
_resolver = RuleConflictResolver()


# -----------------------------------------------------------------------------
# DTO Models
# -----------------------------------------------------------------------------

class ProposeRuleRequest(BaseModel):
    condition: Dict[str, Any] = Field(description="Context trigger condition.")
    recommendation: str = Field(description="Actionable behavioral guideline or prompt rule.")
    domain: str = Field(default="youtube_studio", description="Application domain.")
    scope: KnowledgeVisibilityScope = Field(default=KnowledgeVisibilityScope.ROLE, description="Visibility boundary.")
    target_role: Optional[str] = Field(default=None, description="Target role if scope is ROLE.")
    project_id: Optional[str] = Field(default=None, description="Target project ID if scope is PROJECT.")
    evidence_refs: List[str] = Field(default_factory=list, description="Provenances to supporting runs/experiences.")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Observed quantitative metrics.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score.")
    sample_size: int = Field(default=1, ge=0, description="Observational sample count.")
    supersedes_id: Optional[str] = Field(default=None, description="ID of rule superseded by this rule.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromoteRuleRequest(BaseModel):
    approved_by: Optional[str] = Field(default=None, description="Approver ID if review occurred.")
    harness_version: Optional[str] = Field(default=None, description="Target harness version string.")


class DeprecateRuleRequest(BaseModel):
    reason: str = Field(default="Superseded or outdated", description="Deprecation justification.")


class RollbackRuleRequest(BaseModel):
    reason: str = Field(default="Rollback due to performance regression", description="Rollback justification.")
    rollback_target_id: Optional[str] = Field(default=None, description="Target previous rule version ID to reactivate.")


class QueryRulesRequest(BaseModel):
    agent_context: AgentExecutionContext
    active_harness_version: Optional[str] = None


class AttributeMetricsRequest(BaseModel):
    episode_id: str = Field(description="Episode or run identifier.")
    metric_signals: Dict[str, float] = Field(description="Raw performance metrics dictionary.")
    baseline_signals: Optional[Dict[str, float]] = Field(default=None, description="Baseline metrics to compute deltas.")
    domain: str = Field(default="youtube_studio", description="Domain name.")


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def propose_rule(payload: ProposeRuleRequest) -> Dict[str, Any]:
    """Proposes a new candidate learned rule (§20, §23)."""
    if not payload.recommendation.strip():
        raise HTTPException(status_code=400, detail="Recommendation cannot be empty.")

    rule_id = f"rule_{uuid.uuid4().hex[:12]}"
    now = utc_now()
    version = 1

    if payload.supersedes_id and payload.supersedes_id in _ephemeral_rules:
        version = _ephemeral_rules[payload.supersedes_id].version + 1

    rule = LearnedRule(
        rule_id=rule_id,
        condition=payload.condition,
        recommendation=payload.recommendation.strip(),
        domain=payload.domain,
        scope=payload.scope,
        target_role=payload.target_role,
        project_id=payload.project_id,
        evidence_refs=payload.evidence_refs,
        metrics=payload.metrics,
        confidence=payload.confidence,
        sample_size=payload.sample_size,
        version=version,
        state=LearnedRuleState.CANDIDATE,
        supersedes_id=payload.supersedes_id,
        created_at=now,
        metadata=payload.metadata,
    )

    _ephemeral_rules[rule.rule_id] = rule
    return rule.to_dict()


@router.get("/rules")
async def list_rules(
    domain: Optional[str] = Query(None),
    state: Optional[LearnedRuleState] = Query(None),
    scope: Optional[KnowledgeVisibilityScope] = Query(None),
    target_role: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    """Lists learned rules with optional filtering."""
    results = list(_ephemeral_rules.values())

    if domain:
        results = [r for r in results if r.domain == domain]
    if state:
        results = [r for r in results if r.state == state]
    if scope:
        results = [r for r in results if r.scope == scope]
    if target_role:
        results = [r for r in results if r.target_role == target_role]
    if project_id:
        results = [r for r in results if r.project_id == project_id]

    results.sort(key=lambda r: r.created_at, reverse=True)
    return [r.to_dict() for r in results[:limit]]


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str) -> Dict[str, Any]:
    """Retrieves a single learned rule by ID."""
    rule = _ephemeral_rules.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
    return rule.to_dict()


@router.post("/rules/{rule_id}/promote")
async def promote_rule(rule_id: str, payload: PromoteRuleRequest) -> Dict[str, Any]:
    """Promotes a candidate rule to active PROMOTED status (§20, §23)."""
    rule = _ephemeral_rules.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")

    now = utc_now()
    # Deprecate superseded rule if present
    if rule.supersedes_id and rule.supersedes_id in _ephemeral_rules:
        parent = _ephemeral_rules[rule.supersedes_id]
        if parent.state == LearnedRuleState.PROMOTED:
            _ephemeral_rules[parent.rule_id] = LearnedRule(
                **{
                    **parent.to_dict(),
                    "state": LearnedRuleState.DEPRECATED,
                    "superseded_by": rule.rule_id,
                    "deprecated_at": now,
                }
            )

    meta = dict(rule.metadata)
    if payload.approved_by:
        meta["approved_by"] = payload.approved_by
        meta["approved_at"] = now.isoformat()

    promoted = LearnedRule(
        **{
            **rule.to_dict(),
            "state": LearnedRuleState.PROMOTED,
            "harness_version": payload.harness_version or rule.harness_version,
            "activated_at": now,
            "last_validated_at": now,
            "metadata": meta,
        }
    )
    _ephemeral_rules[rule_id] = promoted
    return promoted.to_dict()


@router.post("/rules/{rule_id}/deprecate")
async def deprecate_rule(rule_id: str, payload: DeprecateRuleRequest) -> Dict[str, Any]:
    """Deprecates an existing rule."""
    rule = _ephemeral_rules.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")

    now = utc_now()
    meta = dict(rule.metadata)
    meta["deprecation_reason"] = payload.reason

    deprecated = LearnedRule(
        **{
            **rule.to_dict(),
            "state": LearnedRuleState.DEPRECATED,
            "deprecated_at": now,
            "metadata": meta,
        }
    )
    _ephemeral_rules[rule_id] = deprecated
    return deprecated.to_dict()


@router.post("/rules/{rule_id}/rollback")
async def rollback_rule(rule_id: str, payload: RollbackRuleRequest) -> Dict[str, Any]:
    """Rolls back an active rule due to regression (§20, §35)."""
    rule = _ephemeral_rules.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")

    now = utc_now()
    meta = dict(rule.metadata)
    meta["rollback_reason"] = payload.reason
    meta["rolled_back_at"] = now.isoformat()

    rolled_back = LearnedRule(
        **{
            **rule.to_dict(),
            "state": LearnedRuleState.ROLLED_BACK,
            "deprecated_at": now,
            "metadata": meta,
        }
    )
    _ephemeral_rules[rule_id] = rolled_back

    target_id = payload.rollback_target_id or rule.supersedes_id
    reactivated = None
    if target_id and target_id in _ephemeral_rules:
        tgt = _ephemeral_rules[target_id]
        reactivated = LearnedRule(
            **{
                **tgt.to_dict(),
                "state": LearnedRuleState.PROMOTED,
                "activated_at": now,
                "deprecated_at": None,
                "superseded_by": None,
            }
        )
        _ephemeral_rules[target_id] = reactivated

    return {
        "rolled_back_rule": rolled_back.to_dict(),
        "reactivated_rule": reactivated.to_dict() if reactivated else None,
    }


@router.post("/query")
async def query_rules_for_agent(payload: QueryRulesRequest) -> List[Dict[str, Any]]:
    """Resolves applicable rules for the querying agent context, enforcing visibility and conflict resolution."""
    ctx = payload.agent_context
    active_rules = [r for r in _ephemeral_rules.values() if r.domain == ctx.domain and r.is_active]

    # Visibility filter
    visible_rules: List[LearnedRule] = []
    for r in active_rules:
        if r.scope == KnowledgeVisibilityScope.GLOBAL:
            visible_rules.append(r)
        elif r.scope == KnowledgeVisibilityScope.PROJECT and ctx.project_id and r.project_id == ctx.project_id:
            visible_rules.append(r)
        elif r.scope == KnowledgeVisibilityScope.ROLE and (not r.target_role or r.target_role == ctx.role):
            visible_rules.append(r)
        elif r.scope == KnowledgeVisibilityScope.SESSION and ctx.session_id and r.metadata.get("session_id") == ctx.session_id:
            visible_rules.append(r)
        elif r.scope == KnowledgeVisibilityScope.TASK and ctx.task_id and r.metadata.get("task_id") == ctx.task_id:
            visible_rules.append(r)
        elif r.scope == KnowledgeVisibilityScope.PRIVATE_AGENT and ctx.agent_id and r.metadata.get("agent_id") == ctx.agent_id:
            visible_rules.append(r)

    # Condition matching
    matching: List[LearnedRule] = []
    for r in visible_rules:
        matches = True
        for k, v in r.condition.items():
            if k not in ctx.context_tags or ctx.context_tags[k] != v:
                matches = False
                break
        if matches:
            matching.append(r)

    if not matching:
        return []

    # Group conflicting rules
    groups: Dict[str, List[LearnedRule]] = {}
    for rule in matching:
        grp = rule.metadata.get("conflict_group") or f"{rule.target_role or 'all'}_{'_'.join(sorted(rule.condition.keys()))}"
        groups.setdefault(grp, []).append(rule)

    resolved: List[LearnedRule] = []
    for group in groups.values():
        if len(group) == 1:
            resolved.append(group[0])
        else:
            winner, rec = _resolver.resolve_conflict(
                competing_rules=group,
                context_query=ctx.context_tags,
                domain=ctx.domain,
                active_harness_version=payload.active_harness_version,
            )
            _ephemeral_conflict_resolutions[rec.resolution_id] = rec
            resolved.append(winner)

    return [r.to_dict() for r in resolved]


@router.post("/attributions", status_code=status.HTTP_201_CREATED)
async def create_attribution(payload: AttributeMetricsRequest) -> Dict[str, Any]:
    """Ingests YouTube performance signals and computes multi-agent attribution (§21, §22)."""
    baselines = payload.baseline_signals or {}
    role_attributions: Dict[str, Dict[str, Any]] = {}

    for sig_name, sig_val in payload.metric_signals.items():
        mapping = YOUTUBE_SIGNAL_ROLE_MAP.get(sig_name)
        if not mapping:
            continue

        base_val = baselines.get(sig_name, sig_val)
        delta = sig_val - base_val

        status_str = "outperforming" if delta > 0.05 else ("underperforming" if delta < -0.05 else "neutral")
        role_attributions[mapping["role"]] = {
            "signal": sig_name,
            "dimension": mapping["dimension"],
            "value": float(sig_val),
            "baseline": float(base_val),
            "delta": round(float(delta), 4),
            "status": status_str,
            "description": mapping["description"],
        }

    attribution_rec = MultiAgentAttributionRecord(
        attribution_id=f"attr_{uuid.uuid4().hex[:12]}",
        episode_id=payload.episode_id,
        domain=payload.domain,
        metric_signals=payload.metric_signals,
        role_attributions=role_attributions,
        created_at=utc_now(),
    )

    _ephemeral_attributions[attribution_rec.attribution_id] = attribution_rec
    return attribution_rec.to_dict()


@router.get("/attributions/{attribution_id}")
async def get_attribution(attribution_id: str) -> Dict[str, Any]:
    """Retrieves an attribution record by ID."""
    rec = _ephemeral_attributions.get(attribution_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Attribution '{attribution_id}' not found.")
    return rec.to_dict()


@router.get("/conflict-resolutions")
async def list_conflict_resolutions(domain: Optional[str] = Query(None), limit: int = Query(50)) -> List[Dict[str, Any]]:
    """Lists recorded conflict resolutions."""
    recs = list(_ephemeral_conflict_resolutions.values())
    if domain:
        recs = [r for r in recs if r.domain == domain]
    recs.sort(key=lambda r: r.resolved_at, reverse=True)
    return [r.to_dict() for r in recs[:limit]]

