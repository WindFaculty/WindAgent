"""Database health probes for readiness endpoints and bootstrap flows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Literal, Self

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from windagent.kernel.time import normalize_utc, utc_now

type HealthStatus = Literal["healthy", "unhealthy"]


@dataclass(frozen=True, slots=True)
class DatabaseHealthReport:
    """Outcome of one database probe.

    ``server_version`` and ``database_name`` are only populated for the
    canonical engine; other dialects report reachability and latency only.
    """

    status: HealthStatus
    checked_at: datetime
    latency_ms: float | None = None
    server_version: str | None = None
    database_name: str | None = None
    error: str | None = None

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"

    @classmethod
    def healthy(
        cls,
        *,
        latency_ms: float,
        server_version: str | None = None,
        database_name: str | None = None,
        checked_at: datetime | None = None,
    ) -> Self:
        return cls(
            status="healthy",
            checked_at=normalize_utc(checked_at) if checked_at else utc_now(),
            latency_ms=latency_ms,
            server_version=server_version,
            database_name=database_name,
        )

    @classmethod
    def unhealthy(cls, *, error: str, checked_at: datetime | None = None) -> Self:
        return cls(
            status="unhealthy",
            checked_at=normalize_utc(checked_at) if checked_at else utc_now(),
            error=error,
        )


async def check_database_health(
    target: AsyncEngine | AsyncConnection | AsyncSession,
) -> DatabaseHealthReport:
    """Probe the database once and classify it healthy or unhealthy.

    The probe never raises: failures are reported as an unhealthy outcome so
    readiness endpoints and bootstrap loops can consume the result directly.
    """
    try:
        if isinstance(target, AsyncEngine):
            async with target.connect() as connection:
                return await _probe(connection)
        if isinstance(target, AsyncConnection):
            return await _probe(target)
        return await _probe(await target.connection())
    except Exception as exc:  # noqa: BLE001 - a probe classifies, never raises
        return DatabaseHealthReport.unhealthy(error=f"{type(exc).__name__}: {exc}")


async def wait_for_database(
    target: AsyncEngine | AsyncConnection | AsyncSession,
    *,
    timeout_s: float = 30.0,
    interval_s: float = 0.25,
) -> DatabaseHealthReport:
    """Probe repeatedly until healthy or ``timeout_s`` has elapsed.

    Returns the last report on timeout so callers can log the precise
    bootstrap failure.
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")

    deadline = perf_counter() + timeout_s
    report = await check_database_health(target)
    while not report.is_healthy and perf_counter() < deadline:
        remaining = deadline - perf_counter()
        await asyncio.sleep(max(0.0, min(interval_s, remaining)))
        report = await check_database_health(target)
    return report


async def _probe(connection: AsyncConnection) -> DatabaseHealthReport:
    started = perf_counter()
    await connection.execute(text("SELECT 1"))
    latency_ms = (perf_counter() - started) * 1000.0

    server_version: str | None = None
    database_name: str | None = None
    if connection.dialect.name == "postgresql":
        row = (await connection.execute(text("SELECT version(), current_database()"))).one()
        server_version = str(row[0])
        database_name = str(row[1])

    return DatabaseHealthReport.healthy(
        latency_ms=latency_ms,
        server_version=server_version,
        database_name=database_name,
    )
