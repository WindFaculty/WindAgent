# ADR-0004: `/api/v4` is the single canonical API prefix

- Status: Accepted
- Date: 2026-09-02
- Phase: 8 (API foundation)

## Context

Plan section 12 requires the new API to carry a fresh canonical version and
states that the folder name `Wind_agent_v2` must not decide the API version.
The old system mounts 29 routers with V2-compatibility and Live Record
dual-mounts still active, so reusing `/api/v2` or `/api/v3` would drag that
history into the clean-room implementation.

## Decision

- Every module-owned route is mounted under **`/api/v4`**
  (`windagent_api.api.API_PREFIX`).  The version constant lives in code, not
  in the repository name.
- There is exactly **one** router tree.  No legacy routers, no compatibility
  mounts, no dual-mount of any capability (plan section 12: "không kéo theo
  29 router V2 hoặc dual-mount").
- The Phase 7 `/debug/jobs` surface is the sole exception: it is an
  unauthenticated development tool that is only mounted when a durable queue
  is explicitly injected into `create_app`, and it is removed once Phase 9
  provides an authenticated transport.
- Error responses use one canonical envelope:
  `{"error": {"code", "message", "context"}}`.  Unmapped domain codes fail
  closed with HTTP 500.

## Consequences

- Clients can detect the V2 world by prefix alone; there is no
  version-negotiation surface.
- Frontend SDK generation (plan section 27) targets the
  `/api/v4/openapi.json` document only.
- When a feature module ships a router, it appears under `/api/v4`
  automatically through its `ModuleManifest.routers` — no bootstrap edit.
- Any temptation to mount "temporary" second paths must be resolved by an
  ADR like this one, not by silent dual-mounting.
