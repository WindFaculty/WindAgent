"""API V2 Candidates endpoints for WindAgent (Phase 9 — Diagnosis & Candidate Learning).

Endpoints for proposing learning candidates, mining candidates from empirical experiences,
evaluating eligibility thresholds, and managing candidate lifecycle state transitions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearnedRule,
    LearnedRuleState,
    LearningCandidate,
)
from windagent_core.domain.experience import Experience
from windagent_intelligence.candidate.candidate_generator import CandidateGenerator
from windagent_intelligence.candidate.eligibility_gate import EligibilityGate

router = APIRouter(prefix="/api/v2/candidates", tags=["Candidates V2"])

# Ephemeral in-memory fallback store for routing / test isolation
_ephemeral_candidates: Dict[str, LearningCandidate] = {}
_ephemeral_rules: Dict[str, LearnedRule] = {}


class ProposeCandidateRequest(BaseModel):
    kind: CandidateKind
    condition: str
    proposed_change: Dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str
    supporting_experiences: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    sample_size: int = Field(default=1, ge=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    scope: CandidateScope = Field(default=CandidateScope.PROJECT)
    risk_level: CandidateRiskLevel = Field(default=CandidateRiskLevel.MEDIUM)
    project_id: Optional[str] = None
    domain: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MineCandidatesRequest(BaseModel):
    experiences: List[Dict[str, Any]]
    min_cluster_size: int = Field(default=2, ge=1)
    scope: CandidateScope = Field(default=CandidateScope.PROJECT)


class EvaluateEligibilityRequest(BaseModel):
    min_sample_size: Optional[int] = None
    min_confidence: Optional[float] = None
    max_counter_ratio: Optional[float] = None


class RejectCandidateRequest(BaseModel):
    reason: str


class CandidateResponse(BaseModel):
    candidate_id: str
    kind: CandidateKind
    condition: str
    proposed_change: Dict[str, Any]
    reasoning_summary: str
    supporting_experiences: List[str]
    counter_evidence: List[str]
    sample_size: int
    confidence: float
    scope: CandidateScope
    risk_level: CandidateRiskLevel
    status: CandidateStatus
    project_id: Optional[str] = None
    domain: Optional[str] = None
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class LearnedRuleResponse(BaseModel):
    rule_id: str
    condition: str
    recommendation: str
    domain: str
    scope: CandidateScope
    evidence_refs: List[str]
    metrics: Dict[str, Any]
    confidence: float
    sample_size: int
    created_at: datetime
    last_validated_at: Optional[datetime] = None
    harness_version: Optional[str] = None
    version: int
    state: LearnedRuleState


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
async def propose_candidate(req: ProposeCandidateRequest) -> CandidateResponse:
    """Proposes a new learning candidate (starts in PROPOSED state)."""
    cand_id = f"cand_{uuid.uuid4().hex[:12]}"
    candidate = LearningCandidate(
        candidate_id=cand_id,
        kind=req.kind,
        condition=req.condition,
        proposed_change=req.proposed_change,
        reasoning_summary=req.reasoning_summary,
        supporting_experiences=req.supporting_experiences,
        counter_evidence=req.counter_evidence,
        sample_size=req.sample_size,
        confidence=req.confidence,
        scope=req.scope,
        risk_level=req.risk_level,
        status=CandidateStatus.PROPOSED,
        project_id=req.project_id,
        domain=req.domain,
        metadata=req.metadata,
    )
    candidate.assert_candidate_invariants()
    _ephemeral_candidates[cand_id] = candidate
    return CandidateResponse(**candidate.model_dump())


@router.post("/mine", response_model=List[CandidateResponse])
async def mine_candidates(req: MineCandidatesRequest) -> List[CandidateResponse]:
    """Mines clustered learning candidates from a batch of experience records."""
    exps = [Experience.model_validate(e) for e in req.experiences]
    mined = CandidateGenerator.mine_candidates_from_experiences(
        experiences=exps,
        min_cluster_size=req.min_cluster_size,
        scope=req.scope,
    )
    for c in mined:
        _ephemeral_candidates[c.candidate_id] = c
    return [CandidateResponse(**c.model_dump()) for c in mined]


@router.get("", response_model=List[CandidateResponse])
async def list_candidates(
    status_filter: Optional[CandidateStatus] = Query(default=None, alias="status"),
    kind: Optional[CandidateKind] = None,
    scope: Optional[CandidateScope] = None,
    project_id: Optional[str] = None,
    domain: Optional[str] = None,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[CandidateResponse]:
    """Lists candidates matching filter criteria."""
    results = []
    for cand in _ephemeral_candidates.values():
        if status_filter and cand.status != status_filter:
            continue
        if kind and cand.kind != kind:
            continue
        if scope and cand.scope != scope:
            continue
        if project_id and cand.project_id != project_id:
            continue
        if domain and cand.domain != domain:
            continue
        if cand.confidence < min_confidence:
            continue
        results.append(CandidateResponse(**cand.model_dump()))
        if len(results) >= limit:
            break
    return results


@router.get("/rules", response_model=List[LearnedRuleResponse])
async def list_rules(
    domain: Optional[str] = None,
    state: Optional[LearnedRuleState] = None,
) -> List[LearnedRuleResponse]:
    """Lists learned rules with optional domain and state filter."""
    results = []
    for rule in _ephemeral_rules.values():
        if domain and rule.domain != domain:
            continue
        if state and rule.state != state:
            continue
        results.append(LearnedRuleResponse(**rule.model_dump()))
    return results


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str) -> CandidateResponse:
    """Retrieves candidate details by ID."""
    cand = _ephemeral_candidates.get(candidate_id)
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )
    return CandidateResponse(**cand.model_dump())


@router.post("/{candidate_id}/evaluate", response_model=Dict[str, Any])
async def evaluate_candidate(
    candidate_id: str,
    req: EvaluateEligibilityRequest,
) -> Dict[str, Any]:
    """Evaluates candidate eligibility against thresholds."""
    cand = _ephemeral_candidates.get(candidate_id)
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    return EligibilityGate.evaluate(
        candidate=cand,
        min_sample_size=req.min_sample_size,
        min_confidence=req.min_confidence,
        max_counter_ratio=req.max_counter_ratio,
    )


@router.post("/{candidate_id}/mark-eligible", response_model=CandidateResponse)
async def mark_candidate_eligible(
    candidate_id: str,
    req: EvaluateEligibilityRequest,
) -> CandidateResponse:
    """Transitions candidate from PROPOSED to ELIGIBLE state."""
    cand = _ephemeral_candidates.get(candidate_id)
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    try:
        eligible = EligibilityGate.apply(
            candidate=cand,
            min_sample_size=req.min_sample_size,
            min_confidence=req.min_confidence,
            max_counter_ratio=req.max_counter_ratio,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    _ephemeral_candidates[candidate_id] = eligible
    return CandidateResponse(**eligible.model_dump())


@router.post("/{candidate_id}/reject", response_model=CandidateResponse)
async def reject_candidate(
    candidate_id: str,
    req: RejectCandidateRequest,
) -> CandidateResponse:
    """Transitions candidate to REJECTED state."""
    cand = _ephemeral_candidates.get(candidate_id)
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    rejected = cand.reject(reason=req.reason)
    _ephemeral_candidates[candidate_id] = rejected
    return CandidateResponse(**rejected.model_dump())


@router.post("/{candidate_id}/expire", response_model=CandidateResponse)
async def expire_candidate(candidate_id: str) -> CandidateResponse:
    """Transitions candidate to EXPIRED state."""
    cand = _ephemeral_candidates.get(candidate_id)
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate {candidate_id} not found.",
        )

    expired = cand.expire()
    _ephemeral_candidates[candidate_id] = expired
    return CandidateResponse(**expired.model_dump())

