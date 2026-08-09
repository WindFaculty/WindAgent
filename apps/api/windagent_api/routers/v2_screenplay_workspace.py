"""
API V2 Screenplay Workspace Router (Stage C — UI8 to UI18).

Provides REST API endpoints for screenplay read model projections, Fountain text parsing/serializing,
semantic revision comparison, downstream impact dry-runs, human-approved AI proposals, and lock validation gating.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_api.dependencies import get_video_production_uow
from windagent_core.domain.video_production.screenplay_command_handlers import ScreenplayCommandHandler
from windagent_core.domain.video_production.screenplay_diff import ScreenplayDiffEngine
from windagent_core.domain.video_production.screenplay_impact import ProductionImpactAnalyzer
from windagent_core.domain.video_production.screenplay_parser import ScreenplayParser, ScreenplaySerializer
from windagent_core.domain.video_production.screenplay_proposal import AIScreenplayProposalService
from windagent_core.domain.video_production.screenplay_query_service import ScreenplayQueryService
from windagent_core.domain.video_production.screenplay_validation import ScreenplayValidationGate

router = APIRouter(prefix="/api/v2/screenplay", tags=["screenplay-workspace"])


class TextParseRequestSchema(BaseModel):
    text: str
    base_screenplay_id: str = "sp_parsed"


class TextSerializeRequestSchema(BaseModel):
    screenplay: Dict[str, Any]


class ImpactDryRunRequestSchema(BaseModel):
    project_id: str
    base_model: Dict[str, Any]
    target_model: Dict[str, Any]


class AIProposalRequestSchema(BaseModel):
    project_id: str
    base_model: Dict[str, Any]
    action_type: str = Field(..., description="REWRITE | SHORTEN | EXPAND | CHANGE_TONE | POLISH_DIALOGUE")
    instruction: str
    target_scene_id: Optional[str] = None


class ProposalVerdictRequestSchema(BaseModel):
    verdict: str = Field(..., description="APPROVE | REJECT")
    actor: str = "human_operator"


@router.get("/projects/{project_id}/read-model", response_model=Dict[str, Any])
async def get_screenplay_read_model(
    project_id: str,
    revision_id: Optional[str] = Query(None, description="Optional target revision ID"),
    uow_factory=Depends(get_video_production_uow),
) -> Dict[str, Any]:
    """Retrieve canonical Screenplay Workspace Read Model (UI8)."""
    async with uow_factory as uow:
        svc = ScreenplayQueryService(uow)
        return await svc.get_screenplay_read_model(project_id, revision_id)


@router.post("/parse", response_model=Dict[str, Any])
async def parse_fountain_text(body: TextParseRequestSchema) -> Dict[str, Any]:
    """Parse Fountain text into candidate structured screenplay model (UI11)."""
    result = ScreenplayParser.parse(body.text, body.base_screenplay_id)
    return result.model_dump()


@router.post("/serialize", response_model=Dict[str, Any])
async def serialize_screenplay_model(body: TextSerializeRequestSchema) -> Dict[str, Any]:
    """Serialize structured screenplay model to Fountain text format (UI11)."""
    text = ScreenplaySerializer.serialize(body.screenplay)
    return {"text": text}


@router.post("/revisions/compare", response_model=Dict[str, Any])
async def compare_revisions(
    base_model: Dict[str, Any], target_model: Dict[str, Any]
) -> Dict[str, Any]:
    """Compute semantic revision diff between two screenplay models (UI12 & UI15)."""
    diff_res = ScreenplayDiffEngine.compare(base_model, target_model)
    return diff_res.model_dump()


@router.post("/impact/dry-run", response_model=Dict[str, Any])
async def compute_production_impact(body: ImpactDryRunRequestSchema) -> Dict[str, Any]:
    """Analyze downstream production impact before committing script edits (UI16)."""
    diff_res = ScreenplayDiffEngine.compare(body.base_model, body.target_model)
    impact = ProductionImpactAnalyzer.analyze_impact(body.project_id, diff_res)
    return impact.model_dump()


@router.post("/proposals", response_model=Dict[str, Any])
async def create_ai_proposal(body: AIProposalRequestSchema) -> Dict[str, Any]:
    """Generate reviewable AI script refactoring proposal (UI17)."""
    proposal = AIScreenplayProposalService.create_proposal(
        project_id=body.project_id,
        base_model=body.base_model,
        action_type=body.action_type,
        instruction=body.instruction,
        target_scene_id=body.target_scene_id,
    )
    return proposal.model_dump()


@router.post("/revisions/{revision_id}/lock", response_model=Dict[str, Any])
async def lock_revision_with_gate(
    revision_id: str,
    project_id: str = Query(..., description="Target VideoProject ID"),
    uow_factory=Depends(get_video_production_uow),
) -> Dict[str, Any]:
    """Revalidate and lock a revision (UI18). Blocks lock if blocking validation count > 0."""
    async with uow_factory as uow:
        query_svc = ScreenplayQueryService(uow)
        read_model = await query_svc.get_screenplay_read_model(project_id, revision_id)

        validation_report = ScreenplayValidationGate.validate_screenplay(project_id, read_model)
        if not validation_report.is_lockable:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "LOCK_REJECTED_BLOCKING_ISSUES",
                    "message": f"Cannot lock revision '{revision_id}'. Found {validation_report.blocking_count} blocking issue(s).",
                    "validation_report": validation_report.model_dump(),
                },
            )

        cmd_handler = ScreenplayCommandHandler(uow)
        res = await cmd_handler.handle_command(
            command_type="LOCK_REVISION",
            project_id=project_id,
            target_revision_id=revision_id,
            payload={"reason": "Validation gate approved lock"},
            idempotency_key=f"lock_{revision_id}",
        )
        res["validation_report"] = validation_report.model_dump()
        return res
