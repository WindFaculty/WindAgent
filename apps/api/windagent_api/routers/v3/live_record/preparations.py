"""Recording Preparation endpoint — Phase 2 (ban_ke_hoach_v1.md Section 5).

Episode workspace calls this to let RECORDING_PREPARER produce a frozen
Recording Preparation Package (scenes + prepared actions + payload_bundles).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from windagent_api.routers.v3.live_record.dependencies import (
    get_live_record_service,
    require_idempotency_key,
)
from windagent_api.services.live_record_application_service import LiveRecordApplicationService

router = APIRouter(prefix="/live-record/preparations", tags=["live-record"])


class PrepareRecordingRequest(BaseModel):
    episode_id: str = Field(min_length=1)
    episode_revision_id: str = Field(min_length=1)
    source_workspace_hash: str = ""
    recording_profile: Optional[Dict[str, Any]] = None
    scenes: List[Dict[str, Any]] = Field(default_factory=list)
    # Optional explicit plan_id (for tests); normally server allocates plan_ep_rN
    plan_id: Optional[str] = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def prepare_recording_package(
    body: PrepareRecordingRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Build a Recording Preparation Package into a DRAFT LiveExecutionPlan."""
    return await service.prepare_recording_package(
        payload=body.model_dump(),
        idempotency_key=idempotency_key,
    )
