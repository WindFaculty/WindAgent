"""
/api/v3/studio aggregator (Plan C1).

The single narrow include registered in ``main.py``. Composes the modular
resource routers plus the capability/readiness view the desktop and
certification need. No route here orchestrates or persists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from windagent_api.routers.v3.studio.artifacts import (
    router_artifact,
    router_episode_artifacts,
)
from windagent_api.routers.v3.studio.dependencies import get_studio_application_service
from windagent_api.routers.v3.studio.decisions import router as decisions_router
from windagent_api.routers.v3.studio.episodes import router_episode, router_series_episodes
from windagent_api.routers.v3.studio.runs import router_runs, router_runs_start
from windagent_api.routers.v3.studio.schemas import ReadinessResponse
from windagent_api.routers.v3.studio.series import router as series_router
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.contracts.studio.capabilities import (
    CapabilityStatus,
    RuntimeCapabilityProfile,
)

router = APIRouter(prefix="/api/v3/studio", tags=["studio-v3"])

router.include_router(series_router)
router.include_router(router_series_episodes)
router.include_router(router_episode)
router.include_router(router_runs_start)
router.include_router(router_runs)
router.include_router(decisions_router)
router.include_router(router_episode_artifacts)
router.include_router(router_artifact)


@router.get("/capabilities", response_model=RuntimeCapabilityProfile)
async def get_capabilities(
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> RuntimeCapabilityProfile:
    """Typed runtime capability snapshot; fails closed on fake/mock/bypass."""
    return await service.get_capabilities()


@router.get("/readiness", response_model=ReadinessResponse)
async def get_readiness(
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> ReadinessResponse:
    """Readiness summary for desktop boot and certification checks."""
    profile = await service.get_capabilities()
    statuses = {c.name: c.status.value for c in profile.capabilities}
    critical = {name for name, s in statuses.items() if s == CapabilityStatus.UNAVAILABLE.value}
    if not critical:
        overall = "READY"
    elif critical <= {_STORY_ENGINE, _STUDIO_ORCHESTRATION, _WORKER}:
        overall = "DEGRADED"
    else:
        overall = "UNAVAILABLE"
    return ReadinessResponse(
        status=overall,
        capabilities=statuses,
        fail_closed_flags=list(profile.fail_closed_flags),
        certification_mode=profile.certification_mode,
    )


_STORY_ENGINE = "story_engine"
_STUDIO_ORCHESTRATION = "studio_orchestration"
_WORKER = "worker"
