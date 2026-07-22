# WORKER (windagent_worker)

## Responsibility
Background worker process for asynchronous task execution

## Target Package
`apps/worker/windagent_worker`

## Allowed Dependencies
- `windagent_core`
- `windagent_orchestration`
- `windagent_storage`
- `windagent_observability`

## Forbidden Dependencies
- None

## Legacy Migration Source
`apps/backend/worker.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for worker.
- Exposed strictly via `windagent_worker` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
