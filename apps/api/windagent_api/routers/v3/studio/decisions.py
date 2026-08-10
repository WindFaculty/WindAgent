"""Decision command routers: idea selection, approvals, revisions, screenplay lock."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status

from windagent_api.routers.v3.studio.dependencies import (
    get_actor,
    get_studio_application_service,
    require_idempotency_key,
)
from windagent_api.routers.v3.studio.schemas import (
    DeriveRevisionRequest,
    LockScreenplayRequest,
    RecordApprovalRequest,
    SelectIdeaRequest,
)
from windagent_api.services.studio_application_service import StudioApplicationService

router = APIRouter(prefix="/episodes/{episode_id}", tags=["studio-decisions"])


@router.post("/idea-selection", response_model=dict)
async def select_idea(
    episode_id: str = Path(...),
    body: SelectIdeaRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    result = await service.select_idea(
        path_episode_id=episode_id,
        episode_id=body.episode_id,
        revision_id=body.revision_id,
        candidate_id=body.candidate_id,
        expected_content_hash=body.expected_content_hash,
        expected_optimistic_version=body.expected_optimistic_version,
        idempotency_key=idempotency_key,
    )
    return {
        "episode_id": str(result.episode_id),
        "candidate_id": result.candidate_id,
        "revision_id": str(result.revision_id),
    }


@router.post("/approvals", response_model=dict)
async def record_approval(
    episode_id: str = Path(...),
    body: RecordApprovalRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    actor: str = Depends(get_actor),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    result = await service.record_approval(
        path_episode_id=episode_id,
        episode_id=body.episode_id,
        revision_id=body.revision_id,
        checkpoint=body.checkpoint,
        artifact_hash=body.artifact_hash,
        actor=actor,
        decision=body.decision,
        reason=body.reason,
        expected_optimistic_version=body.expected_optimistic_version,
        idempotency_key=idempotency_key,
    )
    return {
        "episode_id": str(result.episode_id),
        "checkpoint": result.checkpoint,
        "next_state": result.next_state,
        "awaiting_approval": result.awaiting_approval,
    }


@router.post("/revisions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def derive_revision(
    episode_id: str = Path(...),
    body: DeriveRevisionRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    actor: str = Depends(get_actor),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    result = await service.derive_revision(
        path_episode_id=episode_id,
        episode_id=body.episode_id,
        series_id=body.series_id,
        parent_revision_id=body.parent_revision_id,
        new_content_hash=body.new_content_hash,
        actor=actor,
        invalidation_intent=body.invalidation_intent,
        summary=body.summary,
        expected_optimistic_version=body.expected_optimistic_version,
        idempotency_key=idempotency_key,
    )
    return {
        "revision_id": str(result.revision_id),
        "parent_revision_id": str(result.parent_revision_id),
        "episode_id": str(result.episode_id),
        "revision_url": f"/api/v3/studio/episodes/{result.episode_id}",
    }


@router.post("/screenplay-lock", response_model=dict)
async def lock_screenplay(
    episode_id: str = Path(...),
    body: LockScreenplayRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    result = await service.lock_screenplay(
        path_episode_id=episode_id,
        episode_id=body.episode_id,
        revision_id=body.revision_id,
        expected_content_hash=body.expected_content_hash,
        expected_optimistic_version=body.expected_optimistic_version,
        idempotency_key=idempotency_key,
    )
    return {
        "episode_id": str(result.episode_id),
        "revision_id": str(result.revision_id),
        "lock_receipt_artifact_id": result.lock_receipt_artifact_id,
        "state": result.state,
    }
