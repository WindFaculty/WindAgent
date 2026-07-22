# CLI (windagent_cli)

## Responsibility
WindAgent CLI entrypoint (doctor, architecture check, workflow run)

## Target Package
`apps/cli/windagent_cli`

## Allowed Dependencies
- `windagent_core`
- `windagent_orchestration`
- `windagent_intelligence`
- `windagent_storage`

## Forbidden Dependencies
- None

## Legacy Migration Source
`apps/backend/cli.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for cli.
- Exposed strictly via `windagent_cli` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
