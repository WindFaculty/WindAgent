# ADR-0002: Persistence V2 — canonical PostgreSQL and the contract/adapter split

- Status: Accepted
- Date: 2026-09-02
- Phase: 5 (persistence)

## Context

Phase 3 froze `platform/persistence` as a pure contract surface: an
infrastructure-free `UnitOfWork` ABC, with the implementation deferred.
Phase 5 (plan section 8) must now deliver the real persistence layer —
engine, transactions, unit of work, health — with PostgreSQL as the only
canonical database, without weakening the architecture gates that stop V2
from drifting back into the old repository's shape.

Two tensions had to be resolved:

1. The Phase 3 architecture test scanned *every* file under
   `platform/persistence` and banned infrastructure imports — yet the plan's
   target layout for Phase 5 puts concrete adapters (`database.py`,
   `postgres/`) in exactly that package.
2. The old system's semantics worth preserving (SQL UoW, CAS durable
   updates, transactional finalization crash gates, outbox-ready
   transaction boundaries) must be carried over as behavior, not as copied
   files (plan sections 8, 30, 31).

## Decision

- **Target layout implemented as planned.** `platform/persistence` now
  contains `database.py`, `transaction.py`, `unit_of_work.py`,
  `health.py`, `metadata.py`, and a `postgres/` subpackage
  (SQLSTATE classification, advisory locks, CAS, upsert) next to the
  untouched `contracts.py`.
- **Contract/adapter split inside the package.** The architecture test now
  treats `persistence/contracts.py` as the only contract file (kernel +
  stdlib imports only). A new gate
  (`test_persistence_adapters_import_only_the_persistence_toolchain`)
  restricts every other persistence file to kernel, configuration
  settings, and SQLAlchemy/Alembic/asyncpg — deliberately excluding
  FastAPI/httpx/pydantic so the layer stays a persistence layer.
- **PostgreSQL canonicality enforced at three levels** (plan section 8,
  35): `Settings` rejects SQLite URLs outside the test environment;
  `Database.from_url` re-validates raw URLs at composition time and masks
  credentials on every public surface; the
  `test_sqlite_is_not_a_default_in_backend_source` text gate is unchanged.
- **Semantics preserved by rewrite.** The unit of work keeps one
  session-scoped repository composition point, explicit commit/rollback,
  discard-on-abandon exits, and the old Phase 5A crash-gate seam
  (`checkpoint(name)`, sync/async hooks, zero overhead when unset). CAS
  keeps the conditional version-bump statement with rowcount-as-outcome.
  SQLSTATE transient classes (serialization/deadlock/lock/connection)
  survive for the Phase 7 retry classifier.
- **Clean migration chain.** `0001_v2_foundation` is an intentionally
  empty baseline (plan section 9); `target_metadata` is published from
  `platform/persistence/metadata.py` so Alembic autogenerate is live for
  module migrations only.
- **PostgreSQL is continuously proven.** CI gains a `postgres-integration`
  job (PostgreSQL 16 service container) running the `-m postgres`
  integration suite: health metadata, UoW commit, CAS/upsert, advisory
  lock exclusion, and an upgrade/downgrade round trip on a throwaway
  database. Local runs skip cleanly when the canonical database is down.

## Consequences

- Phases 6/7 build directly on this surface: the outbox writes through the
  UoW transaction, the job queue reuses `compare_and_swap_update` and the
  SQLSTATE classifier, and recovery leader leases use the advisory lock
  helpers.
- Foundation packages must never add a second SQL access path: module
  infrastructures compose repositories through unit-of-work scopes, not
  through ad-hoc engines.
- The contract-file allowlist pattern (`PLATFORM_CONTRACT_FILES`) extends
  to future packages only when a phase deliberately moves concrete
  adapters into `platform/`, with the same paired adapter gate.
