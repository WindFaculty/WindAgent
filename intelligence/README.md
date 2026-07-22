# INTELLIGENCE (windagent_intelligence)

## Responsibility
Task classifier, planner, context builder, model router, summarizer, reviewer, reporter

## Target Package
`intelligence/windagent_intelligence`

## Allowed Dependencies
- `windagent_core`
- `windagent_providers`
- `windagent_context`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/services/model_routing_service.py, agent_service.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for intelligence.
- Exposed strictly via `windagent_intelligence` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
