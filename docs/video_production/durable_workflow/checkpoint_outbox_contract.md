# Phase 17 — Durable Production Workflow: Checkpoint & Outbox Contract

- **Gate:** `VP17_DURABLE_WORKFLOW_VERIFIED`
- **Plan:** `docs/video_production/plans/05_phase_17_20_orchestration_cost_review.md` §8.3
- **Module:** `orchestration/windagent_orchestration/production/checkpoint.py`,
  `orchestration/windagent_orchestration/production/outbox.py`,
  `orchestration/windagent_orchestration/production/engine.py`

## 1. Checkpoint payload

A `ProductionCheckpoint` records (plan 05 §8.3):

```text
run_id, current_step, step_version, attempt
input_revision_hash, input_hashes, output_hashes
lease (worker_id, expires_at, token)
pending_external_operation (step_id, provider, request_hash, external_id, submitted_at)
```

The pending external operation is the key reconciliation field: a checkpoint
with a pending op means "a submit may have happened — inspect the provider
before doing anything".

## 2. Atomic commit (Unit of Work)

`ProductionUnitOfWork.commit(run, events)` persists run state + checkpoint +
outbox events in a **single atomic write** (temp file + `os.replace`). Events
are only marked `published` after that write succeeds.

Property: a crash before the write leaves **nothing** persisted — the journal
on disk never contains an unpublished event, so there is no stuck-pending
window. `replay_pending()` is provided defensively and returns `[]` in normal
operation.

## 3. Outbox journal rules

- append-only; published events are never deleted;
- `append` deduplicates on `deduplication_key`;
- `mark_published` only transitions `pending → published`;
- external provider result ingestion is idempotent by generation/external
  event ID (`ingest_external_result`): a duplicate delivery applies **no**
  side effects and never overwrites output hashes.

## 4. SUBMITTING intent before side effect (gate-critical)

For external-cost steps the engine persists the SUBMITTING intent
(`video_production.generation_submitting` event + checkpoint with a pending
op placeholder) **BEFORE** invoking the `StepExecutorPort`. A crash between
the intent write and the executor's real submit therefore lands in
reconciliation — never a blind resubmit (plan 05 §8.5).

## 5. Stale-write protection

- **Lease:** a run leased by worker A rejects writes from worker B until the
  lease expires (clock-injectable).
- **Version CAS:** `ProductionRunStore.save` compares the on-disk version to
  the version snapshot taken at load and rejects mismatches with
  `ConcurrentStateConflictError`. Duplicate or stale worker writes can never
  cause side effects.

## 6. Evidence

- `artifacts/video_production/phase_17/checkpoint_outbox_receipt.json`
