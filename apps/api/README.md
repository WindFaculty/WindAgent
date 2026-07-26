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

## Legacy Migration Source
`apps/backend/main.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for api.
- Exposed strictly via `windagent_api` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
