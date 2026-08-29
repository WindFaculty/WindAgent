"""API V2 Experiences endpoints for WindAgent (Phase 8 — Experience Store).

Endpoints for querying empirical agent experiences, attaching diagnostic hypotheses,
filtering learning-ready experiences, and archiving execution records.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.experience import Experience, ExperienceState
from windagent_intelligence.experience.diagnostics import ExperienceDiagnostics

router = APIRouter(prefix="/api/v2/experiences", tags=["Experiences V2"])

# Module-level ephemeral store for API testing / routing fallback
_ephemeral_store: Dict[str, Experience] = {}


class ExperienceResponse(BaseModel):
    experience_id: str
    execution_id: str
    trajectory_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    state: ExperienceState
    context: Dict[str, Any] = Field(default_factory=dict)
    decision: Dict[str, Any] = Field(default_factory=dict)
    action: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    evaluator_results: List[Dict[str, Any]] = Field(default_factory=list)
    hypothesis: Optional[str] = None
    confidence: float = 0.0
    provenance: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DiagnoseExperienceRequest(BaseModel):
    hypothesis: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    baseline_metrics: Optional[Dict[str, float]] = None
    details: Optional[Dict[str, Any]] = None


class CreateExperienceRequest(BaseModel):
    execution_id: str
    trajectory_id: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    decision: Dict[str, Any] = Field(default_factory=dict)
    action: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    evaluator_results: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


@router.post("", response_model=ExperienceResponse, status_code=status.HTTP_201_CREATED)
async def create_experience(req: CreateExperienceRequest) -> ExperienceResponse:
    """Creates a new empirical experience in RAW or EVALUATED state."""
    exp_id = f"exp_{uuid.uuid4().hex[:12]}"
    initial_state = ExperienceState.EVALUATED if req.evaluator_results else ExperienceState.RAW

    exp = Experience(
        experience_id=exp_id,
        execution_id=req.execution_id,
        trajectory_id=req.trajectory_id,
        parent_task_id=req.parent_task_id,
        session_id=req.session_id,
        project_id=req.project_id,
        state=initial_state,
        context=req.context,
        decision=req.decision,
        action=req.action,
        result=req.result,
        artifacts=req.artifacts,
        metrics=req.metrics,
        evaluator_results=req.evaluator_results,
        provenance=req.provenance,
    )
    _ephemeral_store[exp_id] = exp
    return ExperienceResponse(**exp.model_dump())


@router.get("/learning-ready", response_model=List[ExperienceResponse])
async def list_learning_ready(
    project_id: Optional[str] = None,
    min_confidence: float = Query(default=0.6, ge=0.0, le=1.0),
) -> List[ExperienceResponse]:
    """Returns experiences qualified for Phase 9 Learning Candidate generation."""
    candidates = [
        ExperienceResponse(**exp.model_dump())
        for exp in _ephemeral_store.values()
        if (project_id is None or exp.project_id == project_id)
        and exp.is_learning_candidate_ready(min_confidence=min_confidence)
    ]
    return candidates


@router.get("/{experience_id}", response_model=ExperienceResponse)
async def get_experience(experience_id: str) -> ExperienceResponse:
    """Retrieves an experience by its identifier."""
    exp = _ephemeral_store.get(experience_id)
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experience {experience_id} not found.",
        )
    return ExperienceResponse(**exp.model_dump())


@router.get("", response_model=List[ExperienceResponse])
async def list_experiences(
    project_id: Optional[str] = None,
    state: Optional[ExperienceState] = None,
    execution_id: Optional[str] = None,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[ExperienceResponse]:
    """Lists experiences matching filter criteria."""
    results = []
    for exp in _ephemeral_store.values():
        if project_id and exp.project_id != project_id:
            continue
        if state and exp.state != state:
            continue
        if execution_id and exp.execution_id != execution_id:
            continue
        if exp.confidence < min_confidence:
            continue
        results.append(ExperienceResponse(**exp.model_dump()))
        if len(results) >= limit:
            break
    return results


@router.post("/{experience_id}/diagnose", response_model=ExperienceResponse)
async def diagnose_experience(
    experience_id: str,
    req: DiagnoseExperienceRequest,
) -> ExperienceResponse:
    """Applies diagnosis and attribution to transition an experience into DIAGNOSED state."""
    exp = _ephemeral_store.get(experience_id)
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experience {experience_id} not found.",
        )

    if req.hypothesis and req.confidence is not None:
        diagnosed = exp.with_diagnosis(
            hypothesis=req.hypothesis,
            confidence=req.confidence,
            details=req.details,
        )
    else:
        diagnosed = ExperienceDiagnostics.attribute_experience(
            experience=exp,
            custom_hypothesis=req.hypothesis,
            baseline_metrics=req.baseline_metrics,
        )

    _ephemeral_store[experience_id] = diagnosed
    return ExperienceResponse(**diagnosed.model_dump())


@router.post("/{experience_id}/archive", response_model=ExperienceResponse)
async def archive_experience(experience_id: str) -> ExperienceResponse:
    """Transitions an experience into ARCHIVED state."""
    exp = _ephemeral_store.get(experience_id)
    if not exp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experience {experience_id} not found.",
        )

    archived = exp.archive()
    _ephemeral_store[experience_id] = archived
    return ExperienceResponse(**archived.model_dump())
