# Phase 17 — Durable Production Workflow: Approval Gate Contract

- **Gate:** `VP17_DURABLE_WORKFLOW_VERIFIED`
- **Plan:** `docs/video_production/plans/05_phase_17_20_orchestration_cost_review.md` §8.2
- **Module:** `orchestration/windagent_orchestration/production/approvals.py`,
  `orchestration/windagent_orchestration/production/engine.py`

## 1. Approval gates

Seven canonical gates (plan 05 §8.2):

```text
CONCEPT_APPROVAL
SCREENPLAY_APPROVAL
CHARACTER_APPROVAL
LOCATION_APPROVAL
SHOT_PLAN_APPROVAL
COST_APPROVAL
FINAL_CUT_APPROVAL
```

## 2. Revision/hash binding (fail-closed)

Every `ProductionApproval` points at an exact `revision_id` + `target_hash`
(64-hex content hash) plus actor, role, decision and reason.

The engine (`approve`) enforces:

1. `target_hash` must equal the run's **current** `revision_hash` — an
   approval for any other hash is rejected
   (`WINDAGENT_ERR_APPROVAL_TARGET`).
2. `revision_id` must equal the run's current revision
   (`WINDAGENT_ERR_APPROVAL_TARGET`).
3. If an approval already exists for this gate on a **different** hash, a new
   approval is rejected (`WINDAGENT_ERR_STALE_APPROVAL`) — the stale approval
   is never reused for the new target.

## 3. Gate satisfaction uses the CURRENT hash only

`ProductionWorkflowEngine.ready_step_ids` builds the approved-gate set from
`ApprovalLedger.has_current_approval(gate, revision_id, target_hash)` for the
run's current revision/hash. A stale approval (recorded for an old hash)
**never** re-opens a gate, even if the same gate was approved earlier.

## 4. Idempotency

`ApprovalLedger.record` is idempotent: a duplicate
(gate, revision_id, target_hash, actor, decision) is not re-appended. The
ledger is append-only for audit.

## 5. Resume semantics

The run resumes from `WAITING_APPROVAL` to `RUNNING` only when **no pending
gates remain** (`_pending_gates` is empty) — approving a duplicate or a gate
the run is not waiting on never resumes the run prematurely.

## 6. Evidence

- `artifacts/video_production/phase_17/approval_gate_receipt.json`
