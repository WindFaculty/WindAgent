"""Phase 9 contracts: bearer authentication enforced at the transport."""

from __future__ import annotations

import httpx
from windagent.kernel.ids import ActorId
from windagent.platform.configuration.settings import Settings
from windagent.platform.security import (
    TOKEN_KEY_SECRET_NAME,
    HmacTokenAuthenticator,
    HmacTokenIssuer,
    Identity,
    IdentityKind,
    InMemoryAuditSink,
    InMemoryIdentityStore,
    InMemorySecretStore,
    SecretValue,
)
from windagent_api.app import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class Stack:
    def __init__(self) -> None:
        self.secrets = InMemorySecretStore()
        self.secrets.put(TOKEN_KEY_SECRET_NAME, SecretValue("contract-key"))
        self.identities = InMemoryIdentityStore()
        self.identity = Identity(
            actor_id=ActorId.new(), kind=IdentityKind.USER, name="ana"
        )
        self.identities.put(self.identity)
        self.issuer = HmacTokenIssuer(self.secrets, ttl_s=300.0)
        self.authenticator = HmacTokenAuthenticator(self.secrets, self.identities)

    async def token(self) -> str:
        return await self.issuer.issue(self.identity.actor_id)


class StubQueue:
    """Functional DurableJobQueue stand-in for the debug surface."""

    def __init__(self) -> None:
        self._accepted = 0

    async def submit(self, job: object) -> object:
        self._accepted += 1
        from windagent.kernel.ids import EntityId
        from windagent.platform.jobs import JobReceipt

        return JobReceipt(EntityId.new())

    async def get(self, job_id: object) -> object:  # pragma: no cover
        return None

    async def request_cancel(self, job_id: object) -> bool:  # pragma: no cover
        return False


def _app(stack: Stack | None = None, *, with_queue: bool = False):  # type: ignore[no-untyped-def]
    from typing import cast

    from windagent.platform.jobs import DurableJobQueue

    return create_app(
        Settings(environment="test", database_url=TEST_DATABASE_URL),
        audit_sink=InMemoryAuditSink(),
        authenticator=stack.authenticator if stack is not None else None,
        job_queue=cast(DurableJobQueue, StubQueue()) if with_queue else None,
    )


async def test_unauthenticated_requests_fail_closed() -> None:
    stack = Stack()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(stack)), base_url="http://v2.test"
    ) as client:
        for headers in (
            {},
            {"Authorization": "Basic dXNlcjpwYXNz"},
            {"Authorization": "Bearer not-a-real-token"},
        ):
            response = await client.get("/api/v4/system/info", headers=headers)
            assert response.status_code == 401
            body = response.json()
            assert body["error"]["code"] == "unauthorized"
            assert response.headers["www-authenticate"] == "Bearer"


async def test_health_probes_stay_public() -> None:
    stack = Stack()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(stack)), base_url="http://v2.test"
    ) as client:
        health = await client.get("/health")
        ready = await client.get("/ready")
    assert health.status_code == 200
    assert ready.status_code == 200


async def test_valid_bearer_tokens_reach_the_routes() -> None:
    stack = Stack()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(stack)), base_url="http://v2.test"
    ) as client:
        response = await client.get(
            "/api/v4/system/info",
            headers={"Authorization": f"Bearer {await stack.token()}"},
        )
    assert response.status_code == 200
    assert response.json()["api_version"] == "v4"


async def test_debug_surface_requires_authentication_too() -> None:
    stack = Stack()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(stack, with_queue=True)),
        base_url="http://v2.test",
    ) as client:
        denied = await client.post(
            "/debug/jobs", json={"job_type": "debug.echo", "payload": {}}
        )
        allowed = await client.post(
            "/debug/jobs",
            json={"job_type": "debug.echo", "payload": {}},
            headers={"Authorization": f"Bearer {await stack.token()}"},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 202


async def test_without_authenticator_the_api_stays_open() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()), base_url="http://v2.test"
    ) as client:
        response = await client.get("/api/v4/system/info")
    assert response.status_code == 200
