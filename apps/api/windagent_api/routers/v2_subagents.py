"""API V2 Subagents Evolution & Management Router (Phase 13 — ban_ke_hoach_v1 §19, §24, §25, §29, §35).

Endpoints for specialized subagent proposals, security audits, benchmark evaluations,
human-governed promotions, versioned spec tracking, and automated rollbacks.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_api.composition.subagents import make_subagent_evolution_adapters
from windagent_core.domain.agent_loop import AgentBudgetLimits
from windagent_core.domain.lifecycle import utc_now
from windagent_core.domain.subagent_evolution import (
    MemoryAccessPolicy,
    MemoryScope,
    ModelRoutingPolicy,
    SubagentCandidate,
    SubagentCandidateStatus,
    SubagentOutputContract,
    SubagentPromotionDecision,
    SubagentPromotionStatus,
    SubagentRiskLevel,
    SubagentSpecStatus,
    SubagentSpecVersion,
)

router = APIRouter(prefix="/api/v2/subagents", tags=["Subagents V2"])

# Ephemeral state for isolated API operation
_ephemeral_candidates: Dict[str, SubagentCandidate] = {}
_ephemeral_specs: Dict[str, SubagentSpecVersion] = {}
_ephemeral_promotions: Dict[str, SubagentPromotionDecision] = {}

_scanner, _evaluator = make_subagent_evolution_adapters()


# -----------------------------------------------------------------------------
# DTO Models
# -----------------------------------------------------------------------------

class ProposeSubagentCandidateRequest(BaseModel):
    role: str = Field(description="Subagent specialized role name (e.g. 'MarketResearchAgent').")
    proposed_spec: Dict[str, Any] = Field(description="Subagent spec configuration dictionary.")
    reasoning_summary: str = Field(default="", description="Reasoning and hypothesis behind this subagent.")
    supporting_experiences: List[str] = Field(default_factory=list, description="Linked experience IDs.")
    risk_level: SubagentRiskLevel = SubagentRiskLevel.LOW
    is_high_risk: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromoteSubagentCandidateRequest(BaseModel):
    target_version: str = Field(description="Target semver string (e.g. '1.0.0').")
    approved_by: Optional[str] = Field(default=None, description="Approver ID if human review is required.")
    decision_rationale: str = Field(default="", description="Rationale for promotion decision.")


class RollbackSubagentSpecRequest(BaseModel):
    target_version_id: Optional[str] = Field(default=None, description="Optional specific spec version ID.")
    target_version: Optional[str] = Field(default=None, description="Optional target semver string.")
    reason: str = Field(default="Rollback triggered due to regression", description="Justification for rollback.")
    initiated_by: Optional[str] = Field(default=None, description="User/authority ID initiating rollback.")


class SubagentCandidateResponse(BaseModel):
    candidate_id: str
    role: str
    status: SubagentCandidateStatus
    risk_level: SubagentRiskLevel
    is_high_risk: bool
    proposed_spec: Dict[str, Any]
    reasoning_summary: str
    supporting_experiences: List[str]
    security_audit: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


class SubagentSpecResponse(BaseModel):
    id: str
    role: str
    version: str
    parent_version: Optional[str] = None
    objective: str
    system_supplement: str
    allowed_tools: List[str]
    allowed_skills: List[str]
    model_routing_policy: Dict[str, Any]
    memory_access: Dict[str, Any]
    max_budget: Dict[str, Any]
    max_depth: int
    output_contract: Dict[str, Any]
    status: SubagentSpecStatus
    risk_level: SubagentRiskLevel
    spec_hash: Optional[str] = None
    promoted_from_candidate_id: Optional[str] = None
    created_at: str
    activated_at: Optional[str] = None
    deprecated_at: Optional[str] = None


class SubagentPromotionResponse(BaseModel):
    id: str
    candidate_id: str
    role: str
    source_version: Optional[str] = None
    target_version: str
    status: SubagentPromotionStatus
    security_audit_passed: bool
    evaluation_passed: bool
    requires_human_approval: bool
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    decision_rationale: str
    created_at: str
    updated_at: str


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/candidates", response_model=SubagentCandidateResponse, status_code=status.HTTP_201_CREATED)
async def propose_candidate(payload: ProposeSubagentCandidateRequest) -> SubagentCandidateResponse:
    """Proposes a new specialized subagent candidate."""
    if not payload.role or not payload.role.strip():
        raise HTTPException(status_code=400, detail="role cannot be empty.")

    spec_data = dict(payload.proposed_spec)
    spec_data["role"] = payload.role

    mem_access = spec_data.get("memory_access", {})
    write_scopes = mem_access.get("allowed_write_scopes", []) if isinstance(mem_access, dict) else []
    has_global_write = "GLOBAL" in write_scopes or MemoryScope.GLOBAL in write_scopes or "PROJECT" in write_scopes

    max_depth = int(spec_data.get("max_depth", 2))
    max_budget = spec_data.get("max_budget", {})
    max_cost = float(max_budget.get("max_cost_usd", 0.0)) if isinstance(max_budget, dict) else 0.0

    final_high_risk = (
        payload.is_high_risk
        or has_global_write
        or (max_depth > 3)
        or (max_cost > 20.0)
        or (payload.risk_level in (SubagentRiskLevel.HIGH, SubagentRiskLevel.CRITICAL))
    )
    final_risk_level = SubagentRiskLevel.HIGH if final_high_risk and payload.risk_level == SubagentRiskLevel.LOW else payload.risk_level

    candidate_id = f"subcand_{uuid.uuid4().hex[:12]}"
    candidate = SubagentCandidate(
        candidate_id=candidate_id,
        role=payload.role,
        proposed_spec=spec_data,
        reasoning_summary=payload.reasoning_summary or f"Proposed evolution for role [{payload.role}].",
        supporting_experiences=payload.supporting_experiences,
        status=SubagentCandidateStatus.PROPOSED,
        risk_level=final_risk_level,
        is_high_risk=final_high_risk,
        metadata=payload.metadata,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    _ephemeral_candidates[candidate_id] = candidate
    return _to_candidate_dto(candidate)


@router.get("/candidates", response_model=List[SubagentCandidateResponse])
async def list_candidates(
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> List[SubagentCandidateResponse]:
    """Lists subagent candidates with optional role and status filters."""
    results = list(_ephemeral_candidates.values())
    if role:
        results = [c for c in results if c.role == role]
    if status:
        results = [c for c in results if c.status.value == status]
    return [_to_candidate_dto(c) for c in results]


@router.get("/candidates/{candidate_id}", response_model=SubagentCandidateResponse)
async def get_candidate(candidate_id: str) -> SubagentCandidateResponse:
    """Retrieves a subagent candidate by ID."""
    candidate = _ephemeral_candidates.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Subagent candidate [{candidate_id}] not found.")
    return _to_candidate_dto(candidate)


@router.post("/candidates/{candidate_id}/audit", response_model=SubagentCandidateResponse)
async def audit_candidate(candidate_id: str) -> SubagentCandidateResponse:
    """Runs a security and policy audit on a subagent candidate."""
    candidate = _ephemeral_candidates.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Subagent candidate [{candidate_id}] not found.")

    audit_result = _scanner.audit(candidate)
    updated = candidate.with_audit(audit_result)
    _ephemeral_candidates[candidate_id] = updated
    return _to_candidate_dto(updated)


@router.post("/candidates/{candidate_id}/evaluate", response_model=SubagentCandidateResponse)
async def evaluate_candidate(candidate_id: str) -> SubagentCandidateResponse:
    """Runs functional task benchmarks and contract evaluation on a subagent candidate."""
    candidate = _ephemeral_candidates.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Subagent candidate [{candidate_id}] not found.")

    if candidate.status not in (SubagentCandidateStatus.AUDITED, SubagentCandidateStatus.EVALUATED):
        audit_result = _scanner.audit(candidate)
        candidate = candidate.with_audit(audit_result)
        if not audit_result.is_safe:
            _ephemeral_candidates[candidate_id] = candidate
            return _to_candidate_dto(candidate)

    eval_result = _evaluator.evaluate(candidate)
    updated = candidate.with_evaluation(eval_result)
    _ephemeral_candidates[candidate_id] = updated
    return _to_candidate_dto(updated)


@router.post("/candidates/{candidate_id}/promote", response_model=SubagentSpecResponse)
async def promote_candidate(candidate_id: str, payload: PromoteSubagentCandidateRequest) -> SubagentSpecResponse:
    """Promotes an evaluated subagent candidate to an active, deployed SubagentSpecVersion."""
    candidate = _ephemeral_candidates.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Subagent candidate [{candidate_id}] not found.")

    if candidate.status not in (SubagentCandidateStatus.EVALUATED, SubagentCandidateStatus.AUDITED):
        raise HTTPException(
            status_code=400,
            detail=f"Candidate [{candidate_id}] is in state '{candidate.status.value}'. Must be AUDITED or EVALUATED.",
        )

    if not candidate.security_audit or not candidate.security_audit.is_safe:
        violations = ", ".join(candidate.security_audit.violations) if candidate.security_audit else "None"
        raise HTTPException(
            status_code=400,
            detail=f"Promotion rejected: security audit failed. Violations: {violations}",
        )

    if not candidate.evaluation or not candidate.evaluation.benchmark_passed:
        raise HTTPException(
            status_code=400,
            detail="Promotion rejected: evaluation benchmark failed.",
        )

    requires_human = candidate.is_high_risk or candidate.risk_level in (
        SubagentRiskLevel.HIGH,
        SubagentRiskLevel.CRITICAL,
    )
    if requires_human and not payload.approved_by:
        raise HTTPException(
            status_code=403,
            detail=f"Promotion of high-risk subagent [{candidate.role}] strictly requires human approval (approved_by).",
        )

    # Check semver collision
    for s in _ephemeral_specs.values():
        if s.role == candidate.role and s.version == payload.target_version and s.status == SubagentSpecStatus.ACTIVE:
            raise HTTPException(
                status_code=409,
                detail=f"SubagentSpecVersion [{candidate.role}:{payload.target_version}] is already active.",
            )

    # Find previous active version
    parent_version: Optional[str] = None
    for s in _ephemeral_specs.values():
        if s.role == candidate.role and s.status == SubagentSpecStatus.ACTIVE:
            parent_version = s.version
            _ephemeral_specs[s.id] = s.model_copy(
                update={"status": SubagentSpecStatus.DEPRECATED, "deprecated_at": utc_now()}
            )

    spec_dict = candidate.proposed_spec
    version_id = f"subspec_{uuid.uuid4().hex[:12]}"
    new_spec = SubagentSpecVersion(
        id=version_id,
        role=candidate.role,
        version=payload.target_version,
        parent_version=parent_version,
        objective=spec_dict.get("objective", f"Specialized {candidate.role}"),
        system_supplement=spec_dict.get("system_supplement", ""),
        allowed_tools=spec_dict.get("allowed_tools", []),
        allowed_skills=spec_dict.get("allowed_skills", []),
        model_routing_policy=ModelRoutingPolicy(**spec_dict.get("model_routing_policy", {})),
        memory_access=MemoryAccessPolicy(**spec_dict.get("memory_access", {})),
        max_budget=AgentBudgetLimits(**spec_dict.get("max_budget", {})),
        max_depth=int(spec_dict.get("max_depth", 2)),
        output_contract=SubagentOutputContract(**spec_dict.get("output_contract", {})),
        status=SubagentSpecStatus.ACTIVE,
        risk_level=candidate.risk_level,
        promoted_from_candidate_id=candidate.candidate_id,
        security_audit_id=candidate.candidate_id,
        evaluation_id=candidate.evaluation.evaluation_id if candidate.evaluation else None,
        metadata=candidate.metadata,
        created_at=utc_now(),
        activated_at=utc_now(),
    )
    _ephemeral_specs[version_id] = new_spec
    _ephemeral_candidates[candidate_id] = candidate.model_copy(
        update={"status": SubagentCandidateStatus.PROMOTED, "updated_at": utc_now()}
    )

    decision_id = f"subprom_{uuid.uuid4().hex[:12]}"
    _ephemeral_promotions[decision_id] = SubagentPromotionDecision(
        id=decision_id,
        candidate_id=candidate.candidate_id,
        role=candidate.role,
        source_version=parent_version,
        target_version=payload.target_version,
        status=SubagentPromotionStatus.PROMOTED,
        security_audit_passed=True,
        evaluation_passed=True,
        requires_human_approval=requires_human,
        approved_by=payload.approved_by,
        approved_at=utc_now() if payload.approved_by else None,
        decision_rationale=payload.decision_rationale,
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    return _to_spec_dto(new_spec)


@router.post("/roles/{role}/rollback", response_model=SubagentSpecResponse)
async def rollback_spec(role: str, payload: RollbackSubagentSpecRequest) -> SubagentSpecResponse:
    """Rolls back an active subagent spec to a previous/parent SubagentSpecVersion."""
    active_spec: Optional[SubagentSpecVersion] = None
    for s in _ephemeral_specs.values():
        if s.role == role and s.status == SubagentSpecStatus.ACTIVE:
            active_spec = s
            break

    if not active_spec:
        raise HTTPException(status_code=404, detail=f"No active SubagentSpecVersion found for role [{role}].")

    target_spec: Optional[SubagentSpecVersion] = None
    if payload.target_version_id:
        target_spec = _ephemeral_specs.get(payload.target_version_id)
    elif payload.target_version:
        for s in _ephemeral_specs.values():
            if s.role == role and s.version == payload.target_version:
                target_spec = s
                break
    elif active_spec.parent_version:
        for s in _ephemeral_specs.values():
            if s.role == role and s.version == active_spec.parent_version:
                target_spec = s
                break

    if not target_spec:
        raise HTTPException(status_code=404, detail=f"Target rollback SubagentSpecVersion not found for role [{role}].")

    _ephemeral_specs[active_spec.id] = active_spec.model_copy(
        update={"status": SubagentSpecStatus.ROLLED_BACK, "deprecated_at": utc_now()}
    )
    restored = target_spec.model_copy(
        update={"status": SubagentSpecStatus.ACTIVE, "activated_at": utc_now()}
    )
    _ephemeral_specs[restored.id] = restored

    decision_id = f"subprom_{uuid.uuid4().hex[:12]}"
    _ephemeral_promotions[decision_id] = SubagentPromotionDecision(
        id=decision_id,
        candidate_id=active_spec.promoted_from_candidate_id or "rollback_trigger",
        role=role,
        source_version=active_spec.version,
        target_version=restored.version,
        status=SubagentPromotionStatus.ROLLED_BACK,
        security_audit_passed=True,
        evaluation_passed=True,
        requires_human_approval=True,
        approved_by=payload.initiated_by,
        approved_at=utc_now(),
        rejection_reason=payload.reason,
        decision_rationale=f"Rolled back role [{role}] to [{restored.version}]",
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    return _to_spec_dto(restored)


@router.get("/specs", response_model=List[SubagentSpecResponse])
async def list_specs(
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> List[SubagentSpecResponse]:
    """Lists subagent spec versions with optional role and status filters."""
    results = list(_ephemeral_specs.values())
    if role:
        results = [s for s in results if s.role == role]
    if status:
        results = [s for s in results if s.status.value == status]
    return [_to_spec_dto(s) for s in results]


@router.get("/specs/{spec_id}", response_model=SubagentSpecResponse)
async def get_spec(spec_id: str) -> SubagentSpecResponse:
    """Retrieves a subagent spec by ID."""
    spec = _ephemeral_specs.get(spec_id)
    if not spec:
        raise HTTPException(status_code=404, detail=f"SubagentSpecVersion [{spec_id}] not found.")
    return _to_spec_dto(spec)


@router.get("/roles/{role}/active", response_model=SubagentSpecResponse)
async def get_active_spec(role: str) -> SubagentSpecResponse:
    """Retrieves the currently active spec for a role."""
    for s in _ephemeral_specs.values():
        if s.role == role and s.status == SubagentSpecStatus.ACTIVE:
            return _to_spec_dto(s)
    raise HTTPException(status_code=404, detail=f"No active SubagentSpecVersion found for role [{role}].")


@router.get("/promotions", response_model=List[SubagentPromotionResponse])
async def list_promotions(
    role: Optional[str] = Query(None),
    candidate_id: Optional[str] = Query(None),
) -> List[SubagentPromotionResponse]:
    """Lists subagent promotion decisions and rollback audits."""
    results = list(_ephemeral_promotions.values())
    if role:
        results = [p for p in results if p.role == role]
    if candidate_id:
        results = [p for p in results if p.candidate_id == candidate_id]
    return [_to_promotion_dto(p) for p in results]


# -----------------------------------------------------------------------------
# DTO Converters
# -----------------------------------------------------------------------------

def _to_candidate_dto(cand: SubagentCandidate) -> SubagentCandidateResponse:
    return SubagentCandidateResponse(
        candidate_id=cand.candidate_id,
        role=cand.role,
        status=cand.status,
        risk_level=cand.risk_level,
        is_high_risk=cand.is_high_risk,
        proposed_spec=cand.proposed_spec,
        reasoning_summary=cand.reasoning_summary,
        supporting_experiences=cand.supporting_experiences,
        security_audit=cand.security_audit.model_dump() if cand.security_audit else None,
        evaluation=cand.evaluation.model_dump() if cand.evaluation else None,
        metadata=cand.metadata,
        created_at=cand.created_at.isoformat(),
        updated_at=cand.updated_at.isoformat(),
    )


def _to_spec_dto(spec: SubagentSpecVersion) -> SubagentSpecResponse:
    return SubagentSpecResponse(
        id=spec.id,
        role=spec.role,
        version=spec.version,
        parent_version=spec.parent_version,
        objective=spec.objective,
        system_supplement=spec.system_supplement,
        allowed_tools=spec.allowed_tools,
        allowed_skills=spec.allowed_skills,
        model_routing_policy=spec.model_routing_policy.model_dump(),
        memory_access=spec.memory_access.model_dump(),
        max_budget=spec.max_budget.model_dump(),
        max_depth=spec.max_depth,
        output_contract=spec.output_contract.model_dump(),
        status=spec.status,
        risk_level=spec.risk_level,
        spec_hash=spec.spec_hash,
        promoted_from_candidate_id=spec.promoted_from_candidate_id,
        created_at=spec.created_at.isoformat(),
        activated_at=spec.activated_at.isoformat() if spec.activated_at else None,
        deprecated_at=spec.deprecated_at.isoformat() if spec.deprecated_at else None,
    )


def _to_promotion_dto(prom: SubagentPromotionDecision) -> SubagentPromotionResponse:
    return SubagentPromotionResponse(
        id=prom.id,
        candidate_id=prom.candidate_id,
        role=prom.role,
        source_version=prom.source_version,
        target_version=prom.target_version,
        status=prom.status,
        security_audit_passed=prom.security_audit_passed,
        evaluation_passed=prom.evaluation_passed,
        requires_human_approval=prom.requires_human_approval,
        approved_by=prom.approved_by,
        approved_at=prom.approved_at.isoformat() if prom.approved_at else None,
        rejection_reason=prom.rejection_reason,
        decision_rationale=prom.decision_rationale,
        created_at=prom.created_at.isoformat(),
        updated_at=prom.updated_at.isoformat(),
    )
