"""Episode resource routers (/api/v3/studio)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status

from windagent_api.routers.v3.studio.dependencies import (
    get_studio_application_service,
    require_idempotency_key,
)
from windagent_api.routers.v3.studio.schemas import CreateEpisodeRequest, EpisodeListResponse
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.contracts.studio.errors import StudioNotFoundError
from windagent_core.contracts.studio.ids import EpisodeId, SeriesProjectId

# Episodes nested under a series.
router_series_episodes = APIRouter(prefix="/series/{series_id}/episodes", tags=["studio-episodes"])

# Episode detail outside the series nesting (frozen api_surface.json).
router_episode = APIRouter(prefix="/episodes", tags=["studio-episodes"])


@router_series_episodes.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_episode(
    series_id: str = Path(...),
    body: CreateEpisodeRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    _parsed_series = service.parse_id(SeriesProjectId, series_id, "series_id")
    result = await service.create_episode(
        path_series_id=series_id,
        series_id=body.series_id,
        title=body.title,
        episode_number=body.episode_number,
        metadata=body.metadata,
        idempotency_key=idempotency_key,
    )
    return {
        "episode_id": str(result.episode_id),
        "series_id": str(result.series_id),
        "state": result.state,
        "episode_url": f"/api/v3/studio/episodes/{result.episode_id}",
    }


@router_series_episodes.get("", response_model=EpisodeListResponse)
async def list_episodes(
    series_id: str = Path(...),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> EpisodeListResponse:
    parsed_series = service.parse_id(SeriesProjectId, series_id, "series_id")
    items = await service.list_episodes(series_id=parsed_series)
    return EpisodeListResponse(items=items)


@router_episode.get("/{episode_id}", response_model=dict)
async def get_episode(
    episode_id: str = Path(...),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    parsed = service.parse_id(EpisodeId, episode_id, "episode_id")
    view = await service.get_episode(episode_id=parsed)
    if view is None:
        raise StudioNotFoundError(
            f"Episode {episode_id!r} does not exist.",
            details={"episode_id": episode_id},
        )
    return view
