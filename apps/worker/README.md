# WORKER (windagent_worker)

## Responsibility
Background worker process for asynchronous task execution - Architecture V3

## Target Package
`apps/worker/windagent_worker`

## Allowed Dependencies
- `windagent_core`
- `windagent_orchestration`
- `windagent_execution`
- `windagent_providers`
- `windagent_tools`
- `windagent_intelligence`
- `windagent_context`
- `windagent_memory`
- `windagent_workflows`
- `windagent_verification`
- `windagent_storage`
- `windagent_observability`

## Forbidden Dependencies
- None

## Runtime

The Worker is installed from the root workspace and shares
`WINDAGENT_DATABASE_URL` with the API process. It does not import an API
application package or any retired runtime implementation.

## Public API (Target)
- Expected domain models, interfaces, and public handlers for worker.
- Exposed strictly via `windagent_worker` top-level exports.

## Out-of-Scope
- HTTP routing and ASGI startup.
- Retired Architecture V1/V2 implementations.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
