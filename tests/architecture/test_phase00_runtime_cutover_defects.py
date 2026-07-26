"""Regression gates for the Architecture V2 runtime cutover defects."""

from __future__ import annotations

import inspect
import sys
import subprocess
from pathlib import Path

import pytest

from windagent_api.composition import ApplicationContainer
from windagent_plugins.registry import PluginRegistry
from windagent_skills.registry import SkillRegistry
from windagent_observability.health.checker import HealthChecker, HealthProfile, HealthStatus

ROOT = Path(__file__).resolve().parents[2]


def test_api_does_not_compose_worker_orchestration_container():
    """The API process must not own the Worker orchestration container."""
    container = ApplicationContainer()
    assert not hasattr(container, "orchestration_container")


@pytest.mark.asyncio
async def test_api_shutdown_plugin_registry_close_is_idempotent():
    registry = PluginRegistry()
    await registry.close()
    await registry.close()


@pytest.mark.asyncio
async def test_api_shutdown_skill_registry_close_is_idempotent():
    registry = SkillRegistry()
    await registry.close()
    await registry.close()


def test_worker_composition_imports_canonical_pipeline():
    from windagent_worker.composition import WorkerContainer

    assert WorkerContainer.__module__ == "windagent_worker.composition"


def test_api_does_not_compose_outbox_repository_or_publisher():
    container = ApplicationContainer(db_url="sqlite+aiosqlite:///:memory:")
    assert not hasattr(container, "outbox_publisher")


def test_worker_composition_owns_outbox_publisher():
    from windagent_worker.composition import WorkerContainer

    container = WorkerContainer(db_url="sqlite+aiosqlite:///:memory:")
    assert hasattr(container, "outbox_publisher")


def test_migration_002_stages_overlapping_legacy_tables():
    from windagent_storage.migrations.v2_canonical.migration_002_legacy_data import upgrade

    source = inspect.getsource(upgrade)
    assert "legacy_chat_sessions_snapshot" in source
    assert "legacy_execution_events_snapshot" in source


@pytest.mark.asyncio
async def test_production_health_requires_outbox_repository():
    checker = HealthChecker(profile=HealthProfile.PRODUCTION, db_session_factory=None, outbox_repository=None)
    result = await checker._check_outbox_publisher()
    assert result.status == HealthStatus.DOWN


def test_architecture_checker_passes_cutover_policy():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_architecture_imports.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Architecture policy: PASS" in proc.stdout
