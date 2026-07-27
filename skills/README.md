# SKILLS (windagent_skills)

## Responsibility
Skills system for reusable capabilities - loader, registry, execution, versioning

## Target Package
`skills/windagent_skills`

## Allowed Dependencies
- `windagent_core`
- `windagent_providers`
- `windagent_tools`

## Forbidden Dependencies
- `apps`
- `windagent_orchestration`

## Legacy Migration Source
`apps/backend/skills/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for skills.
- Exposed strictly via `windagent_skills` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
