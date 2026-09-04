# ADR-0005: Security foundation — verified bearer auth, fail-closed policy, durable audit

- Status: Accepted
- Date: 2026-09-02
- Phase: 9 (security foundation)

## Context

Plan section 13 requires Identity, Authentication, Authorization, Policy
Engine, Secret Store, Audit, and Rate limiting to exist **before any feature
module migrates**.  The Phase 3 `platform.security` contracts
(`PolicyEngine`, `SecretStore`, `PolicyDecision` with
`ALLOW/DENY/REQUIRE_APPROVAL`) already existed; Phase 9 adds the
implementations and the HTTP enforcement.

## Decisions

1. **Fail-closed everywhere.**  `RuleBasedPolicyEngine` returns DENY when no
   rule matches (`policy_id="default-deny"`), and an authentication-enabled
   app without explicit rules denies everything.  Authorization is only open
   when no engine is configured at all — a state the composition root may
   enter solely for unsecured local development (`WINDAGENT_AUTH_ENABLED`
   unset).
2. **HMAC-signed bearer tokens (stdlib only).**  Tokens are
   `wa1.<payload>.<hmac_sha256>`, verified in constant time against a key
   held in the `SecretStore` (`auth/token_key`), checked for expiry against
   the kernel clock, and resolved to an **active** identity.  A JWT library
   can replace the codec behind the same `Authenticator` protocol; until an
   external identity provider is a requirement, no new crypto dependency is
   added.  A missing signing key is a `TokenConfigurationError` (server
   error), never a 401.
3. **Authentication is middleware, not per-route.**  When an authenticator
   is composed, every path except `/health`, `/ready`, `/docs`, `/redoc`,
   `/openapi.json` requires `Authorization: Bearer`.  Routes cannot forget
   to opt in.  Known gap (documented, deliberate): the debug websocket is
   not yet authenticated; authenticated durable realtime replay stays with
   the later realtime phase.
4. **Audit is durable from day one.**  `OutboxAuditSink` writes every audit
   event as a `security.audit.recorded` event through the Phase 6
   transactional outbox (own unit-of-work scope, deduplication by audit
   event id), so the trail survives crashes exactly like domain events.
   `InMemoryAuditSink` exists for tests.
5. **`REQUIRE_APPROVAL` is never executed over HTTP.**  The guard maps it to
   403 with code `require_approval` plus the deciding `policy_id`; the
   approval workflow arrives with agent-runtime approvals (plan section 19).
6. **Rate limiting is per-process.**  A sliding-window limiter keyed by
   client host answers 429 with `Retry-After` and `X-RateLimit-*` headers.
   A distributed limiter can implement the same `RateLimiter` protocol
   later; Windows are bounded in memory (FIFO eviction of tracked keys).
7. **Identity is a store contract plus an in-memory implementation.**  The
   durable identity store becomes a feature-module concern; provisioning
   (who may exist) is out of scope for the foundation.

## Consequences

- `Authorization PASS` / `Authentication PASS` gates (plan section 15) are
  now mechanically testable: inject the stack, assert 401/403/429 envelopes
  and audit records.
- Environment-provisioned secrets (`WINDAGENT_SECRET_<NAME>`) let
  production bootstrap the token key without a database write path.
- Modules must express authorization as `PolicyRule`s (action,
  resource_type, effect) contributed at composition — no ad-hoc checks
  inside handlers.
- Debug routes remain a bootstrap-mounted exception until Phase 9's
  authenticated transport replaces them; they are authenticated whenever an
  authenticator is configured.
