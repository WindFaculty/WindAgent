# ADR-FE-006: Semantic Separation of Memory vs Database

- **Status**: ACCEPTED
- **Date**: 2026-08-14
- **Phase**: Phase 1 (Canonical Domain Vocabulary)
- **Deciders**: Architecture Council, Intelligence & UX Team

---

## Context and Problem Statement
In the desktop navigation (`DESKTOP_NAVIGATION_GROUPS`), the item `memory` was labeled with the user-facing text `"Database"` with a `BETA` badge. Meanwhile, `v2_memory.py` serves agent memory records (facts, user preferences, vector embeddings, entities), while low-level persistence uses SQLite / PostgreSQL databases.
This caused users to believe they were managing raw SQL tables or database migrations rather than agent recall memory.

## Decision
1. **`Memory` is the canonical domain term for contextual agent knowledge**:
   - Semantic memories, user persona facts, project-specific knowledge bases, vector search stores.
2. **`Database` is strictly reserved for infrastructure persistence & administrative tools**:
   - Connection pools, migrations, vacuuming, backups.
3. **UI / Navigation Alignment**:
   - The navigation item with id `memory` is canonicalized in UI label to **`"Memory"`** (or `"Agent Memory"`), removing the misleading `"Database"` label.
   - Any raw database inspection tools, if needed, will be categorized under System / Developer Tools, not general agent workspace.

## Consequences
- **Positive**: Direct alignment between user mental model, backend service (`memory/`), and API endpoints (`/api/v3/memory`).
- **Enforcement**: Phase 4 router manifest and Phase 5 navigation will render label `"Memory"`.
