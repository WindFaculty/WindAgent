# Phase 6 — Event + Outbox foundation

Date: 2026-09-02

## Scope delivered

`platform/events` now implements the plan section 10 target layout on top of
the Phase 5 persistence layer:

```text
platform/events/
├── contracts.py     EventBus / EventHandler / EventPublisher / EventSubscription (unchanged)
├── envelope.py      canonical envelope (kernel re-export)
├── registry.py      EventTypeRegistry — name → schema version, envelope validation
├── dispatcher.py    InProcessEventBus — fan-out, registration order, error isolation
├── subscriptions.py Subscription handles + SubscriptionSet (group teardown)
├── outbox.py        platform_events + platform_outbox tables, TransactionalOutbox, OutboxStore
└── publisher.py     OutboxPublisher — claim → deliver → finalize drain loop
```

The envelope keeps every plan-mandated field (event_id, event_type,
event_version, aggregate identity + sequence, actor/correlation/causation,
occurred_at, payload) — the kernel owns it; the platform adds persistence
and delivery around it.

## Atomic transaction pattern (preserved from the old system)

```text
domain change (same session)
  → event-store append (platform_events)
  → crash gate: uow.checkpoint("after_event_write")   # old Phase 5A seam
  → outbox write (platform_outbox)
  → COMMIT
```

`TransactionalOutbox` joins the caller's unit of work — a crash anywhere
before commit rolls the domain change, the event, and the outbox row back
together. `deduplication_key` reproduces the old finalizer's idempotency
check (pre-select by key; unique constraint as the backstop). A rollback
discards both writes; a checkpoint failure aborts the commit.

Sequence numbers mirror the old event store: `record_next` allocates
`max(sequence) + 1` per aggregate stream inside the caller's transaction;
`uq_platform_events_stream` is the concurrency backstop.

## Publisher semantics (preserved + tightened)

- Claim: `pending` + `available_at <= now`, oldest stream position first,
  guarded status flip `pending → publishing` with `claimed_by`,
  `claim_token`, `claim_expires_at` (lease).  On PostgreSQL the scan uses
  `FOR UPDATE SKIP LOCKED`; on other dialects the guarded flip alone
  guarantees single ownership.
- Deliver outside any database transaction — the old processor dispatched
  inside its claim transaction; V2 claims in one short transaction,
  delivers via the `EventPublisher` port, then finalizes.
- Finalize: `mark_published` is a claim-token CAS (old semantics);
  `mark_failed` increments `attempt_count` in the same statement, sets
  `last_error`, applies backoff, and moves to `dead_letter` at
  `max_attempts` (default 5) instead of back to `pending`.
- Recovery: `reclaim_expired_claims` returns expired leases to `pending`;
  `run()` drains + reclaims until a stop event is set (worker foundation
  for Phase 7).

## Intentional improvement (ADR-0003)

The outbox now persists `actor_id`, `correlation_id`, `causation_id` and
restores them in the delivered envelope. The old system dropped the causal
chain at the outbox boundary; V2 keeps it end-to-end for tracing (Phase 10).

## Boundaries preserved

- Contract/adapter split (ADR-0002 pattern): `contracts.py`, `envelope.py`,
  `registry.py`, `dispatcher.py`, `subscriptions.py` stay kernel+stdlib
  only; `outbox.py` and `publisher.py` are adapters gated to kernel,
  configuration, persistence, and the DB toolchain.
- Migration `0002_events_outbox` creates both platform tables from the same
  definitions the runtime uses (`migrations/versions/0002_events_outbox.py`
  imports the table objects) — schema and adapter cannot drift. The chain
  is `0001 → 0002`; no legacy schema was copied.

## Verification

- Unit tests (in-memory databases): registry validation, fan-out order,
  error isolation, subscription lifecycle, atomic record (commit/rollback/
  crash-gate failure), dedup idempotency, stream sequence allocation and
  conflict rejection, claim exclusivity + lease fields, claim-token CAS
  finalize, retry→dead-letter transitions, expired-claim reclaim, status
  counts, publisher drain reports and `run(stop)` loop behavior.
- Integration tests (`-m postgres`, CI service container): end-to-end
  record→commit→deliver→published flow with causal identity round trip,
  concurrent claim scans with disjoint ownership (SKIP LOCKED), failure
  retry recovery on live rows, timestamptz round trip, and the migration
  chain probe now asserts `0002` head plus both platform tables.
