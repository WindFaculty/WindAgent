# Phase 7 — Job Runtime + Worker foundation

Date: 2026-09-02

## Scope delivered

The V2 worker is a clean rewrite around the Phase 3 contracts and Phase 5–6
transaction/outbox seams:

```text
WorkerRuntime
  → PostgresJobQueue.claim_next
  → LeaseGuard heartbeat + authority probe
  → JobHandlerRegistry
  → handler execution
  → JobResultValidator
  → fencing CAS
  → job state + attempt + event + outbox
  → COMMIT
```

`JobEnvelope` contains the required identity/type/version/payload, priority,
attempt/max-attempts, timeout/deadline, correlation/causation IDs, and fencing
token. Payloads and results cross an immutable JSON boundary.

## Durable semantics

- Submission is priority-descending/FIFO and supports a unique idempotency key.
- PostgreSQL claims use `FOR UPDATE SKIP LOCKED`; guarded state updates remain
  the race backstop on every dialect.
- Every takeover increments both attempt and lease generation and receives a
  new fencing token. Expired/stale workers cannot renew or finalize.
- Heartbeats renew only a live exact-token lease and surface durable
  cancellation requests.
- Failures retry with bounded deterministic exponential backoff until the
  attempt/deadline limit; timeouts and worker-stop interruptions use the same
  durable path.
- Success, terminal failure, retry scheduling, and cancellation update the job
  and attempt, append the job event, and write the outbox in one transaction.
  `after_job_state_write` is the crash-injection gate.
- A restarted queue can reclaim an expired claim; exhausted or cancelled
  expired claims are finalized by recovery.

Migration `0003` creates `platform_jobs` and `platform_job_attempts` from the
same table definitions used by the runtime.

## Module and vertical-slice composition

`WorkerModuleRuntime` accepts `JobRegistration` entries from the Phase 4
loader and fills `JobHandlerRegistry`; feature names never enter the worker
engine.

The opt-in debug slice is:

```text
POST /debug/jobs
  → durable queue
  → WorkerRuntime
  → FakeJobHandler (`debug.echo`)
  → atomic result + outbox
  → OutboxPublisher
  → RealtimeHub
  → /debug/jobs/events websocket
```

The hub's short replay buffer is explicitly process-local. The event/outbox
tables remain the durable source; authenticated durable websocket replay is a
later API/realtime phase.

## Reliability gates

Tests cover every required Phase 7 case: two-worker claim exclusion, worker
crash, lease expiry/takeover, stale finalization, duplicate submission, retry,
timeout, queued and running cancellation, server restart, worker restart, and
crash rollback between job-state mutation and outbox write. Frozen behavioral
oracles for priority/FIFO and fencing live under `tests/parity/`.

Current local evidence:

```text
targeted Phase 7 suite       PASS
full backend regression      PASS (162 passed, 0 skipped)
PostgreSQL integration       PASS (12 passed)
Ruff                         PASS
mypy strict                  PASS (119 source files)
frontend typecheck/test      PASS
frontend production build    PASS
backend/frontend audit       PASS
```

The PostgreSQL integration suite passes concurrent disjoint claims and
restart-visible finalization. It also certifies the exact milestone path:
HTTP submission → PostgreSQL → worker → fake handler → atomic result/outbox
→ WebSocket replay. Both local Docker certification and the CI gate are green.
