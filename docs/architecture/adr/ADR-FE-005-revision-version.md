# ADR-FE-005: Concurrency & Content Authority — Revision vs Version

- **Status**: ACCEPTED
- **Date**: 2026-08-14
- **Phase**: Phase 1 (Canonical Domain Vocabulary)
- **Deciders**: Architecture Council, Core API Team, Studio State Team

---

## Context and Problem Statement
Collaborative editing across desktop sidecars, web clients, and background agent writers requires a clear, unambiguous concurrency and content history model. Previously, "version" and "revision" were used interchangeably to mean both a snapshot of content and a concurrency lock.

## Decision
We formally decouple **Immutable Content History** from **Mutable Concurrency Control**:

1. **`Revision` (`rev_*`)**:
   - **Semantic**: An immutable snapshot of resource content at a point in time.
   - **Properties**: `revision_id`, `created_at`, `author_id` (user or agent), `parent_revision_id`, `content_hash`, `diff_summary`.
   - **Usage**: Used for undo/redo, timeline playback, audit logs, branching, and comparison views.

2. **`version` (Integer Concurrency Counter)**:
   - **Semantic**: A monotonically increasing positive integer (`1, 2, 3, ...`) representing the resource's current mutation sequence.
   - **Usage**: Optimistic concurrency control (OCC).
   - **Mutation Rule**:
     - All state-mutating requests (`PATCH`, `PUT`, `POST` actions) must supply `expected_version: number`.
     - If `expected_version !== current_version`, the server rejects the request with HTTP 409 Conflict using the canonical `ApiProblem` payload (`code: "REVISION_CONFLICT"` or `"VERSION_CONFLICT"`).
3. **ETag / If-Match**:
   - We standardize on `version` / `expected_version` in the JSON request body and response payload rather than relying on HTTP header parsing (`ETag` / `If-Match`), ensuring consistency across WebSocket RPC, Tauri IPC, and REST HTTP.

## Example Payload
```json
// Response
{
  "id": "proj_123",
  "version": 4,
  "current_revision_id": "rev_987",
  "title": "Neon Horizons"
}

// Mutating Request
{
  "expected_version": 4,
  "title": "Neon Horizons - Director's Cut"
}
```

## Consequences
- **Positive**: Zero lost updates; deterministic conflict resolution across multi-agent concurrent writes.
- **Negative**: Client mutation functions must explicitly track and pass `expected_version`.
