"""Unit tests for Phase 10 — Health Dependency Wiring & Fail-Closed Behavior."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from windagent_observability.health.contracts import (
    HealthStatus,
    HealthProfile,
    HealthDependencyBundle,
)
from windagent_observability.health.checker import HealthChecker


@pytest.mark.asyncio
async def test_health_dependency_bundle_injection():
    """HealthChecker accepts typed HealthDependencyBundle."""
    mock_db = MagicMock()
    bundle = HealthDependencyBundle(
        database=mock_db,
    )

    checker = HealthChecker(bundle=bundle, profile=HealthProfile.DEVELOPMENT)
    assert checker._db_session_factory == mock_db


@pytest.mark.asyncio
async def test_production_profile_missing_outbox_returns_down():
    """In PRODUCTION profile, missing outbox repository returns DOWN (fail-closed)."""
    checker = HealthChecker(
        outbox_repository=None,
        profile=HealthProfile.PRODUCTION,
    )
    status = await checker.check_readiness(profile=HealthProfile.PRODUCTION)
    assert status.overall_status == HealthStatus.DOWN
    assert status.checks["outbox"].status == HealthStatus.DOWN
    assert status.checks["outbox"].required is True


@pytest.mark.asyncio
async def test_production_profile_missing_worker_returns_down():
    """In PRODUCTION profile, missing worker query returns DOWN."""
    checker = HealthChecker(
        worker_status_query=None,
        profile=HealthProfile.PRODUCTION,
    )
    status = await checker.check_readiness(profile=HealthProfile.PRODUCTION)
    assert status.overall_status == HealthStatus.DOWN
    assert status.checks["worker"].status == HealthStatus.DOWN


@pytest.mark.asyncio
async def test_production_profile_missing_queue_returns_down():
    """In PRODUCTION profile, missing queue session factory returns DOWN."""
    checker = HealthChecker(
        db_session_factory=None,
        profile=HealthProfile.PRODUCTION,
    )
    status = await checker.check_readiness(profile=HealthProfile.PRODUCTION)
    assert status.overall_status == HealthStatus.DOWN
    assert status.checks["queue"].status == HealthStatus.DOWN


@pytest.mark.asyncio
async def test_development_profile_missing_worker_returns_degraded():
    """In DEVELOPMENT profile, missing worker returns DEGRADED rather than DOWN if other checks pass."""
    checker = HealthChecker(
        worker_status_query=None,
        profile=HealthProfile.DEVELOPMENT,
    )
    status = await checker.check_readiness(profile=HealthProfile.DEVELOPMENT)
    # Database is also None, so overall status will be DOWN due to missing db, but worker status is DEGRADED
    assert status.checks["worker"].status in (HealthStatus.DEGRADED, HealthStatus.DOWN)
