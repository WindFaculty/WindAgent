# CLI (windagent_cli)

## Responsibility
WindAgent CLI entrypoint (doctor, architecture check, workflow run) - Architecture V3

## Target Package
`apps/cli/windagent_cli`

## Allowed Dependencies
- `windagent_core`
- `windagent_orchestration`
- `windagent_intelligence`
- `windagent_providers`
- `windagent_tools`
- `windagent_workflows`
- `windagent_storage`
- `windagent_observability`
- `windagent_plugins`
- `windagent_skills`

## Forbidden Dependencies
- None

## Runtime

Install or run `windagent_cli` from the root workspace. The CLI composes only
canonical packages and has no dependency on an HTTP application implementation.

## Public API (Target)
- Expected domain models, interfaces, and public handlers for cli.
- Exposed strictly via `windagent_cli` top-level exports.

## Out-of-Scope
- ASGI and Worker process startup.
- Retired Architecture V1/V2 implementations.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
