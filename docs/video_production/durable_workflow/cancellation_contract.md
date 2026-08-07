# Phase 17 — Durable Production Workflow: Cancellation Contract

- **Gate:** `VP17_DURABLE_WORKFLOW_VERIFIED`
- **Plan:** `docs/video_production/plans/05_phase_17_20_orchestration_cost_review.md` §8.6
- **Module:** `orchestration/windagent_orchestration/production/cancellation.py`

## 1. Rules

Plan 05 §8.6:

1. Cancel stops **new scheduling**.
2. An active provider operation transitions to cancel/reconcile according to
   **real** provider capability — WindAgent never claims the external job
   stopped without evidence.
3. Artifacts that already completed keep their provenance but are **not**
   auto-published.
4. Cancel reason / actor / timestamp are audited in an append-only log.

## 2. Audit

`ProductionCancellation.request` appends a `CancelAuditEntry`:

```text
cancel_id, run_id, actor, reason, requested_at,
provider_cancel_confirmed, provider_evidence
```

The log is append-only and survives restart (persisted with the run).

## 3. Provider-side honesty

`provider_cancel_transition(provider_cancel_confirmed, evidence)`:

- only `provider_cancel_confirmed == True` **and** non-empty evidence →
  `CANCELLED`;
- otherwise the run stays observable (`WAITING_PROVIDER`) — the engine never
  asserts the provider job stopped.

The engine's `cancel()` applies the same rule: with confirmed+evidence the run
goes `CANCELLED`; without it an active provider run goes `WAITING_PROVIDER`.

## 4. Scheduling stop

A cancelled run yields zero ready steps (`SchedulerFacts.cancelled`), and
`engine.advance()` short-circuits on any cancellation entry — no new
scheduling and no gating transitions are attempted (no crash on a cancelled
`WAITING_PROVIDER` run).

## 5. Artifact publish

`artifact_publish_allowed(cancel_requested)` returns `False` when cancel was
requested — completed artifacts keep provenance but are not auto-published.

## 6. Completeness guard

`ensure_cancellable` rejects cancelling a `COMPLETED` run (archive instead).

## 7. Evidence

- `artifacts/video_production/phase_17/cancellation_receipt.json`
