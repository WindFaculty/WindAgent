"""Phase 9 contracts: policy-engine authorization with durable audit."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from windagent.kernel.ids import ActorId
from windagent.platform.configuration.settings import Settings
from windagent.platform.modules import ModuleManifest
from windagent.platform.security import (
    TOKEN_KEY_SECRET_NAME,
    HmacTokenAuthenticator,
    HmacTokenIssuer,
    Identity,
    IdentityKind,
    InMemoryAuditSink,
    InMemoryIdentityStore,
    InMemorySecretStore,
    PolicyDecision,
    PolicyEffect,
    PolicyRule,
    RuleBasedPolicyEngine,
    SecretValue,
)
from windagent_api.app import create_app
from windagent_api.auth import require_policy

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class _Security:
    def __init__(self) -> None:
        self.secrets = InMemorySecretStore()
        self.secrets.put(TOKEN_KEY_SECRET_NAME, SecretValue("authz-key"))
        self.identities = InMemoryIdentityStore()
        self.identity = Identity(
            actor_id=ActorId.new(), kind=IdentityKind.USER, name="ana"
        )
        self.identities.put(self.identity)
        self.issuer = HmacTokenIssuer(self.secrets, ttl_s=300.0)
        self.authenticator = HmacTokenAuthenticator(self.secrets, self.identities)

    async def token(self) -> str:
        return await self.issuer.issue(self.identity.actor_id)


def _guarded_router() -> APIRouter:
    router = APIRouter()
    guard = require_policy("episode:write", "episode")

    @router.post("/guarded")
    async def guarded(
        request: Request,
        decision: PolicyDecision = Depends(guard),
    ) -> JSONResponse:
        return JSONResponse(
            {"effect": decision.effect.value, "policy_id": decision.policy_id}
        )

    return router


def _app(
    security: _Security,
    rules: tuple[PolicyRule, ...],
    audit_sink: InMemoryAuditSink,
) -> FastAPI:
    return create_app(
        Settings(environment="test", database_url=TEST_DATABASE_URL),
        manifests=(
            ModuleManifest(
                id="test.guarded", version="0", routers=(_guarded_router(),)
            ),
        ),
        authenticator=security.authenticator,
        policy_engine=RuleBasedPolicyEngine(rules=rules),
        audit_sink=audit_sink,
    )


async def _post_guarded(app: FastAPI, security: _Security) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://v2.test"
    ) as client:
        return await client.post(
            "/api/v4/guarded",
            headers={"Authorization": f"Bearer {await security.token()}"},
        )


async def test_denied_operations_return_403_and_are_audited() -> None:
    security = _Security()
    audit = InMemoryAuditSink()
    app = _app(security, rules=(), audit_sink=audit)
    response = await _post_guarded(app, security)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["context"]["policy_id"] == "default-deny"
    assert len(audit.events) == 1
    assert audit.events[0].outcome == "deny"
    assert audit.events[0].action == "episode:write"
    assert audit.events[0].trace_id == response.headers["x-trace-id"]
    assert str(audit.events[0].correlation_id) == response.headers[
        "x-correlation-id"
    ]
    assert audit.events[0].actor_id == security.identity.actor_id


async def test_allowed_operations_run_and_are_audited() -> None:
    security = _Security()
    audit = InMemoryAuditSink()
    app = _app(
        security,
        rules=(
            PolicyRule(
                policy_id="writers",
                action="episode:write",
                resource_type="episode",
                effect=PolicyEffect.ALLOW,
            ),
        ),
        audit_sink=audit,
    )
    response = await _post_guarded(app, security)
    assert response.status_code == 200
    body = response.json()
    assert body == {"effect": "allow", "policy_id": "writers"}
    assert audit.events[0].outcome == "allow"


async def test_require_approval_is_never_executed() -> None:
    security = _Security()
    audit = InMemoryAuditSink()
    app = _app(
        security,
        rules=(
            PolicyRule(
                policy_id="approval-gate",
                action="episode:write",
                resource_type="episode",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                reason="needs a human",
            ),
        ),
        audit_sink=audit,
    )
    response = await _post_guarded(app, security)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "require_approval"
    assert body["error"]["message"] == "needs a human"
    assert audit.events[0].outcome == "require_approval"
