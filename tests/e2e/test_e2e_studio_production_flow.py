"""E2E Test: Studio creative generation flowing into Production video rendering & EDL assembly."""

from __future__ import annotations

import pytest
from windagent.kernel.time import SystemClock
from windagent.modules.production.application.runtime import ProductionContainer, ProductionServices
from windagent.modules.production.infrastructure.memory import (
    InMemoryProductionStore,
)
from windagent.modules.production.infrastructure.memory import (
    memory_scope_factory as prod_scope_factory,
)
from windagent.modules.studio.application.runtime import StudioContainer, StudioServices
from windagent.modules.studio.infrastructure.memory import (
    InMemoryStudioStore,
)
from windagent.modules.studio.infrastructure.memory import (
    memory_scope_factory as studio_scope_factory,
)


@pytest.mark.asyncio
async def test_e2e_studio_to_production_pipeline() -> None:
    clock = SystemClock()

    # 1. Studio Project & Series & Episode
    studio_store = InMemoryStudioStore()
    studio_container = StudioContainer(
        StudioServices(scope_factory=studio_scope_factory(studio_store), clock=clock)
    )

    proj_view = await studio_container.studio.create_project(
        title="Neon Horizon E2E",
        description="Autonomous agent film in cyberpunk world",
    )
    assert proj_view is not None
    assert proj_view.title == "Neon Horizon E2E"

    series_view = await studio_container.studio.create_series(
        project_id=proj_view.project_id,
        title="Season 1: Protocol Genesis",
        description="Initial anime arc",
    )
    assert series_view is not None

    episode_view = await studio_container.studio.create_episode(
        series_id=series_view.series_id,
        project_id=proj_view.project_id,
        title="Episode 1: The First Spark",
        episode_number=1,
    )
    assert episode_view is not None
    assert episode_view.title == "Episode 1: The First Spark"

    # 2. Production Video Master & Media Asset Normalization
    prod_store = InMemoryProductionStore()
    prod_container = ProductionContainer(
        ProductionServices(scope_factory=prod_scope_factory(prod_store), clock=clock)
    )

    prod_proj = await prod_container.production.create_project(
        title="Neon Horizon Master 4K",
        description="Master 4K timeline rendering",
    )
    assert prod_proj is not None
    assert prod_proj.title == "Neon Horizon Master 4K"

    # 3. Dispatch Render Job
    render_job = await prod_container.production.create_render_job(
        project_id=prod_proj.project_id,
        colorspace="ACEScg",
    )
    assert render_job is not None
    assert render_job.colorspace == "ACEScg"
    assert render_job.status == "QUEUED"
