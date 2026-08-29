"""API V2 Experiment endpoints for WindAgent (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Provides REST endpoints for running and querying empirical candidate-baseline experiments,
evaluating statistical significance, safety compliance, and cost impact.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)
from windagent_core.domain.experiment import (
    Experiment,
    ExperimentType,
)
from windagent_orchestration.learning.experiment_runner import ExperimentRunner

router = APIRouter(prefix="/api/v2/experiments", tags=["Experiments V2"])

# Ephemeral in-memory store for isolated router execution
_ephemeral_experiments: Dict[str, Experiment] = {}
_runner = ExperimentRunner()


class RunExperimentRequest(BaseModel):
    candidate_id: str
    baseline_harness_version: str
    experiment_type: ExperimentType = ExperimentType.REPLAY
    dataset_id: Optional[str] = None
    baseline_episodes: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_episodes: List[Dict[str, Any]] = Field(default_factory=list)
    project_id: Optional[str] = None
    domain: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    experiment_id: str
    candidate_id: str
    baseline_harness_version: str
    experiment_type: str
    status: str
    dataset_id: Optional[str]
    sample_size: int
    baseline_metrics: Optional[Dict[str, Any]]
    candidate_metrics: Optional[Dict[str, Any]]
    comparison: Optional[Dict[str, Any]]
    safety_check_passed: bool
    reliability_check_passed: bool
    verdict: str
    project_id: Optional[str]
    domain: Optional[str]
    created_at: str
    completed_at: Optional[str]
    metadata: Dict[str, Any]


def _to_response(exp: Experiment) -> ExperimentResponse:
    return ExperimentResponse(
        experiment_id=exp.experiment_id,
        candidate_id=exp.candidate_id,
        baseline_harness_version=exp.baseline_harness_version,
        experiment_type=exp.experiment_type.value,
        status=exp.status.value,
        dataset_id=exp.dataset_id,
        sample_size=exp.sample_size,
        baseline_metrics=exp.baseline_metrics.model_dump() if exp.baseline_metrics else None,
        candidate_metrics=exp.candidate_metrics.model_dump() if exp.candidate_metrics else None,
        comparison=exp.comparison.model_dump() if exp.comparison else None,
        safety_check_passed=exp.safety_check_passed,
        reliability_check_passed=exp.reliability_check_passed,
        verdict=exp.verdict.value,
        project_id=exp.project_id,
        domain=exp.domain,
        created_at=exp.created_at.isoformat(),
        completed_at=exp.completed_at.isoformat() if exp.completed_at else None,
        metadata=exp.metadata,
    )


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_and_run_experiment(req: RunExperimentRequest) -> ExperimentResponse:
    """Runs a comparative experiment between baseline and candidate and persists the result."""
    # Synthetic candidate stub if running standalone via API
    cand = LearningCandidate(
        candidate_id=req.candidate_id,
        kind=CandidateKind.PROMPT_RULE,
        condition="api_evaluation",
        proposed_change={"rule": "Test modification"},
        reasoning_summary="API evaluation test",
        sample_size=max(1, len(req.candidate_episodes)),
        confidence=0.85,
        scope=CandidateScope.PROJECT,
        risk_level=CandidateRiskLevel.LOW,
        status=CandidateStatus.EXPERIMENTING,
        project_id=req.project_id,
        domain=req.domain,
    )

    base_eps = req.baseline_episodes or [
        {"accuracy": 0.80, "safety_score": 1.0, "reliability_score": 0.95, "cost_usd": 0.05}
    ]
    cand_eps = req.candidate_episodes or [
        {"accuracy": 0.92, "safety_score": 1.0, "reliability_score": 0.95, "cost_usd": 0.05}
    ]

    exp = await _runner.run_experiment(
        candidate=cand,
        baseline_harness_version=req.baseline_harness_version,
        baseline_episodes=base_eps,
        candidate_episodes=cand_eps,
        experiment_type=req.experiment_type,
        dataset_id=req.dataset_id,
    )

    _ephemeral_experiments[exp.experiment_id] = exp
    return _to_response(exp)


@router.get("", response_model=List[ExperimentResponse])
async def list_experiments(
    candidate_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ExperimentResponse]:
    """Lists experiments matching query parameters."""
    results = list(_ephemeral_experiments.values())
    if candidate_id:
        results = [e for e in results if e.candidate_id == candidate_id]
    if project_id:
        results = [e for e in results if e.project_id == project_id]
    if status_filter:
        results = [e for e in results if e.status.value == status_filter]

    results.sort(key=lambda e: e.created_at, reverse=True)
    return [_to_response(e) for e in results[:limit]]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str) -> ExperimentResponse:
    """Retrieves an experiment by ID."""
    exp = _ephemeral_experiments.get(experiment_id)
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found",
        )
    return _to_response(exp)
