# TOOLS (windagent_tools)

## Responsibility
Tool registry, filesystem, shell, git, code_search, AST, LSP, browser, database, MCP

## Target Package
`tools/windagent_tools`

## Allowed Dependencies
- `windagent_core`

## Forbidden Dependencies
- `apps`
- `windagent_orchestration`

## Legacy Migration Source
`apps/backend/services/tool_execution_service.py, tools/`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for tools.
- Exposed strictly via `windagent_tools` top-level exports.

## Out-of-Scope
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
