"""Phase 9 contracts: per-client rate limiting at the transport."""

from __future__ import annotations

import httpx
from windagent.platform.configuration.settings import Settings
from windagent.platform.security import SlidingWindowRateLimiter
from windagent_api.app import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _app(limit: int):  # type: ignore[no-untyped-def]
    return create_app(
        Settings(environment="test", database_url=TEST_DATABASE_URL),
        rate_limiter=SlidingWindowRateLimiter(limit=limit, window_s=60.0),
    )


async def test_exhausted_clients_receive_429_with_retry_after() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(limit=2)), base_url="http://v2.test"
    ) as client:
        first = await client.get("/health")
        second = await client.get("/health")
        third = await client.get("/health")

    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.headers["x-ratelimit-remaining"] == "0"

    assert third.status_code == 429
    body = third.json()
    assert body["error"]["code"] == "rate_limited"
    retry_after = int(third.headers["retry-after"])
    assert 1 <= retry_after <= 60


async def test_without_a_limiter_requests_are_unbounded() -> None:
    app = create_app(Settings(environment="test", database_url=TEST_DATABASE_URL))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://v2.test"
    ) as client:
        for _ in range(5):
            response = await client.get("/health")
            assert response.status_code == 200
            assert "x-ratelimit-limit" not in response.headers
