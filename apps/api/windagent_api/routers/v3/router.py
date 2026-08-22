"""
Canonical V3 Root Router Aggregator.

Consolidates all modular V3 domain subrouters into a single root V3 router
mounted in main.py.
"""

from fastapi import APIRouter
from windagent_api.routers.v3.studio.aggregator import router as v3_studio_router
from windagent_api.routers.v3.system import router as v3_system_router, ws_router as v3_system_ws_router
from windagent_api.routers.v3.dashboard import router as v3_dashboard_router
from windagent_api.routers.v3.monitoring import router as v3_monitoring_router
from windagent_api.routers.v3.projects import router as v3_projects_router
from windagent_api.routers.v3.project_templates import router as v3_project_templates_router
from windagent_api.routers.v3.episodes import router as v3_episodes_router, ws_router as v3_episodes_ws_router

# Phase 9 — Story Production Domain
from windagent_api.routers.v3.characters import router as v3_characters_router
from windagent_api.routers.v3.world import router as v3_world_router, sync_router as v3_world_sync_router
from windagent_api.routers.v3.storyboard import router as v3_storyboard_router, ws_router as v3_storyboard_ws_router
from windagent_api.routers.v3.reviews import router as v3_reviews_router
from windagent_api.routers.v3.assets import router as v3_assets_router

# Phase 10 — Production Cutover Domain
from windagent_api.routers.v3.production import router as v3_production_router, ws_router as v3_production_ws_router

# Phase 11 — Agent System Convergence Domain
from windagent_api.routers.v3.agent_definitions import router as v3_agent_definitions_router
from windagent_api.routers.v3.agent_instances import router as v3_agent_instances_router
from windagent_api.routers.v3.conversations import router as v3_conversations_router
from windagent_api.routers.v3.tasks import router as v3_tasks_router
from windagent_api.routers.v3.workflows import router as v3_workflows_router, ws_router as v3_agent_system_ws_router

# Phase 12 — Models, Providers & Routing Infrastructure Domain
from windagent_api.routers.v3.models import router as v3_models_router
from windagent_api.routers.v3.providers import router as v3_providers_router
from windagent_api.routers.v3.routing import router as v3_routing_router, ws_router as v3_model_infra_ws_router

# Phase 13 — Platform & Administration Domain
from windagent_api.routers.v3.browser import router as v3_browser_router, ws_router as v3_browser_ws_router
from windagent_api.routers.v3.files import router as v3_files_router
from windagent_api.routers.v3.memory import router as v3_memory_router
from windagent_api.routers.v3.logs import router as v3_logs_router, ws_router as v3_logs_ws_router
from windagent_api.routers.v3.settings import router as v3_settings_router

v3_router = APIRouter()

# Include Modular V3 Subrouters
v3_router.include_router(v3_studio_router)
v3_router.include_router(v3_system_router)
v3_router.include_router(v3_system_ws_router)
v3_router.include_router(v3_dashboard_router)
v3_router.include_router(v3_monitoring_router)
v3_router.include_router(v3_projects_router)
v3_router.include_router(v3_project_templates_router)
v3_router.include_router(v3_episodes_router)
v3_router.include_router(v3_episodes_ws_router)

# Phase 9 — Story Production Domain routers
v3_router.include_router(v3_characters_router)
v3_router.include_router(v3_world_router)
v3_router.include_router(v3_world_sync_router)
v3_router.include_router(v3_storyboard_router)
v3_router.include_router(v3_storyboard_ws_router)
v3_router.include_router(v3_reviews_router)
v3_router.include_router(v3_assets_router)

# Phase 10 — Production Cutover Domain routers
v3_router.include_router(v3_production_router)
v3_router.include_router(v3_production_ws_router)

# Phase 11 — Agent System Convergence Domain routers
v3_router.include_router(v3_agent_definitions_router)
v3_router.include_router(v3_agent_instances_router)
v3_router.include_router(v3_conversations_router)
v3_router.include_router(v3_tasks_router)
v3_router.include_router(v3_workflows_router)
v3_router.include_router(v3_agent_system_ws_router)

# Phase 12 — Models, Providers & Routing Infrastructure Domain routers
v3_router.include_router(v3_models_router)
v3_router.include_router(v3_providers_router)
v3_router.include_router(v3_routing_router)
v3_router.include_router(v3_model_infra_ws_router)

# Phase 13 — Platform & Administration Domain routers
v3_router.include_router(v3_browser_router)
v3_router.include_router(v3_browser_ws_router)
v3_router.include_router(v3_files_router)
v3_router.include_router(v3_memory_router)
v3_router.include_router(v3_logs_router)
v3_router.include_router(v3_logs_ws_router)
v3_router.include_router(v3_settings_router)

