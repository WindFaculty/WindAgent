"""
FastAPI Router for Stage G — Recovery Reconciliation & 3-Way Conflict Resolution (UI39 & UI40).
Exposes /api/v2/recovery/reconcile, /api/v2/conflict/three-way-diff, /api/v2/conflict/resolve,
and handles HTTP 409 REJECTED_STALE responses.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.state_recovery import (
    ProductionRecoverySnapshot,
    compute_snapshot_checksum,
    sanitize_recovery_payload,
)
from windagent_core.domain.video_production.conflict_resolution_service import (
    ConflictResolutionService,
    ConflictResolutionPayload,
    ResolutionStrategy,
    ThreeWayDiffResult,
    ConflictClassification,
)
from windagent_core.errors.exceptions import ValidationError

router = APIRouter(prefix="/api/v2", tags=["Recovery & Conflict Handling"])


class ThreeWayDiffRequest(BaseModel):
    project_id: str
    base_revision_id: str
    local_payload: Dict[str, Any]
    latest_revision_id: str
    latest_payload: Optional[Dict[str, Any]] = None


class ReconcileRequest(BaseModel):
    project_id: str
    client_base_revision_id: str
    client_base_sequence: int
    snapshot: Optional[Dict[str, Any]] = None


class ReconcileResponse(BaseModel):
    status: str  # "MATCHED" | "STALE_DRAFT_DETECTED" | "SEQUENCE_GAP" | "CORRUPT_CLEARED"
    server_current_revision_id: str
    server_current_sequence: int
    requires_diff_resolution: bool = False
    message: str = ""


class StaleConflictErrorResponse(BaseModel):
    code: str = "REJECTED_STALE"
    detail: str = "Client revision is stale. High concurrency edit detected."
    client_base_revision_id: str
    server_current_revision_id: str
    server_current_sequence: int


@router.get("/recovery/reconcile", response_model=ReconcileResponse)
async def reconcile_bootstrap(
    project_id: str = Query(...),
    client_base_revision_id: str = Query("rev_01"),
    client_base_sequence: int = Query(0),
) -> ReconcileResponse:
    """Bootstrap reconciliation endpoint comparing client state against server state."""
    server_rev = "rev_01"  # Simulated current server revision
    server_seq = 1        # Simulated current server sequence

    if client_base_revision_id == server_rev:
        return ReconcileResponse(
            status="MATCHED",
            server_current_revision_id=server_rev,
            server_current_sequence=server_seq,
            requires_diff_resolution=False,
            message="Client base revision matches server canonical state.",
        )
    elif client_base_sequence < server_seq:
        return ReconcileResponse(
            status="STALE_DRAFT_DETECTED",
            server_current_revision_id=server_rev,
            server_current_sequence=server_seq,
            requires_diff_resolution=True,
            message="Server has advanced past client base revision. Local draft is stale.",
        )
    else:
        return ReconcileResponse(
            status="SEQUENCE_GAP",
            server_current_revision_id=server_rev,
            server_current_sequence=server_seq,
            requires_diff_resolution=True,
            message="Sequence gap detected. Refetch required.",
        )


@router.post("/conflict/three-way-diff", response_model=ThreeWayDiffResult)
async def compute_three_way_diff(req: ThreeWayDiffRequest) -> ThreeWayDiffResult:
    """Computes entity & field level 3-way semantic diff between Base, Local, and Remote."""
    return ConflictResolutionService.compute_three_way_diff(
        project_id=req.project_id,
        base_revision_id=req.base_revision_id,
        local_payload=req.local_payload,
        latest_revision_id=req.latest_revision_id,
        latest_payload=req.latest_payload,
    )


@router.post("/conflict/resolve")
async def resolve_conflict(payload: ConflictResolutionPayload) -> Dict[str, Any]:
    """Applies conflict resolution strategy and issues a new revision on top of latest base."""
    return ConflictResolutionService.resolve_conflict(payload)


@router.post("/conflict/check-stale-edit")
async def check_stale_edit(
    project_id: str,
    client_base_revision_id: str,
    server_latest_revision_id: str = "rev_02",
    server_latest_sequence: int = 5,
) -> Dict[str, Any]:
    """
    Checks if edit is stale. If stale, raises 409 REJECTED_STALE HTTP exception with context.
    """
    if client_base_revision_id != server_latest_revision_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "REJECTED_STALE",
                "message": "Client edit rejected because server has advanced to a newer revision.",
                "client_base_revision_id": client_base_revision_id,
                "server_current_revision_id": server_latest_revision_id,
                "server_current_sequence": server_latest_sequence,
            },
        )
    return {"status": "OK", "message": "Client base is current."}
