# CORE (windagent_core)

## Responsibility
Core domain models, contracts, domain events, errors, config, security types

## Target Package
`core/windagent_core`

## Allowed Dependencies
- None (leaf module)

## Forbidden Dependencies
- `apps`
- `fastapi`
- `sqlalchemy`
- `mcp`
- `langgraph`
- `providers`

## Legacy Migration Source
`apps/backend/models, apps/backend/config.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for core.
- Exposed strictly via `windagent_core` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
