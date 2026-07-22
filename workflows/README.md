# WORKFLOWS (windagent_workflows)

## Responsibility
Predefined workflow definitions and step implementations

## Target Package
`workflows/windagent_workflows`

## Allowed Dependencies
- `windagent_core`
- `windagent_orchestration`
- `windagent_tools`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/workflows/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for workflows.
- Exposed strictly via `windagent_workflows` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
