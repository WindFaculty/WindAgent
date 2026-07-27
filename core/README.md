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

## Migration Status

The legacy backend model and configuration sources have been retired. This
package is the canonical source for shared domain contracts.

## Public API (Target)
- Expected domain models, interfaces, and public handlers for core.
- Exposed strictly via `windagent_core` top-level exports.

## Out-of-Scope

- Application runtime and transport concerns.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
