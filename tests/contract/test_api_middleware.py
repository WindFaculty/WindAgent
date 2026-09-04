"""Request identity middleware contracts."""

from __future__ import annotations

import httpx
from windagent.platform.configuration.settings import Settings
from windagent_api.app import create_app


def _client() -> httpx.AsyncClient:
    app = create_app(Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"))
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://v2.test"
    )


async def test_every_response_carries_a_request_id() -> None:
    async with _client() as client:
        response = await client.get("/health")
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    int(request_id, 16)


async def test_incoming_request_ids_are_honored_verbatim() -> None:
    async with _client() as client:
        response = await client.get("/health", headers={"x-request-id": "my-trace-42"})
    assert response.headers["x-request-id"] == "my-trace-42"


async def test_invalid_correlation_headers_are_ignored_not_fatal() -> None:
    async with _client() as client:
        response = await client.get(
            "/health",
            headers={
                "x-correlation-id": "not-a-uuid",
                "x-causation-id": "not-a-uuid",
            },
        )
    assert response.status_code == 200


async def test_valid_correlation_headers_are_accepted() -> None:
    from uuid import uuid4

    correlation = str(uuid4())
    causation = str(uuid4())
    async with _client() as client:
        response = await client.get(
            "/health",
            headers={"x-correlation-id": correlation, "x-causation-id": causation},
        )
    assert response.status_code == 200
