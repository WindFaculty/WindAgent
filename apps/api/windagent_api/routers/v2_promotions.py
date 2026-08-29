"""API V2 Promotion Decision & Rollback endpoints (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Provides REST endpoints for evaluating the 7 Promotion Gates, authorizing mutations,
committing new HarnessVersions, and coordinating rollbacks upon detected regressions.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

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
    HarnessVersion,
)
from windagent_core.domain.promotion import (
    PromotionDecision,
)
from windagent_orchestration.learning.promotion_gate import PromotionGate
from windagent_orchestration.learning.rollback_coordinator import RollbackCoordinator

router = APIRouter(prefix="/api/v2/promotions", tags=["Promotions V2"])

# Ephemeral in-memory stores for isolated API execution
_ephemeral_decisions: Dict[str, PromotionDecision] = {}
_ephemeral_harnesses: Dict[str, HarnessVersion] = {}
_gate = PromotionGate()
_rollback_coord = RollbackCoordinator()


class EvaluatePromotionRequest(BaseModel):
    candidate_id: str
    experiment_id: str
    source_harness_version: str
    candidate_scope: CandidateScope = CandidateScope.PROJECT
    candidate_risk: CandidateRiskLevel = CandidateRiskLevel.LOW
    candidate_kind: CandidateKind = CandidateKind.PROMPT_RULE
    accuracy_delta: float = 0.08
    safety_score: float = 1.0
    reliability_score: float = 0.95
    cost_delta: float = 0.02
    sample_size: int = 5
    project_id: Optional[str] = None
    domain: Optional[str] = None


class PromoteCandidateRequest(BaseModel):
    decision_id: str
    approver: str = "human_admin"
    new_version_id: Optional[str] = None
    rationale: str = "Promotion gate verified and approved."


class RollbackPromotionRequest(BaseModel):
    version_id: str
    decision_id: str
    reason: str


class GateChecksDTO(BaseModel):
    min_sample_size_passed: bool
    beats_baseline_passed: bool
    no_safety_regression_passed: bool
    no_reliability_regression_passed: bool
    cost_within_budget_passed: bool
    provenance_complete_passed: bool
    uncertainty_acceptable_passed: bool
    all_passed: bool
    failed_gates: List[str]
    details: Dict[str, Any]


class PromotionDecisionResponse(BaseModel):
    decision_id: str
    candidate_id: str
    experiment_id: Optional[str]
    source_harness_version: str
    target_harness_version: Optional[str]
    status: str
    gate_checks: GateChecksDTO
    is_high_risk: bool
    requires_human_approval: bool
    approved_by: Optional[str]
    approved_at: Optional[str]
    rejection_reason: Optional[str]
    decision_rationale: str
    project_id: Optional[str]
    domain: Optional[str]
    created_at: str
    metadata: Dict[str, Any]


def _to_response(dec: PromotionDecision) -> PromotionDecisionResponse:
    gc = dec.gate_checks
    gate_dto = GateChecksDTO(
        min_sample_size_passed=gc.min_sample_size_passed,
        beats_baseline_passed=gc.beats_baseline_passed,
        no_safety_regression_passed=gc.no_safety_regression_passed,
        no_reliability_regression_passed=gc.no_reliability_regression_passed,
        cost_within_budget_passed=gc.cost_within_budget_passed,
        provenance_complete_passed=gc.provenance_complete_passed,
        uncertainty_acceptable_passed=gc.uncertainty_acceptable_passed,
        all_passed=gc.all_passed,
        failed_gates=gc.failed_gates(),
        details=gc.details,
    )

    return PromotionDecisionResponse(
        decision_id=dec.decision_id,
        candidate_id=dec.candidate_id,
        experiment_id=dec.experiment_id,
        source_harness_version=dec.source_harness_version,
        target_harness_version=dec.target_harness_version,
        status=dec.status.value,
        gate_checks=gate_dto,
        is_high_risk=dec.is_high_risk,
        requires_human_approval=dec.requires_human_approval,
        approved_by=dec.approved_by,
        approved_at=dec.approved_at.isoformat() if dec.approved_at else None,
        rejection_reason=dec.rejection_reason,
        decision_rationale=dec.decision_rationale,
        project_id=dec.project_id,
        domain=dec.domain,
        created_at=dec.created_at.isoformat(),
        metadata=dec.metadata,
    )


@router.post("/evaluate", response_model=PromotionDecisionResponse, status_code=status.HTTP_200_OK)
async def evaluate_promotion(req: EvaluatePromotionRequest) -> PromotionDecisionResponse:
    """Evaluates the 7 Promotion Gates for a candidate experiment."""
    cand = LearningCandidate(
        candidate_id=req.candidate_id,
        kind=req.candidate_kind,
        condition="api_evaluation",
        proposed_change={"rule": "Evaluated rule"},
        reasoning_summary="Promotion gate evaluation API",
        supporting_experiences=["exp_api_1", "exp_api_2"],
        sample_size=req.sample_size,
        confidence=0.88,
        scope=req.candidate_scope,
        risk_level=req.candidate_risk,
        status=CandidateStatus.ELIGIBLE,
        project_id=req.project_id,
        domain=req.domain,
    )

    verdict = (
        ExperimentVerdict.BEATS_BASELINE
        if req.accuracy_delta > 0.02
        else ExperimentVerdict.TIE
        if req.accuracy_delta >= 0.0
        else ExperimentVerdict.INFERIOR
    )

    exp = Experiment(
        experiment_id=req.experiment_id,
        candidate_id=req.candidate_id,
        baseline_harness_version=req.source_harness_version,
        experiment_type=ExperimentType.REPLAY,
        status=ExperimentStatus.COMPLETED,
        sample_size=req.sample_size,
        baseline_metrics=ExperimentMetrics(accuracy=0.80, safety_score=1.0, reliability_score=0.95, sample_size=req.sample_size),
        candidate_metrics=ExperimentMetrics(
            accuracy=0.80 + req.accuracy_delta,
            safety_score=req.safety_score,
            reliability_score=req.reliability_score,
            sample_size=req.sample_size,
        ),
        comparison=StatisticalComparison(
            accuracy_delta=req.accuracy_delta,
            safety_delta=req.safety_score - 1.0,
            reliability_delta=req.reliability_score - 0.95,
            cost_delta=req.cost_delta,
            uncertainty_margin=round(1.0 / ((req.sample_size * 2) ** 0.5), 4),
        ),
        safety_check_passed=(req.safety_score >= 0.95),
        reliability_check_passed=(req.reliability_score >= 0.85),
        verdict=verdict,
        project_id=req.project_id,
        domain=req.domain,
    )

    decision = _gate.evaluate_candidate(
        candidate=cand,
        experiment=exp,
        source_harness_version=req.source_harness_version,
    )

    _ephemeral_decisions[decision.decision_id] = decision
    return _to_response(decision)


@router.post("/promote", response_model=PromotionDecisionResponse, status_code=status.HTTP_200_OK)
async def promote_candidate(req: PromoteCandidateRequest) -> PromotionDecisionResponse:
    """Executes promotion for an approved candidate decision."""
    dec = _ephemeral_decisions.get(req.decision_id)
    if not dec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promotion decision '{req.decision_id}' not found",
        )

    target_vid = req.new_version_id or f"harness_v{uuid.uuid4().hex[:6]}"
    promoted = dec.approve_and_promote(
        target_harness_version=target_vid,
        approver=req.approver,
        rationale=req.rationale,
    )

    _ephemeral_decisions[promoted.decision_id] = promoted
    return _to_response(promoted)


@router.post("/rollback", response_model=PromotionDecisionResponse, status_code=status.HTTP_200_OK)
async def rollback_promotion(req: RollbackPromotionRequest) -> PromotionDecisionResponse:
    """Rolls back a promoted harness version due to detected regression."""
    dec = _ephemeral_decisions.get(req.decision_id)
    if not dec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promotion decision '{req.decision_id}' not found",
        )

    rolled_back = dec.rollback(req.reason)
    _ephemeral_decisions[rolled_back.decision_id] = rolled_back
    return _to_response(rolled_back)


@router.get("", response_model=List[PromotionDecisionResponse])
async def list_promotions(
    candidate_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> List[PromotionDecisionResponse]:
    """Lists promotion decisions matching query parameters."""
    results = list(_ephemeral_decisions.values())
    if candidate_id:
        results = [d for d in results if d.candidate_id == candidate_id]
    if project_id:
        results = [d for d in results if d.project_id == project_id]
    if status_filter:
        results = [d for d in results if d.status.value == status_filter]

    results.sort(key=lambda d: d.created_at, reverse=True)
    return [_to_response(d) for d in results[:limit]]


@router.get("/{decision_id}", response_model=PromotionDecisionResponse)
async def get_promotion_decision(decision_id: str) -> PromotionDecisionResponse:
    """Retrieves a promotion decision by ID."""
    dec = _ephemeral_decisions.get(decision_id)
    if not dec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promotion decision '{decision_id}' not found",
        )
    return _to_response(dec)
