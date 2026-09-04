# WindAgent V2 API

FastAPI entrypoint and HTTP composition root (Phase 8).

- All module routes live under the single canonical prefix `/api/v4`
  (ADR-0004).  There is no legacy router tree and no dual-mount.
- Security (Phase 9, ADR-0005): when authentication is composed (or
  `WINDAGENT_AUTH_ENABLED=true`), every route except `/health`, `/ready`,
  `/metrics`, and the OpenAPI docs requires `Authorization: Bearer <token>`; requests
  are verified HMAC tokens resolved to active identities.  Authorization
  runs through the fail-closed `PolicyEngine` (`default-deny`), every
  decision is audited durably via the transactional outbox, and per-client
  rate limiting answers 429 with `Retry-After`.
- Routers only perform HTTP → DTO validation → CommandBus/QueryBus →
  response mapper; business rules live in handlers registered through
  `ModuleManifest`s discovered from `windagent.modules`.
- `/health` is liveness; `/ready` probes PostgreSQL and fails closed with
  503 when the database is unreachable.
- Observability (Phase 10, ADR-0006): W3C `traceparent` propagation,
  trace/correlation response headers, JSON logs, bounded metrics at
  `/metrics`, and spans around HTTP plus CommandBus/QueryBus dispatch.
- Every error uses the canonical envelope
  `{"error": {"code", "message", "context"}}`.
- The Phase 7 `/debug/jobs` surface is mounted only when a durable queue is
  explicitly injected; authentication protects it whenever the security
  stack is enabled.

Run locally:

```powershell
uv run uvicorn windagent_api.app:app --reload
```
