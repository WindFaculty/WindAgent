"""Phase 5 unit tests: database health probes on isolated engines."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from windagent.platform.persistence import (
    check_database_health,
    wait_for_database,
)


@pytest.fixture
async def memory_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    yield engine
    await engine.dispose()


async def test_reachable_database_reports_healthy(memory_engine: AsyncEngine) -> None:
    report = await check_database_health(memory_engine)

    assert report.is_healthy
    assert report.latency_ms is not None
    assert report.latency_ms >= 0.0
    assert report.error is None
    assert report.checked_at.tzinfo is not None


async def test_non_canonical_dialect_reports_reachability_only(memory_engine: AsyncEngine) -> None:
    report = await check_database_health(memory_engine)

    assert report.is_healthy
    assert report.server_version is None
    assert report.database_name is None


async def test_unreachable_database_reports_unhealthy(tmp_path: Path) -> None:
    broken_path = tmp_path / "missing" / "probe.db"
    broken_engine = create_async_engine(f"sqlite+aiosqlite:///{broken_path.as_posix()}")
    try:
        report = await check_database_health(broken_engine)
    finally:
        await broken_engine.dispose()

    assert not report.is_healthy
    assert report.error is not None


async def test_session_target_probe_reuses_the_active_session(memory_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(memory_engine, expire_on_commit=False)
    async with factory() as session:
        report = await check_database_health(session)

    assert report.is_healthy


async def test_wait_for_database_succeeds_immediately_when_healthy(
    memory_engine: AsyncEngine,
) -> None:
    report = await wait_for_database(memory_engine, timeout_s=2.0, interval_s=0.05)

    assert report.is_healthy


async def test_wait_for_database_returns_last_report_on_timeout(tmp_path: Path) -> None:
    broken_path = tmp_path / "missing" / "probe.db"
    broken_engine = create_async_engine(f"sqlite+aiosqlite:///{broken_path.as_posix()}")
    try:
        report = await wait_for_database(broken_engine, timeout_s=0.2, interval_s=0.05)
    finally:
        await broken_engine.dispose()

    assert not report.is_healthy
    assert report.error is not None


async def test_wait_for_database_rejects_non_positive_timeouts(memory_engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        await wait_for_database(memory_engine, timeout_s=0)
    with pytest.raises(ValueError, match="interval_s"):
        await wait_for_database(memory_engine, timeout_s=1.0, interval_s=0)
