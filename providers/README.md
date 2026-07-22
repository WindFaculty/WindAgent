# PROVIDERS (windagent_providers)

## Responsibility
Model provider integrations (OpenAI, Anthropic, Google, Ollama, etc.)

## Target Package
`providers/windagent_providers`

## Allowed Dependencies
- `windagent_core`

## Forbidden Dependencies
- `apps`
- `windagent_orchestration`
- `windagent_intelligence`

## Legacy Migration Source
`apps/backend/services/model_service.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for providers.
- Exposed strictly via `windagent_providers` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
