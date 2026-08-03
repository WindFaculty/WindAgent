"""
API V2 Production Workspace Router (Phase 23 — plan 06 §18.1).

Exposes endpoints for workspace snapshots, mutating command requests with
idempotency keys and optimistic concurrency (revision_id) checks, and authorized
media delivery.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.workspace import (
    CostApprovalSummary,
    HumanTakeoverPanelState,
    WorkspaceCommandRequest,
    WorkspaceCommandResult,
    WorkspaceCommandStatus,
    WorkspaceCommandType,
    WorkspaceSnapshot,
)

router = APIRouter(prefix="/api/v2/video-production/workspace", tags=["production-workspace"])

# In-memory idempotency cache and revision state for API router
_IDEMPOTENCY_STORE: dict[str, dict[str, Any]] = {}
_CURRENT_REVISION_STORE: dict[str, str] = {"vp_poc": "rev_poc_01"}


class CommandRequestSchema(BaseModel):
    command_type: WorkspaceCommandType
    project_id: str
    target_revision_id: str
    entity_id: str
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/snapshot", response_model=dict[str, Any])
def get_workspace_snapshot(
    project_id: str = Query(..., description="Target VideoProject ID"),
    revision_id: str | None = Query(None, description="Optional target revision ID"),
) -> dict[str, Any]:
    """Retrieve consolidated workspace state snapshot."""
    current_rev = _CURRENT_REVISION_STORE.get(project_id, "rev_poc_01")
    if revision_id and revision_id != current_rev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale revision: Requested '{revision_id}', current is '{current_rev}'",
        )

    snapshot = WorkspaceSnapshot(
        project_id=VideoProjectId(project_id),
        revision_id=ProductionRevisionId(current_rev),
        project_status="IN_PRODUCTION",
        creative_brief_locked=True,
        screenplay_locked=True,
        total_shots=6,
        candidates_count=12,
        cost_summary=CostApprovalSummary(
            project_id=VideoProjectId(project_id),
            estimated_credits=25.0,
            max_approved_credits=50.0,
            reserved_credits=10.0,
            debited_credits=15.0,
            remaining_credits=25.0,
        ),
        human_takeover_state=None,
        current_sequence=1042,
        authorized_media_urls={
            "shot_01": "/api/v2/video-production/workspace/media/tok_shot_01_a9f8",
            "shot_02": "/api/v2/video-production/workspace/media/tok_shot_02_b7e6",
        },
    )

    return {
        "project_id": str(snapshot.project_id),
        "revision_id": str(snapshot.revision_id),
        "project_status": snapshot.project_status,
        "creative_brief_locked": snapshot.creative_brief_locked,
        "screenplay_locked": snapshot.screenplay_locked,
        "total_shots": snapshot.total_shots,
        "candidates_count": snapshot.candidates_count,
        "cost_summary": {
            "estimated_credits": snapshot.cost_summary.estimated_credits,
            "max_approved_credits": snapshot.cost_summary.max_approved_credits,
            "reserved_credits": snapshot.cost_summary.reserved_credits,
            "debited_credits": snapshot.cost_summary.debited_credits,
            "remaining_credits": snapshot.cost_summary.remaining_credits,
            "can_proceed": snapshot.cost_summary.can_proceed,
        },
        "human_takeover_state": snapshot.human_takeover_state,
        "current_sequence": snapshot.current_sequence,
        "authorized_media_urls": snapshot.authorized_media_urls,
    }


@router.post("/commands", response_model=dict[str, Any])
def execute_workspace_command(
    body: CommandRequestSchema,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
) -> dict[str, Any]:
    """Process mutating workspace actions with idempotency & revision validation."""
    # Check idempotency cache
    if x_idempotency_key in _IDEMPOTENCY_STORE:
        return _IDEMPOTENCY_STORE[x_idempotency_key]

    current_rev = _CURRENT_REVISION_STORE.get(body.project_id, "rev_poc_01")
    if body.target_revision_id != current_rev:
        res = {
            "command_id": str(uuid.uuid4()),
            "status": WorkspaceCommandStatus.REJECTED_STALE.value,
            "updated_revision_id": current_rev,
            "message": f"Command rejected: Target revision '{body.target_revision_id}' is stale. Server is at '{current_rev}'",
            "payload": {},
        }
        _IDEMPOTENCY_STORE[x_idempotency_key] = res
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=res)

    # Process command & optionally bump revision
    new_rev = current_rev
    if body.command_type in (
        WorkspaceCommandType.APPROVE_CANDIDATE,
        WorkspaceCommandType.OVERRIDE_CANDIDATE,
    ):
        new_rev = f"rev_poc_{uuid.uuid4().hex[:6]}"
        _CURRENT_REVISION_STORE[body.project_id] = new_rev

    response_data = {
        "command_id": str(uuid.uuid4()),
        "status": WorkspaceCommandStatus.COMPLETED.value,
        "updated_revision_id": new_rev,
        "message": f"Command '{body.command_type.value}' executed successfully.",
        "payload": {"entity_id": body.entity_id, "reason": body.reason},
    }

    _IDEMPOTENCY_STORE[x_idempotency_key] = response_data
    return response_data


@router.get("/media/{media_token}")
def get_authorized_media(media_token: str) -> dict[str, str]:
    """Deliver authorized media delivery token resolution (no file paths exposed)."""
    if not media_token.startswith("tok_"):
        raise HTTPException(status_code=403, detail="Invalid media token format")
    return {
        "media_token": media_token,
        "content_type": "video/mp4",
        "status": "AUTHORIZED",
    }
