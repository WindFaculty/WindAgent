# CONTEXT (windagent_context)

## Responsibility
Context assembly, token budgeting, prompt formatting

## Target Package
`context/windagent_context`

## Allowed Dependencies
- `windagent_core`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/services/context_service.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for context.
- Exposed strictly via `windagent_context` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
