"""Artifact resource routers (/api/v3/studio)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from windagent_api.routers.v3.studio.dependencies import get_studio_application_service
from windagent_api.routers.v3.studio.schemas import ArtifactListResponse
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.contracts.studio.errors import StudioNotFoundError
from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId

# Artifacts nested under an episode.
router_episode_artifacts = APIRouter(
    prefix="/episodes/{episode_id}/artifacts", tags=["studio-artifacts"]
)

# Artifact detail outside the episode nesting.
router_artifact = APIRouter(prefix="/artifacts", tags=["studio-artifacts"])


@router_episode_artifacts.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    episode_id: str = Path(...),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> ArtifactListResponse:
    parsed = service.parse_id(EpisodeId, episode_id, "episode_id")
    items = await service.list_artifacts(episode_id=parsed)
    return ArtifactListResponse(items=items, episode_id=episode_id)


@router_artifact.get("/{artifact_id}", response_model=dict)
async def get_artifact(
    artifact_id: str = Path(...),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    parsed = service.parse_id(ArtifactId, artifact_id, "artifact_id")
    view = await service.get_artifact(artifact_id=parsed)
    if view is None:
        raise StudioNotFoundError(
            f"Artifact {artifact_id!r} does not exist.",
            details={"artifact_id": artifact_id},
        )
    return view
