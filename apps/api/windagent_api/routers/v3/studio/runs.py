"""Run resource routers: start/resume, status, event stream (/api/v3/studio)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import JSONResponse

from windagent_api.routers.v3.studio.dependencies import (
    get_studio_application_service,
    require_idempotency_key,
)
from windagent_api.routers.v3.studio.schemas import RunEventsResponse, StartRunRequest
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.contracts.studio.errors import StudioNotFoundError
from windagent_core.contracts.studio.ids import EpisodeId, StudioRunId

# Start/continue a Story run for an episode.
router_runs_start = APIRouter(prefix="/episodes/{episode_id}/runs", tags=["studio-runs"])

# Run status and event stream.
router_runs = APIRouter(prefix="/runs", tags=["studio-runs"])


@router_runs_start.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_or_resume_run(
    episode_id: str = Path(...),
    body: StartRunRequest = StartRunRequest(),
    idempotency_key: str = Depends(require_idempotency_key),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> Response:
    parsed = service.parse_id(EpisodeId, episode_id, "episode_id")
    # P0.4.1 — a NEW run must pass the server-side preflight; resuming an
    # existing run is never blocked by configuration drift. Only FAIL checks
    # block; WARN surfaces honest non-blocking findings (e.g. worker not yet
    # heartbeating — durable queue accepts submit-before-worker).
    report = await service.preflight_start(episode_id=parsed)
    if not report["ready"] and (await _has_no_active_run(service, parsed)):
        failed = [c for c in report["checks"] if c["status"] == "FAIL"]
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "START_BLOCKED",
                "message": "Story start blocked: requirements not satisfied.",
                "reasons": [
                    f"{c['name']}: {c['detail'] or 'failed'}" for c in failed
                ],
                "report": report,
            },
        )
    result = await service.start_or_resume_run(
        episode_id=parsed, idempotency_key=idempotency_key
    )
    run_url = f"/api/v3/studio/runs/{result.run_id}"
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "run_id": str(result.run_id),
            "episode_id": str(result.episode_id),
            "resuming": result.resuming,
            "run_url": run_url,
        },
        headers={"Location": run_url},
    )


async def _has_no_active_run(service: StudioApplicationService, episode_id: EpisodeId) -> bool:
    """True when the episode holds no active (resumable) run."""
    view = await service.get_episode(episode_id=episode_id)
    if view is None:
        return True
    active_run_id = view.get("active_run_id") if isinstance(view, dict) else getattr(view, "active_run_id", None)
    return not active_run_id


@router_runs.get("/{run_id}", response_model=dict)
async def get_run(
    run_id: str = Path(...),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    parsed = service.parse_id(StudioRunId, run_id, "run_id")
    view = await service.get_run(run_id=parsed)
    if view is None:
        raise StudioNotFoundError(
            f"Run {run_id!r} does not exist.",
            details={"run_id": run_id},
        )
    return view


@router_runs.get("/{run_id}/events", response_model=RunEventsResponse)
async def get_run_events(
    run_id: str = Path(...),
    after: int = Query(default=0, ge=0, description="Exclusive event sequence cursor"),
    limit: int = Query(default=100, ge=1, le=1000),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> RunEventsResponse:
    parsed = service.parse_id(StudioRunId, run_id, "run_id")
    data = await service.get_run_events(run_id=parsed, after_sequence=after, limit=limit)
    return RunEventsResponse(**data)
