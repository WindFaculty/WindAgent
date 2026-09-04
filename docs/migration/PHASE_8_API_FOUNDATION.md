# Phase 8 — API foundation

Date: 2026-09-02

## Scope delivered

The FastAPI layer is now a real composition root built strictly on the
Phase 3–7 seams.  The application layout follows plan section 12:

```text
apps/api/src/windagent_api/
├── api/          /api/v4 builder + system/info surface (ADR-0004)
├── auth/         actor-identity plumbing seam (real auth is Phase 9)
├── bootstrap/    app factory, in-process buses, ApiModuleRuntime
├── debug/        Phase 7 debug slice, now behind the buses
├── errors/       canonical error envelope + DomainError→HTTP mapping
├── health/       /health liveness + /ready readiness with DB probe
├── middleware/   request/correlation/causation identity context
└── app.py        backwards-compatible uvicorn entrypoint
```

## Router discipline (plan section 12)

Every route does exactly:

```text
HTTP  →  validate DTO (Pydantic)  →  CommandBus / QueryBus  →  response mapper
```

- Routers never touch SQL, the job queue, providers, or business logic;
  those live in handlers that own the rules.
- `InProcessCommandBus` / `InProcessQueryBus` implement the Phase 3
  Protocols at the composition root, with single-owner registration and
  fail-closed dispatch errors.
- Feature modules join the API exclusively through `ModuleManifest`s
  discovered from `windagent.modules` — commands, queries, and routers are
  registered by the Phase 4 loader; no bootstrap file lists feature names.

## API version

`/api/v4` is the single canonical prefix (ADR-0004).  No legacy router tree
and no dual-mount exist.  `GET /api/v4/system/info` reports the API version,
environment, and loaded module IDs through the QueryBus.

## Errors

One envelope for every failure:
`{"error": {"code", "message", "context"}}`.  `DomainError` codes map to
HTTP statuses via `DomainErrorStatusMapper` (validation 400, not_found 404,
conflict 409, …); unknown codes fail closed on 500.  Unexpected exceptions
return a generic 500 and never leak internals outside non-production
environments.  Pydantic transport validation returns 422 with sanitized
`loc/msg/type` entries (client input is dropped).

## Identity and readiness

- `RequestContextMiddleware` stamps every request with a bounded
  `X-Request-Id` (echoed on the response) and validates
  `X-Correlation-Id`/`X-Causation-Id` UUIDs into kernel identifiers — the
  values Phase 10 tracing will consume.
- `auth/` exposes the `ActorResolver` seam and a `get_principal`
  dependency; the default resolver reads `X-Actor-Id` without verifying it
  and is explicitly a Phase 9 replacement target.
- `/ready` now probes PostgreSQL via the Phase 5 `check_database_health`
  and fails closed with 503 when the database is unreachable; connection
  details are only exposed outside production.

## Module and debug composition

`ApiModuleRuntime` wires manifest contributions: commands and queries into
the buses, routers under `/api/v4`.  The Phase 7 debug slice keeps its
opt-in contract (`/debug/jobs` + websocket) but its routes now dispatch
`SubmitDebugJob` / `GetDebugJob` / `CancelDebugJob` through the buses, so
even the debug transport obeys the router rules.

## Gates

Current local evidence:

```text
targeted Phase 8 suite       PASS
full offline regression      PASS (183 passed: unit, architecture,
                             contract, parity, e2e)
PostgreSQL integration       PASS (12 passed)
Ruff                         PASS
mypy strict                  PASS (144 source files)
```

New coverage: in-process bus dispatch/ownership rules, `/api/v4/system/info`
through the QueryBus, manifest-driven router mounting, canonical error
envelopes (domain, transport, unexpected), request-identity middleware,
and readiness probe outcomes.
