# ORCHESTRATION (windagent_orchestration)

## Responsibility
Task manager, workflow engine, state machine, scheduler, dispatcher, retry, recovery

## Target Package
`orchestration/windagent_orchestration`

## Allowed Dependencies
- `windagent_core`
- `windagent_storage`

## Forbidden Dependencies
- `apps`
- `windagent_providers`

## Legacy Migration Source
`apps/backend/services/workflow_service.py, recovery.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for orchestration.
- Exposed strictly via `windagent_orchestration` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
