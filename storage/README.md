# STORAGE (windagent_storage)

## Responsibility
Database repositories, ORM mappings, migration adapters, persistent artifact storage

## Target Package
`storage/windagent_storage`

## Allowed Dependencies
- `windagent_core`

## Forbidden Dependencies
- `apps`
- `windagent_orchestration`
- `windagent_intelligence`

## Legacy Migration Source
`apps/backend/db/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for storage.
- Exposed strictly via `windagent_storage` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
