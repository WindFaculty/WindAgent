# API (windagent_api)

## Responsibility
FastAPI REST & WebSocket entrypoint for Architecture V3

## Target Package
`apps/api/windagent_api`

## Allowed Dependencies
- `windagent_core`
- `windagent_orchestration`
- `windagent_execution`
- `windagent_intelligence`
- `windagent_providers`
- `windagent_tools`
- `windagent_workflows`
- `windagent_verification`
- `windagent_context`
- `windagent_memory`
- `windagent_plugins`
- `windagent_skills`
- `windagent_storage`
- `windagent_observability`

## Forbidden Dependencies
- None

## Runtime

This is the only HTTP/ASGI authority. Start it from the workspace root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_api.ps1
```

The ASGI target is `windagent_api.main:app`. API V3 is served under
`/api/v3/*` and realtime WebSocket under `/ws`; `/api/v1/*` and `/api/v2/*`
are permanent `410 Gone` tombstones.

## Public API (Target)
- Expected domain models, interfaces, and public handlers for api.
- Exposed strictly via `windagent_api` top-level exports.

## Out-of-Scope
- Retired Architecture V1/V2 implementations.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
