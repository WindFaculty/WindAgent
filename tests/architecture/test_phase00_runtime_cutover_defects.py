"""Phase 0 Reproduction Test Suite for Architecture V2 Runtime Cutover.

This module contains focused reproduction tests for all P0 runtime defects
identified at starting commit 5b26ed67e5550b97b86b83a21c836ff96bd049a6.

ALL tests in this file pass by confirming that the expected baseline defect / failure occurs.
"""

from __future__ import annotations

import sys
import subprocess
import pytest

from windagent_api.composition import ApplicationContainer
from windagent_plugins.registry import PluginRegistry
from windagent_skills.registry import SkillRegistry
from windagent_observability.health.checker import HealthChecker, HealthProfile, HealthStatus


@pytest.mark.asyncio
async def test_reproduce_api_lifespan_missing_orchestration_container():
    """P0 Defect 1: API lifespan accesses non-existent container.orchestration_container."""
    container = ApplicationContainer()
    with pytest.raises(AttributeError, match="orchestration_container"):
        _ = container.orchestration_container


@pytest.mark.asyncio
async def test_reproduce_api_shutdown_plugin_registry_no_close():
    """P0 Defect 2: ApplicationContainer shutdown fails on PluginRegistry.close()."""
    registry = PluginRegistry()
    with pytest.raises(AttributeError, match="close"):
        await registry.close()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reproduce_api_shutdown_skill_registry_no_close():
    """P0 Defect 3: ApplicationContainer shutdown fails on SkillRegistry.close()."""
    registry = SkillRegistry()
    with pytest.raises(AttributeError, match="close"):
        await registry.close()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reproduce_worker_broken_composition_import():
    """P0 Defect 4: Worker composition imports non-existent module windagent_intelligence.pipeline."""
    with pytest.raises(ModuleNotFoundError, match="windagent_intelligence.pipeline"):
        from windagent_worker.composition import WorkerContainer


@pytest.mark.asyncio
async def test_reproduce_outbox_repository_session_factory_mismatch():
    """P0 Defect 5: SqlOutboxRepository initialized with session factory rather than AsyncSession."""
    container = ApplicationContainer(db_url="sqlite+aiosqlite:///:memory:")
    await container.bootstrap()
    try:
        # container.outbox_publisher wraps SqlOutboxRepository initialized with session_factory
        repo = container.outbox_publisher._outbox_repo
        # Calling method on repo raises AttributeError because self._session is session_factory
        with pytest.raises(AttributeError, match="execute"):
            await repo.get_pending(limit=10)
    finally:
        if container.db:
            await container.db.close()


@pytest.mark.asyncio
async def test_reproduce_outbox_publisher_not_started_in_api():
    """P0 Defect 6: API bootstrap initializes OutboxEventPublisher but does not start its background loop."""
    container = ApplicationContainer(db_url="sqlite+aiosqlite:///:memory:")
    await container.bootstrap()
    try:
        assert container.outbox_publisher is not None
        assert getattr(container.outbox_publisher, "_running", False) is False
    finally:
        if container.db:
            await container.db.close()


@pytest.mark.asyncio
async def test_reproduce_migration_002_self_copy_table_conflict():
    """P0 Defect 7: Migration 002 attempts self-read and self-write on same chat_sessions table."""
    try:
        from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import MIGRATION_DESCRIPTION
        assert "- chat_sessions (backend) -> chat_sessions (V2 storage)" in MIGRATION_DESCRIPTION
        assert "- execution_events (backend) -> execution_events (V2 storage)" in MIGRATION_DESCRIPTION
    except ModuleNotFoundError as err:
        # Baseline defect in storage.windagent_storage import inside migrations __init__.py
        assert "storage" in str(err) or "windagent_storage" in str(err)


@pytest.mark.asyncio
async def test_reproduce_health_outbox_not_required():
    """P0 Defect 8: HealthChecker returns NOT_REQUIRED for outbox repository when missing."""
    checker = HealthChecker(profile=HealthProfile.PRODUCTION, db_session_factory=None, outbox_repository=None)
    result = await checker._check_outbox_publisher()
    # Baseline defect: returns NOT_REQUIRED instead of DOWN
    assert result.status == HealthStatus.NOT_REQUIRED


@pytest.mark.asyncio
async def test_reproduce_architecture_checker_violations():
    """P0 Defect 9: Architecture checker detects 32 dependency policy violations."""
    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "Architecture policy: FAIL (32 violations)" in proc.stdout
