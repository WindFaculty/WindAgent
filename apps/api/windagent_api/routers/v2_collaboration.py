"""
API V2 Collaboration & Human Control Router (Stage F — UI37 & UI38).

Exposes durable endpoints for proposal lifecycle management (submit, list, detail,
approve, reject) and real-time production activity timeline projection and replay.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_api.dependencies import get_video_production_uow
from windagent_core.domain.video_production.collaboration_proposal import (
    ProposalStatus,
    ProposalType,
    ProductionChangeProposal,
    UniversalProposalService,
    SensitiveOperationPolicy,
)
from windagent_core.domain.video_production.activity_timeline import (
    ActivityCategory,
    ActivityProjector,
    ProductionActivity,
)
from windagent_core.domain.video_production.command_dispatcher import CommandDispatcher

router = APIRouter(prefix="/api/v2/collaboration", tags=["collaboration-human-control"])


class CreateProposalRequestSchema(BaseModel):
    project_id: str
    proposal_type: ProposalType
    target_revision_id: str
    base_sequence: int = 1
    creator_actor: str
    candidate_payload: Dict[str, Any]
    affected_entities: List[str] = Field(default_factory=list)
    base_payload: Optional[Dict[str, Any]] = None


class ApproveProposalRequestSchema(BaseModel):
    approver_actor: str
    reason: str = "Human approval"
    idempotency_key: Optional[str] = None
    current_project_sequence: int = 1


class RejectProposalRequestSchema(BaseModel):
    rejector_actor: str
    reason: str


class ReplayEventsRequestSchema(BaseModel):
    events: List[Dict[str, Any]]


@router.post("/proposals", response_model=Dict[str, Any])
async def create_proposal(body: CreateProposalRequestSchema) -> Dict[str, Any]:
    """Submit a new change proposal for human/policy approval."""
    proposal = UniversalProposalService.create_proposal(
        project_id=body.project_id,
        proposal_type=body.proposal_type,
        target_revision_id=body.target_revision_id,
        base_sequence=body.base_sequence,
        creator_actor=body.creator_actor,
        candidate_payload=body.candidate_payload,
        affected_entities=body.affected_entities,
        base_payload=body.base_payload,
    )

    # Append activity to timeline
    ActivityProjector.project_event(
        event_id=f"evt_{proposal.proposal_id}",
        project_id=proposal.project_id,
        revision_id=proposal.target_revision_id,
        event_type="PROPOSAL_CREATED",
        actor=proposal.created_by_agent,
        payload={
            "proposal_id": proposal.proposal_id,
            "proposal_type": proposal.proposal_type.value,
        },
        sequence=proposal.base_sequence,
    )

    return proposal.model_dump()


@router.get("/proposals", response_model=List[Dict[str, Any]])
async def list_proposals(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by proposal status"),
    proposal_type: Optional[str] = Query(None, description="Filter by proposal type"),
) -> List[Dict[str, Any]]:
    """List proposals matching filter criteria."""
    proposals = UniversalProposalService.list_proposals(
        project_id=project_id,
        status=status_filter,
        proposal_type=proposal_type,
    )
    return [p.model_dump() for p in proposals]


@router.get("/proposals/{proposal_id}", response_model=Dict[str, Any])
async def get_proposal_detail(proposal_id: str) -> Dict[str, Any]:
    """Retrieve detailed view of a single proposal."""
    proposal = UniversalProposalService.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "type": "https://windagent.io/errors/proposal-not-found",
                "title": "Proposal Not Found",
                "status": 404,
                "code": "PROPOSAL_NOT_FOUND",
                "detail": f"Proposal '{proposal_id}' does not exist.",
            },
        )
    return proposal.model_dump()


@router.post("/proposals/{proposal_id}/approve", response_model=Dict[str, Any])
async def approve_proposal(
    proposal_id: str,
    body: ApproveProposalRequestSchema,
    uow_factory=Depends(get_video_production_uow),
) -> Dict[str, Any]:
    """Approve a change proposal and execute underlying canonical command."""
    async with uow_factory as uow:
        dispatcher = CommandDispatcher(uow)
        try:
            proposal = await UniversalProposalService.approve_proposal(
                proposal_id=proposal_id,
                approver_actor=body.approver_actor,
                current_project_sequence=body.current_project_sequence,
                command_dispatcher=dispatcher,
                idempotency_key=body.idempotency_key,
                reason=body.reason,
            )
        except Exception as exc:
            err_msg = str(exc)
            err_code = getattr(exc, "code", "APPROVAL_FAILED")
            if "Permission" in exc.__class__.__name__ or "BLOCKED" in err_code:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "type": "https://windagent.io/errors/approval-permission-denied",
                        "title": "Approval Permission Denied",
                        "status": 403,
                        "code": err_code,
                        "detail": err_msg,
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": "https://windagent.io/errors/approval-conflict",
                    "title": "Approval Conflict",
                    "status": 409,
                    "code": err_code,
                    "detail": err_msg,
                },
            )

        # Log timeline event
        ActivityProjector.project_event(
            event_id=f"evt_appr_{proposal.proposal_id}",
            project_id=proposal.project_id,
            revision_id=proposal.resulting_revision_id or proposal.target_revision_id,
            event_type="PROPOSAL_APPROVED",
            actor=body.approver_actor,
            payload={
                "proposal_id": proposal.proposal_id,
                "resulting_command_id": proposal.resulting_command_id,
                "resulting_revision_id": proposal.resulting_revision_id,
            },
        )

        return proposal.model_dump()


@router.post("/proposals/{proposal_id}/reject", response_model=Dict[str, Any])
async def reject_proposal(
    proposal_id: str,
    body: RejectProposalRequestSchema,
) -> Dict[str, Any]:
    """Reject a change proposal with a mandatory decision reason."""
    try:
        proposal = UniversalProposalService.reject_proposal(
            proposal_id=proposal_id,
            rejector_actor=body.rejector_actor,
            reason=body.reason,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "https://windagent.io/errors/rejection-failed",
                "title": "Rejection Failed",
                "status": 409,
                "code": getattr(exc, "code", "REJECTION_FAILED"),
                "detail": str(exc),
            },
        )

    # Log timeline event
    ActivityProjector.project_event(
        event_id=f"evt_rej_{proposal.proposal_id}",
        project_id=proposal.project_id,
        revision_id=proposal.target_revision_id,
        event_type="PROPOSAL_REJECTED",
        actor=body.rejector_actor,
        payload={"proposal_id": proposal.proposal_id, "reason": body.reason},
    )

    return proposal.model_dump()


@router.get("/timeline", response_model=List[Dict[str, Any]])
async def get_activity_timeline(
    project_id: Optional[str] = Query(None, description="Filter timeline by project ID"),
    category: Optional[str] = Query(None, description="Filter by activity category"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    """Query production activity timeline."""
    activities = ActivityProjector.list_activities(
        project_id=project_id,
        category=category,
        limit=limit,
        offset=offset,
    )
    return [a.model_dump() for a in activities]


@router.post("/timeline/replay", response_model=List[Dict[str, Any]])
async def replay_activity_timeline(body: ReplayEventsRequestSchema) -> List[Dict[str, Any]]:
    """Replay event stream to update production activity timeline projection."""
    activities = ActivityProjector.replay_event_stream(body.events)
    return [a.model_dump() for a in activities]
