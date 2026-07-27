# Phase 6 — Controlled retirement of `apps/backend`

Status: **PASS**

Acceptance gate: **LEGACY_BACKEND_RUNTIME_REMOVED**

The tracked legacy backend tree has been removed after repository-owned
consumers and regression contracts were migrated to Architecture V2. No
compatibility shim is retained because the consumer inventory is zero.

## Gate evidence

- Zero production imports from `apps.backend` or `backend`.
- Zero Python source files remain in the retired tree outside ignored local
  caches and virtual environments.
- Zero compatibility shims and therefore zero shim business logic.
- The root workspace and Python path exclude `apps/backend`.
- Runtime launchers start `windagent_api.main:app`.
- Desktop and web source make no `/api/v1` requests.
- `/api/v1/*` remains a permanent `410 Gone` tombstone in the canonical API.
- API, Worker, and CLI pass isolated installation/import probes.
- Python regression: `736 passed, 1 skipped, 0 failed`.
- Desktop: `89` tests, typecheck, and production build passed.
- Web: `83` tests, typecheck, and production build passed.
- Architecture, scaffold, CLI architecture, launcher parse, and targeted lint
  checks passed.

## Deletion and rollback

`deleted_files_manifest.json` records all 170 removed tracked paths. The
rollback plan uses the pre-cutover base commit for investigation and prefers a
minimal delegating package over restoration of legacy business logic. Database
rollback must never discard user data.

## Remaining work

No Phase 6 gate item remains open. Non-blocking release follow-ups are recorded
in `risk_register.md`.
