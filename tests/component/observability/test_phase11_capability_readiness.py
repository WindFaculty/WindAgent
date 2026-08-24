"""Unit tests for Phase 11 — Real Capability Readiness Probes."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_observability.health.contracts import (
    HealthStatus,
    HealthProfile,
)
from windagent_observability.health.checker import HealthChecker


@pytest.mark.asyncio
async def test_outbox_publisher_exists_but_not_running_returns_down():
    """If publisher object exists but is_running=False, readiness returns DOWN."""
    mock_publisher = MagicMock()
    mock_publisher.is_running = False

    checker = HealthChecker(
        outbox_publisher=mock_publisher,
        outbox_repository=MagicMock(),
        profile=HealthProfile.DEVELOPMENT,
    )

    status = await checker.check_readiness(profile=HealthProfile.DEVELOPMENT)
    assert status.checks["outbox"].status == HealthStatus.DOWN
    assert "not running" in status.checks["outbox"].message.lower()


@pytest.mark.asyncio
async def test_schema_revision_outdated_returns_down():
    """If schema revision is behind expected head (002_legacy_data), readiness returns DOWN."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("001_initial", 1)
    mock_session.execute.return_value = mock_result

    class MockSessionFactory:
        def __call__(self):
            return self
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    checker = HealthChecker(
        db_session_factory=MockSessionFactory(),
        profile=HealthProfile.DEVELOPMENT,
    )

    status = await checker.check_readiness(profile=HealthProfile.DEVELOPMENT)
    assert status.checks["schema_migration"].status == HealthStatus.DOWN
    assert "001_initial" in status.checks["schema_migration"].message
    assert "002_legacy_data" in status.checks["schema_migration"].message


@pytest.mark.asyncio
async def test_schema_revision_head_verified_returns_up():
    """If schema revision matches expected head (002_legacy_data), readiness returns UP."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("002_legacy_data", 2)
    mock_session.execute.return_value = mock_result

    class MockSessionFactory:
        def __call__(self):
            return self
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    checker = HealthChecker(
        db_session_factory=MockSessionFactory(),
        profile=HealthProfile.DEVELOPMENT,
    )

    result = await checker._check_schema_migration()
    assert result.status == HealthStatus.UP
    assert "002_legacy_data" in result.message


@pytest.mark.asyncio
async def test_worker_unavailable_in_production_returns_down():
    """In PRODUCTION profile, if worker query reports unavailable, readiness returns DOWN."""
    mock_worker_query = AsyncMock()
    mock_status = MagicMock()
    mock_status.available = False
    mock_status.active_workers = 0
    mock_status.active_leases = 0
    mock_worker_query.get_status.return_value = mock_status

    checker = HealthChecker(
        worker_status_query=mock_worker_query,
        profile=HealthProfile.PRODUCTION,
    )

    status = await checker.check_readiness(profile=HealthProfile.PRODUCTION)
    assert status.checks["worker"].status == HealthStatus.DOWN
