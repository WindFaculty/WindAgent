"""API V2 Continual Harness endpoints for WindAgent (Phase 10 — ban_ke_hoach_v1 §15, §16).

Provides REST endpoints for preview-first refinement proposals (/refine),
exact diff preview, evaluation, promotion, versioning, rollback, and prompt assembly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    HarnessVersionStatus,
    RefinementProposal,
    RefinementStatus,
)
from windagent_intelligence.harness.diff_engine import DiffEngine
from windagent_intelligence.harness.harness_assembler import HarnessAssembler
from windagent_intelligence.harness.immutable_base_guard import (
    ImmutableBaseGuard,
    ImmutableBaseViolationError,
)
from windagent_intelligence.harness.refinement_engine import RefinementEngine

router = APIRouter(prefix="/api/v2/harness", tags=["Continual Harness V2"])

# Ephemeral in-memory fallback stores for test isolation and quick prototyping
_ephemeral_versions: Dict[str, HarnessVersion] = {}
_ephemeral_refinements: Dict[str, RefinementProposal] = {}


def _get_or_init_baseline(project_id: Optional[str] = None) -> HarnessVersion:
    """Returns existing active version or creates a default baseline v1."""
    for v in _ephemeral_versions.values():
        if v.is_active and (not project_id or v.project_id == project_id):
            return v

    baseline = HarnessVersion(
        version_id=f"harness_v1_{project_id or 'global'}",
        version_number=1,
        parent_version=None,
        status=HarnessVersionStatus.ACTIVE,
        entries=[],
        diff={"summary": "Initial baseline continual harness v1"},
        evidence=[],
        promotion_decision={"reason": "Baseline bootstrap"},
        evaluation_set={"composite_score": 1.0},
        created_by="system",
        project_id=project_id,
        is_active=True,
    )
    _ephemeral_versions[baseline.version_id] = baseline
    return baseline


class HarnessEntryDTO(BaseModel):
    entry_id: str
    kind: HarnessEntryKind
    name: str
    content: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    scope: str = "project"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateHarnessVersionRequest(BaseModel):
    version_id: Optional[str] = None
    version_number: int = Field(ge=1)
    parent_version: Optional[str] = None
    status: HarnessVersionStatus = HarnessVersionStatus.DRAFT
    entries: List[HarnessEntryDTO] = Field(default_factory=list)
    diff: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)
    promotion_decision: Dict[str, Any] = Field(default_factory=dict)
    evaluation_set: Dict[str, Any] = Field(default_factory=dict)
    created_by: str = "system"
    project_id: Optional[str] = None
    domain: Optional[str] = None
    is_active: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProposeRefinementRequest(BaseModel):
    target_harness_version: Optional[str] = None
    candidate_ids: List[str] = Field(default_factory=list)
    proposed_entries: List[HarnessEntryDTO] = Field(default_factory=list)
    project_id: Optional[str] = None
    created_by: str = "system"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluateRefinementRequest(BaseModel):
    benchmark_results: Dict[str, Any] = Field(default_factory=dict)
    min_pass_score: float = Field(default=0.70, ge=0.0, le=1.0)


class PromoteRefinementRequest(BaseModel):
    promotion_authority: str = "promotion_gate"
    auto_activate: bool = True


class RollbackVersionRequest(BaseModel):
    reason: str
    fallback_to_parent: bool = True


class AssembleContextRequest(BaseModel):
    base_prompt: Optional[str] = None
    version_id: Optional[str] = None
    project_id: Optional[str] = None
    domain: Optional[str] = None


class HarnessVersionResponse(BaseModel):
    version_id: str
    version_number: int
    parent_version: Optional[str] = None
    status: HarnessVersionStatus
    entries: List[HarnessEntryDTO]
    diff: Dict[str, Any]
    evidence: List[str]
    promotion_decision: Dict[str, Any]
    evaluation_set: Dict[str, Any]
    created_by: str
    project_id: Optional[str] = None
    domain: Optional[str] = None
    is_active: bool
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RefinementProposalResponse(BaseModel):
    refinement_id: str
    target_harness_version: str
    candidate_ids: List[str]
    proposed_entries: List[HarnessEntryDTO]
    preview_diff: Dict[str, Any]
    status: RefinementStatus
    evaluation_results: Dict[str, Any]
    project_id: Optional[str] = None
    created_by: str
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AssembledContextResponse(BaseModel):
    full_system_prompt: str
    base_prompt: str
    prompt_rules: List[str]
    memory_refs: List[Dict[str, Any]]
    skill_refs: List[Dict[str, Any]]
    subagent_specs: List[Dict[str, Any]]
    routing_policies: List[Dict[str, Any]]
    harness_version_id: str
    harness_version_number: int
    entry_count: int
    estimated_tokens: int


# ====================================================================
# Refinements Endpoints (ban_ke_hoach_v1 §16)
# ====================================================================

@router.post("/refinements", response_model=RefinementProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_refinement_proposal(req: ProposeRefinementRequest) -> RefinementProposalResponse:
    """Creates a preview-first refinement proposal and computes exact diff preview."""
    target_version = None
    if req.target_harness_version:
        target_version = _ephemeral_versions.get(req.target_harness_version)
    if not target_version:
        target_version = _get_or_init_baseline(project_id=req.project_id)

    domain_entries = [
        HarnessEntry(
            entry_id=e.entry_id,
            kind=e.kind,
            name=e.name,
            content=e.content,
            priority=e.priority,
            enabled=e.enabled,
            scope=e.scope,
            metadata=e.metadata,
        )
        for e in req.proposed_entries
    ]

    try:
        proposal = RefinementEngine.propose_refinement(
            target_harness=target_version,
            custom_entries=domain_entries,
            project_id=req.project_id,
            created_by=req.created_by,
        )
    except ImmutableBaseViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _ephemeral_refinements[proposal.refinement_id] = proposal
    return RefinementProposalResponse(**proposal.model_dump())


@router.get("/refinements", response_model=List[RefinementProposalResponse])
async def list_refinement_proposals(
    status_filter: Optional[RefinementStatus] = Query(default=None, alias="status"),
    project_id: Optional[str] = None,
) -> List[RefinementProposalResponse]:
    """Lists refinement proposals matching filter criteria."""
    results = []
    for p in _ephemeral_refinements.values():
        if status_filter and p.status != status_filter:
            continue
        if project_id and p.project_id != project_id:
            continue
        results.append(RefinementProposalResponse(**p.model_dump()))
    return results


@router.get("/refinements/{refinement_id}", response_model=RefinementProposalResponse)
async def get_refinement_proposal(refinement_id: str) -> RefinementProposalResponse:
    """Retrieves refinement proposal details by ID."""
    proposal = _ephemeral_refinements.get(refinement_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refinement proposal {refinement_id} not found.",
        )
    return RefinementProposalResponse(**proposal.model_dump())


@router.get("/refinements/{refinement_id}/diff", response_model=Dict[str, Any])
async def get_refinement_diff(refinement_id: str) -> Dict[str, Any]:
    """Retrieves preview exact diff for a refinement proposal without writing."""
    proposal = _ephemeral_refinements.get(refinement_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refinement proposal {refinement_id} not found.",
        )
    return proposal.preview_diff


@router.post("/refinements/{refinement_id}/evaluate", response_model=RefinementProposalResponse)
async def evaluate_refinement_proposal(
    refinement_id: str,
    req: EvaluateRefinementRequest,
) -> RefinementProposalResponse:
    """Evaluates refinement proposal against benchmark thresholds and safety gates."""
    proposal = _ephemeral_refinements.get(refinement_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refinement proposal {refinement_id} not found.",
        )

    try:
        evaluated = RefinementEngine.evaluate_refinement(
            proposal=proposal,
            benchmark_results=req.benchmark_results,
            min_pass_score=req.min_pass_score,
        )
    except ImmutableBaseViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _ephemeral_refinements[refinement_id] = evaluated
    return RefinementProposalResponse(**evaluated.model_dump())


@router.post("/refinements/{refinement_id}/promote", response_model=HarnessVersionResponse)
async def promote_refinement_proposal(
    refinement_id: str,
    req: PromoteRefinementRequest,
) -> HarnessVersionResponse:
    """Promotes an evaluated refinement proposal into a newly committed HarnessVersion."""
    proposal = _ephemeral_refinements.get(refinement_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refinement proposal {refinement_id} not found.",
        )

    base_version = _ephemeral_versions.get(proposal.target_harness_version)
    if not base_version:
        base_version = _get_or_init_baseline(project_id=proposal.project_id)

    try:
        new_version = RefinementEngine.promote_refinement(
            proposal=proposal,
            base_version=base_version,
            promotion_authority=req.promotion_authority,
            auto_activate=req.auto_activate,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if req.auto_activate:
        for v in _ephemeral_versions.values():
            if v.is_active and v.project_id == new_version.project_id:
                _ephemeral_versions[v.version_id] = v.archive()

    _ephemeral_versions[new_version.version_id] = new_version
    _ephemeral_refinements[refinement_id] = proposal.model_copy(
        update={"status": RefinementStatus.PROMOTED}
    )

    return HarnessVersionResponse(**new_version.model_dump())


@router.post("/refinements/{refinement_id}/reject", response_model=RefinementProposalResponse)
async def reject_refinement_proposal(
    refinement_id: str,
    reason: str = Query(default="Rejected by operator"),
) -> RefinementProposalResponse:
    """Transitions a refinement proposal to REJECTED status."""
    proposal = _ephemeral_refinements.get(refinement_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refinement proposal {refinement_id} not found.",
        )

    rejected = proposal.reject(reason=reason)
    _ephemeral_refinements[refinement_id] = rejected
    return RefinementProposalResponse(**rejected.model_dump())


# ====================================================================
# Harness Versions Endpoints
# ====================================================================

@router.get("/active", response_model=HarnessVersionResponse)
async def get_active_harness_version(
    project_id: Optional[str] = None,
) -> HarnessVersionResponse:
    """Retrieves currently active HarnessVersion."""
    active = _get_or_init_baseline(project_id=project_id)
    return HarnessVersionResponse(**active.model_dump())


@router.get("/versions", response_model=List[HarnessVersionResponse])
async def list_harness_versions(
    project_id: Optional[str] = None,
    domain: Optional[str] = None,
    status_filter: Optional[HarnessVersionStatus] = Query(default=None, alias="status"),
) -> List[HarnessVersionResponse]:
    """Lists harness versions."""
    results = []
    for v in _ephemeral_versions.values():
        if project_id and v.project_id != project_id:
            continue
        if domain and v.domain != domain:
            continue
        if status_filter and v.status != status_filter:
            continue
        results.append(HarnessVersionResponse(**v.model_dump()))
    results.sort(key=lambda x: x.version_number, reverse=True)
    return results


@router.get("/versions/{version_id}", response_model=HarnessVersionResponse)
async def get_harness_version(version_id: str) -> HarnessVersionResponse:
    """Retrieves harness version details by ID."""
    v = _ephemeral_versions.get(version_id)
    if not v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Harness version {version_id} not found.",
        )
    return HarnessVersionResponse(**v.model_dump())


@router.post("/versions", response_model=HarnessVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_harness_version(req: CreateHarnessVersionRequest) -> HarnessVersionResponse:
    """Creates an immutable HarnessVersion record."""
    version_id = req.version_id or f"harness_v{req.version_number}_{uuid.uuid4().hex[:6]}"

    domain_entries = [
        HarnessEntry(
            entry_id=e.entry_id,
            kind=e.kind,
            name=e.name,
            content=e.content,
            priority=e.priority,
            enabled=e.enabled,
            scope=e.scope,
            metadata=e.metadata,
        )
        for e in req.entries
    ]

    try:
        ImmutableBaseGuard.validate_entries(domain_entries)
    except ImmutableBaseViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    version = HarnessVersion(
        version_id=version_id,
        version_number=req.version_number,
        parent_version=req.parent_version,
        status=req.status,
        entries=domain_entries,
        diff=req.diff,
        evidence=req.evidence,
        promotion_decision=req.promotion_decision,
        evaluation_set=req.evaluation_set,
        created_by=req.created_by,
        project_id=req.project_id,
        domain=req.domain,
        is_active=req.is_active,
        metadata=req.metadata,
    )

    try:
        version.assert_invariants()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _ephemeral_versions[version_id] = version
    return HarnessVersionResponse(**version.model_dump())


@router.post("/versions/{version_id}/activate", response_model=HarnessVersionResponse)
async def activate_harness_version(version_id: str) -> HarnessVersionResponse:
    """Sets a harness version as active and archives others in matching scope."""
    target = _ephemeral_versions.get(version_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Harness version {version_id} not found.",
        )

    for v in _ephemeral_versions.values():
        if v.is_active and v.project_id == target.project_id:
            _ephemeral_versions[v.version_id] = v.archive()

    activated = target.activate()
    _ephemeral_versions[version_id] = activated
    return HarnessVersionResponse(**activated.model_dump())


@router.post("/versions/{version_id}/rollback", response_model=HarnessVersionResponse)
async def rollback_harness_version(
    version_id: str,
    req: RollbackVersionRequest,
) -> HarnessVersionResponse:
    """Rolls back a harness version due to detected regression and reinstates parent version."""
    target = _ephemeral_versions.get(version_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Harness version {version_id} not found.",
        )

    try:
        rolled_back = target.rollback(reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    _ephemeral_versions[version_id] = rolled_back

    if req.fallback_to_parent and target.parent_version:
        parent = _ephemeral_versions.get(target.parent_version)
        if parent:
            _ephemeral_versions[parent.version_id] = parent.activate()

    return HarnessVersionResponse(**rolled_back.model_dump())


@router.get("/versions/{version_id}/diff", response_model=Dict[str, Any])
async def get_version_diff(
    version_id: str,
    compare_with: Optional[str] = None,
) -> Dict[str, Any]:
    """Computes exact diff between target version and its parent or another version."""
    target = _ephemeral_versions.get(version_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Harness version {version_id} not found.",
        )

    base_version = None
    if compare_with:
        base_version = _ephemeral_versions.get(compare_with)
    elif target.parent_version:
        base_version = _ephemeral_versions.get(target.parent_version)

    return DiffEngine.compute_version_diff(base_version, target)


@router.post("/assemble", response_model=AssembledContextResponse)
async def assemble_harness_context(req: AssembleContextRequest) -> AssembledContextResponse:
    """Assembles base prompt with target (or active) harness version into runtime execution context."""
    harness = None
    if req.version_id:
        harness = _ephemeral_versions.get(req.version_id)
    if not harness:
        harness = _get_or_init_baseline(project_id=req.project_id)

    ctx = HarnessAssembler.assemble(
        base_prompt=req.base_prompt,
        harness_version=harness,
        project_id=req.project_id,
        domain=req.domain,
    )

    return AssembledContextResponse(
        full_system_prompt=ctx.full_system_prompt,
        base_prompt=ctx.base_prompt,
        prompt_rules=ctx.prompt_rules,
        memory_refs=ctx.memory_refs,
        skill_refs=ctx.skill_refs,
        subagent_specs=ctx.subagent_specs,
        routing_policies=ctx.routing_policies,
        harness_version_id=ctx.harness_version_id,
        harness_version_number=ctx.harness_version_number,
        entry_count=ctx.entry_count,
        estimated_tokens=ctx.estimated_tokens,
    )

