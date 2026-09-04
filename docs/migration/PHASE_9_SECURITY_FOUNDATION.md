# Phase 9 — Security foundation

Date: 2026-09-02

## Scope delivered

Every element of plan section 13 exists as a contract + implementation pair
before any feature migration:

| Element          | Contract / implementation                                                        |
| ---------------- | -------------------------------------------------------------------------------- |
| Identity         | `Identity`, `IdentityStore`, `InMemoryIdentityStore`                             |
| Authentication   | `Authenticator` protocol, `HmacTokenAuthenticator` + `HmacTokenIssuer` (stdlib)  |
| Authorization    | `PolicyRule`, `RuleBasedPolicyEngine` (fail-closed `default-deny`)               |
| Policy Engine    | `PolicyEffect` ALLOW/DENY/REQUIRE_APPROVAL (Phase 3 contracts, now enforced)     |
| Secret Store     | `InMemorySecretStore`, `EnvironmentSecretStore` (`WINDAGENT_SECRET_<NAME>`)      |
| Audit            | `AuditEvent`, `AuditSink`, `InMemoryAuditSink`, durable `OutboxAuditSink`        |
| Rate limit       | `RateLimiter`, `SlidingWindowRateLimiter` (bounded, monotonic clock)             |

Key decisions are recorded in ADR-0005 (fail-closed defaults, HMAC bearer
tokens with no new dependency, middleware-level enforcement, durable audit
through the Phase 6 outbox, `REQUIRE_APPROVAL` never executed over HTTP).

## Transport enforcement (`apps/api`)

```text
request → RateLimitMiddleware (429 + Retry-After)
        → AuthenticationMiddleware (401 envelope + WWW-Authenticate)
        → RequestContextMiddleware (request/correlation/causation ids)
        → route (Depends(require_policy(action, resource)))
              ├─ ALLOW            → route runs, decision injected
              ├─ DENY             → 403 forbidden + policy_id
              ├─ REQUIRE_APPROVAL → 403 require_approval
              └─ every decision   → audit event → outbox (durable)
```

- Public paths: `/health`, `/ready`, `/docs`, `/redoc`, `/openapi.json`.
- `Settings.auth_enabled` composes the default stack (environment secret
  store, empty identity store, empty rule engine — nobody passes until
  identities and rules are provisioned).  All collaborators remain
  injectable for tests and alternative deployments.
- `Settings.rate_limit_per_minute > 0` enables the limiter.
- Known documented gap: the debug websocket is not authenticated yet.

## Durable audit

`OutboxAuditSink` turns each `AuditEvent` into a
`security.audit.recorded` event recorded in its own unit-of-work with
`deduplication_key="audit:<event_id>"`, so audit trails inherit outbox
durability, idempotency, and publisher delivery.  Payload is the JSON-safe
`AuditEvent.to_dict()` (actor, action, resource, outcome, reason,
policy_id, occurred_at).

## Gates

Current local evidence:

```text
targeted Phase 9 suite       PASS
full regression              PASS (268 passed: unit, architecture,
                             contract, parity, e2e, PostgreSQL
                             integration)
Ruff                         PASS
mypy strict                  PASS (165 source files)
```

New coverage: identity validation/store, token issue+verify round-trip,
expired/tampered/unknown/inactive rejections, missing-key configuration
errors, rule matching/priority/wildcards/fail-closed, secret store
round-trips and redaction, sliding-window behavior (slide, isolation,
eviction, bounded memory), 401/403/429 canonical envelopes, audit records
for every policy decision, and outbox-backed audit durability/idempotency.
