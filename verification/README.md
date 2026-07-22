# VERIFICATION (windagent_verification)

## Responsibility
Quality gates, verification runners, test assertion helpers

## Target Package
`verification/windagent_verification`

## Allowed Dependencies
- `windagent_core`
- `windagent_tools`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/verification/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for verification.
- Exposed strictly via `windagent_verification` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
