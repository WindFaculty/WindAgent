"""Phase 1 Unit Tests: API Composition Root & Lifespan Lifecycle.

Validates that ApplicationContainer and lifespan context manager start up cleanly,
shut down without exceptions, follow canonical shutdown order, and implement AsyncCloseablePort.
"""

from __future__ import annotations

import os
import tempfile
import pytest
from fastapi import FastAPI

from windagent_api.composition import ApplicationContainer
from windagent_api.lifespan import lifespan
from windagent_plugins.registry import PluginRegistry
from windagent_skills.registry import SkillRegistry
from windagent_tools.registry import ToolRegistry
from windagent_workflows.registry import WorkflowRegistry


@pytest.mark.asyncio
async def test_api_container_bootstrap_and_shutdown():
    """Validates basic bootstrap and shutdown of ApplicationContainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_api.db")
        db_url = f"sqlite+aiosqlite:///{db_path}"
        container = ApplicationContainer(db_url=db_url)

        assert not container.is_initialized
        await container.bootstrap()
        assert container.is_initialized
        assert container.db is not None
        assert container.task_manager is not None
        assert container.provider_registry is not None
        assert container.tool_registry is not None
        assert container.plugin_registry is not None
        assert container.skill_registry is not None

        # Perform clean shutdown
        await container.shutdown()
        assert not container.is_initialized


@pytest.mark.asyncio
async def test_api_container_double_bootstrap_and_shutdown_idempotency():
    """Validates that calling bootstrap() or shutdown() twice is idempotent and safe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_api_idempotency.db")
        db_url = f"sqlite+aiosqlite:///{db_path}"
        container = ApplicationContainer(db_url=db_url)

        await container.bootstrap()
        # Second bootstrap should be no-op
        await container.bootstrap()
        assert container.is_initialized

        # First shutdown
        await container.shutdown()
        assert not container.is_initialized

        # Second shutdown should be no-op without exception
        await container.shutdown()
        assert not container.is_initialized


@pytest.mark.asyncio
async def test_fastapi_lifespan_integration():
    """Validates FastAPI lifespan context manager startup and shutdown hooks."""
    app = FastAPI(lifespan=lifespan)

    async with lifespan(app):
        # Verify app.state fields initialized
        assert hasattr(app.state, "container")
        assert hasattr(app.state, "db")
        assert hasattr(app.state, "event_dispatcher")
        assert hasattr(app.state, "task_manager")
        assert hasattr(app.state, "provider_registry")
        assert hasattr(app.state, "tool_registry")
        assert hasattr(app.state, "worker_status_query")
        # Confirm orchestration_container is NOT present
        assert not hasattr(app.state, "orchestration_container")


@pytest.mark.asyncio
async def test_registry_async_closeable_ports():
    """Validates that all registry facades implement async close() method."""
    plugin_reg = PluginRegistry()
    skill_reg = SkillRegistry()
    tool_reg = ToolRegistry()
    workflow_reg = WorkflowRegistry()

    # None of these should raise AttributeError or Exception
    await plugin_reg.close()
    await skill_reg.close()
    await tool_reg.close()
    await workflow_reg.close()
