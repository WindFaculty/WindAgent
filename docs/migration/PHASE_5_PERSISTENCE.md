# Phase 5 — Persistence V2

Date: 2026-09-02

## Scope delivered

`platform/persistence` now owns the concrete SQL transaction boundary
(plan section 8 target layout):

```text
platform/persistence/
├── contracts.py     UnitOfWork ABC (unchanged, infrastructure-free)
├── database.py      Database — async engine + session factory
├── transaction.py   TransactionScope, IsolationLevel
├── unit_of_work.py  SqlUnitOfWork + crash-gate checkpoint seam
├── health.py        probes: check_database_health, wait_for_database
├── metadata.py      shared MetaData + target_metadata for Alembic
└── postgres/        errors (SQLSTATE), locks (advisory), cas, upsert
```

PostgreSQL is the only canonical database. `Database.from_url` rejects any
non-PostgreSQL scheme outside `WINDAGENT_ENVIRONMENT=test` with a startup
error, engine pooling is tuned for `asyncpg` (`pool_pre_ping`, size,
overflow, recycle), and credentials are masked in every public string
surface. This closes the old project's default-SQLite drift for good.

Preserved semantics from the old storage layer (rewritten, not copied):

- **SQL unit of work** — one session per scope, repositories composed
  session-bound at entry through a single allowlisted construction point,
  explicit commit/rollback, exception paths roll back, uncommitted clean
  exits are discarded (never silently committed).
- **Transactional finalization support** — the crash-gate checkpoint seam
  (old Phase 5A) survives as `SqlUnitOfWork.checkpoint(name)` with
  sync/async hooks and zero overhead when unconfigured. Phases 6/7 place
  gates at the exact event-write and finalizer points.
- **CAS updates** — `compare_and_swap_update` performs the conditional
  `UPDATE ... WHERE version = expected SET version = version + 1` pattern
  used by the durable queue and task finalizer; losing the race is a
  `False`, not an error.
- **Transient-error classification** — SQLSTATE extraction (asyncpg
  `sqlstate`, SQLAlchemy `orig`/`__cause__` chains) with the old
  serialization/deadlock/lock/connection classes preserved for retry
  policies.
- **Leader election primitive** — named advisory locks (deterministic
  SHA-256 → signed int32 pair), transaction- and session-scoped.

Migration chain starts clean: `0001_v2_foundation` is an empty baseline
(plan section 9 — none of the old repository's 31 revisions are copied).
`migrations/env.py` now resolves `target_metadata` from
`platform/persistence/metadata.py`, so autogenerate is live for future
module migrations (`0002_identity`, `0003_jobs`, ...).

## Boundaries preserved

- `platform/persistence/contracts.py` stays infrastructure-free (kernel +
  stdlib only). The adapter files are gated by a new architecture test
  that allows only kernel, configuration settings and the persistence
  toolchain (SQLAlchemy/Alembic/asyncpg) — no HTTP, web framework, or
  provider dependencies (ADR-0002).
- No business module was migrated; persistence is domain-agnostic and
  exposes no Episode/Agent/Model vocabulary.
- The word "SQLite" appears nowhere in backend source outside
  `configuration/settings.py` (architecture gate unchanged).

## Verification

- Unit tests (isolated in-memory databases): engine factory and URL
  canonicality, transaction scope lifecycle, unit-of-work commit/rollback/
  repository composition/checkpoint hooks (sync + async + failure),
  health probes, SQLSTATE classification, CAS win/lose semantics, upsert
  validation, lock-key determinism, metadata naming conventions.
- Integration tests (`-m postgres`, run in CI against a PostgreSQL 16
  service container, skipped locally when the canonical database is
  down): health server metadata, unit-of-work commit on PostgreSQL,
  CAS/upsert on live rows, advisory lock mutual exclusion across
  connections, and a full `alembic upgrade head`/`downgrade base`
  round trip against a throwaway database.
- CI gained a `postgres-integration` job so the Phase 5 gate ("PostgreSQL
  PASS") is continuously verified, not assumed.
