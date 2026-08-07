# Phase 17 — Durable Production Workflow: Recovery Contract

- **Gate:** `VP17_DURABLE_WORKFLOW_VERIFIED`
- **Plan:** `docs/video_production/plans/05_phase_17_20_orchestration_cost_review.md` §8.5
- **Module:** `orchestration/windagent_orchestration/production/recovery.py`

## 1. Principle

> Recovery always inspects durable state AND the provider before retrying.
> "file exists" is never the only decision.

`ProductionRecovery.decide(checkpoint)` is a pure, side-effect-free decision
function. The caller injects an `inspect_provider(request_hash, external_id)`
callback so the gate runs offline with fakes.

## 2. Decision matrix

| Checkpoint state                                   | Decision                         |
|----------------------------------------------------|----------------------------------|
| No checkpoint (crash before any durable write)     | `NEW_ATTEMPT` (safe)             |
| Checkpoint, no pending external op                 | `NEW_ATTEMPT` (not submitted)    |
| Pending op, no inspector available                 | `RECONCILE_UNKNOWN` (never resubmit) |
| Pending op, provider says COMPLETED                | `RESUME_AFTER_INSPECTION`        |
| Pending op, provider says GENERATING               | `REATTACH_WAITING_PROVIDER`      |
| Pending op, provider says FAILED                   | `NEW_ATTEMPT` (bounded)          |
| Pending op, provider says UNKNOWN                  | `RECONCILE_UNKNOWN`              |

Key invariant: with a pending external operation, the provider is always
inspected; without a confirmed outcome the run stays observable
(`WAITING_PROVIDER`) — **no blind resubmit**.

## 3. Download retry

`decide_download_retry` retries the download within a bounded budget
(`max_download_retries`) without resubmitting; exhausting the budget moves the
run to `FAILED` (`FAIL_TERMINAL`).

## 4. Revision change

`decide_revision_change(expected_hash, actual_hash, dependent_artifacts)`:

- unchanged hash → dependents remain valid;
- changed hash → `STALE_REVISION_BLOCK` (run → `WAITING_APPROVAL`); dependent
  artifacts/approvals are marked stale.

## 5. Single-shot failure

`single_shot_failure_keeps_siblings(successful, failed_shot)` preserves
successful sibling shots when one shot fails — a single failure never loses
successful work.

## 6. Evidence

- `artifacts/video_production/phase_17/recovery_receipt.json`
