# MEMORY (windagent_memory)

## Responsibility
Multi-layered memory, working memory, long-term memory, semantic store

## Target Package
`memory/windagent_memory`

## Allowed Dependencies
- `windagent_core`
- `windagent_storage`

## Forbidden Dependencies
- `apps`

## Legacy Migration Source
`apps/backend/services/memory_service.py`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for memory.
- Exposed strictly via `windagent_memory` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
