# API (windagent_api)

## Responsibility
FastAPI REST & WebSocket entrypoint for Architecture V2

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

The ASGI target is `windagent_api.main:app`. API V2 is served under
`/api/v2/*`; `/api/v1/*` is a permanent `410 Gone` tombstone.

## Public API (Target)
- Expected domain models, interfaces, and public handlers for api.
- Exposed strictly via `windagent_api` top-level exports.

## Out-of-Scope
- Retired Architecture V1 implementation.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
