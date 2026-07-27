# PLUGINS (windagent_plugins)

## Responsibility
Plugin system for extensible functionality - loader, registry, lifecycle, security, manifest

## Target Package
`plugins/windagent_plugins`

## Allowed Dependencies
- `windagent_core`

## Forbidden Dependencies
- `apps`
- `windagent_orchestration`
- `windagent_intelligence`
- `windagent_storage`

## Legacy Migration Source
`apps/backend/plugins/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for plugins.
- Exposed strictly via `windagent_plugins` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
