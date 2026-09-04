"""Async client test against the app factory (in-process, no network)."""

from __future__ import annotations

import httpx
from windagent.platform.configuration.settings import Settings
from windagent.platform.persistence import Database
from windagent_api.app import create_app

UNREACHABLE_POSTGRES = "postgresql+asyncpg://secret:secret@primary.internal/v2"


async def test_health_endpoint_reports_ok() -> None:
    app = create_app(Settings(environment="test"))
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://v2.test") as client,
    ):
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str)


async def test_readiness_probes_the_database_and_reports_healthy(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database_path = (tmp_path / "ready.db").as_posix()
    database = Database.from_url(
        f"sqlite+aiosqlite:///{database_path}", environment="test"
    )
    app = create_app(
        Settings(environment="test", database_url=f"sqlite+aiosqlite:///{database_path}"),
        database=database,
    )
    transport = httpx.ASGITransport(app=app)
    try:
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://v2.test") as client,
        ):
            response = await client.get("/ready")
    finally:
        await database.dispose()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["environment"] == "test"
    assert body["database"] == "sqlite+aiosqlite"
    assert body["checks"]["database"] == "healthy"


async def test_readiness_fails_closed_when_database_is_unreachable() -> None:
    app = create_app(Settings(environment="test", database_url=UNREACHABLE_POSTGRES))
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://v2.test") as client,
    ):
        response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"] == "unhealthy"
    assert "secret" not in response.text


async def test_readiness_exposes_environment_without_secrets() -> None:
    app = create_app(Settings(environment="test", database_url=UNREACHABLE_POSTGRES))
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://v2.test") as client,
    ):
        response = await client.get("/ready")
    body = response.json()
    assert body["environment"] == "test"
    assert body["database"] == "postgresql+asyncpg"
    assert "secret" not in response.text
