# EVALS (windagent_evals)

## Responsibility
Evaluation benchmarks, model output scoring, regression suites

## Target Package
`evals/windagent_evals`

## Allowed Dependencies
- `windagent_core`
- `windagent_intelligence`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/evals/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for evals.
- Exposed strictly via `windagent_evals` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
