"""Live Record V3 routers (ban_ke_hoach_v1.md Phase 1-5)."""

from fastapi import APIRouter

from windagent_api.routers.v3.live_record.actions import router as actions_router
from windagent_api.routers.v3.live_record.plans import router as plans_router
from windagent_api.routers.v3.live_record.preparations import router as preparations_router
from windagent_api.routers.v3.live_record.sessions import router as sessions_router
from windagent_api.routers.v3.live_record.takes import router as takes_router

router = APIRouter(tags=["live-record"])
router.include_router(actions_router)
router.include_router(plans_router)
router.include_router(preparations_router)
router.include_router(sessions_router)
router.include_router(takes_router)

__all__ = ["router"]
