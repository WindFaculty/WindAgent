# EXECUTION (windagent_execution)

## Responsibility
Git worktree isolation, sandbox runtime, subprocess execution

## Target Package
`execution/windagent_execution`

## Allowed Dependencies
- `windagent_core`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/services/worktree_service.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for execution.
- Exposed strictly via `windagent_execution` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
