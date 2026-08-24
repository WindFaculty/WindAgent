"""Live Record execution-plan resource routers (/api/v3/live-record/plans).

Plan content is immutable after FROZEN; every lifecycle command re-runs the
plan aggregate's own state machine, so the HTTP layer carries no lifecycle
logic of its own.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status

from windagent_api.routers.v3.live_record.dependencies import (
    get_live_record_service,
    require_idempotency_key,
)
from windagent_api.routers.v3.live_record.schemas import (
    CreatePlanRequest,
    PatchPlanContentRequest,
    PlanListResponse,
    TakeListResponse,
    TransitionPlanRequest,
)
from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)

router = APIRouter(prefix="/live-record/plans", tags=["live-record"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: CreatePlanRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    return await service.create_plan(
        episode_id=body.episode_id,
        episode_revision_id=body.episode_revision_id,
        scenes=body.scenes,
        actions=body.actions,
        recording_profile=body.recording_profile,
        payload_bundles=body.payload_bundles,
        idempotency_key=idempotency_key,
    )


@router.get("", response_model=PlanListResponse)
async def list_plans(
    episode_id: str = Query(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> PlanListResponse:
    items = await service.list_plans(episode_id)
    return PlanListResponse(items=items)


@router.get("/{plan_id}")
async def get_plan(
    plan_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    return await service.get_plan(plan_id)


@router.patch("/{plan_id}/content")
async def patch_plan_content(
    plan_id: str = Path(..., min_length=1),
    body: PatchPlanContentRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Edit plan content before freeze; VALIDATED drops back to PREPARED."""
    return await service.patch_plan_content(
        plan_id_raw=plan_id,
        scenes=body.scenes,
        actions=body.actions,
        payload_bundles=body.payload_bundles,
        source_workspace_hash=body.source_workspace_hash,
        idempotency_key=idempotency_key,
    )


@router.post("/{plan_id}/prepare")
async def prepare_plan(
    plan_id: str = Path(..., min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """DRAFT -> PREPARED: preparation content is complete."""
    return await service.transition_plan(
        plan_id_raw=plan_id, action="prepare", idempotency_key=idempotency_key
    )


@router.post("/{plan_id}/validate")
async def validate_plan(
    plan_id: str = Path(..., min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    return await service.transition_plan(
        plan_id_raw=plan_id, action="validate", idempotency_key=idempotency_key
    )


@router.post("/{plan_id}/freeze")
async def freeze_plan(
    plan_id: str = Path(..., min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """FROZEN is immutable; only staleness may later be observed onto it."""
    return await service.transition_plan(
        plan_id_raw=plan_id, action="freeze", idempotency_key=idempotency_key
    )


@router.post("/{plan_id}/mark-stale")
async def mark_plan_stale(
    plan_id: str = Path(..., min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    return await service.transition_plan(
        plan_id_raw=plan_id, action="mark-stale", idempotency_key=idempotency_key
    )


@router.post("/{plan_id}/mark-invalid")
async def mark_plan_invalid(
    plan_id: str = Path(..., min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    return await service.transition_plan(
        plan_id_raw=plan_id, action="mark-invalid", idempotency_key=idempotency_key
    )


@router.post("/{plan_id}/staleness-check")
async def staleness_check(
    plan_id: str = Path(..., min_length=1),
    body: TransitionPlanRequest = ...,
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Assert the plan's bound revision matches the episode's current revision
    (Principle A). 422 RECORDING_PLAN_STALE when the episode has moved on."""
    return await service.transition_plan(
        plan_id_raw=plan_id,
        action="check",
        idempotency_key="read-only",
        current_episode_revision_id=body.current_episode_revision_id,
    )


@router.post("/{plan_id}/privacy-scan")
async def privacy_scan(
    plan_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Section 23/33 preflight guard: prove plan content is secret-free.

    Scans payload bundles (typed code / commands), narration and action
    metadata against credential-shaped patterns plus exact matches of the
    configured provider credentials. Findings are masked; any finding blocks
    recording (fail-closed).
    """
    return await service.scan_plan_privacy(plan_id_raw=plan_id)


@router.post("/{plan_id}/takes", status_code=status.HTTP_201_CREATED)
async def create_take(
    plan_id: str = Path(..., min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Open a recording take on a FROZEN plan; stamps the canonical plan hash."""
    return await service.create_take(
        plan_id_raw=plan_id, idempotency_key=idempotency_key
    )


@router.get("/{plan_id}/takes", response_model=TakeListResponse)
async def list_takes(
    plan_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> TakeListResponse:
    items = await service.list_takes(plan_id)
    return TakeListResponse(items=items)
