# Flow Durable Job & Idempotency Contract (Phase 14)

**Gate:** `VP14_FLOW_IMAGE_GENERATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §18.2 / §22–§23
**Location:** `tools/windagent_tools/google_flow/job_record.py`

## 1. Purpose

Every generation job is a durable `FlowJobRecord` persisted to JSON under
`{state_dir}/flow_jobs.json` BEFORE the submit click (plan 04 §18.2:
"record action/job before or atomically with submit intent"). Repeated
commands and crash recovery reconcile against the registry and **never
blind-resubmit**.

## 2. Record shape

```text
generation_id
project_id / revision_id / shot_id
provider                    (google_flow_browser)
request_hash                (idempotency key component)
submitted_at
browser_session_id
flow_project_id
status
attempt                     (1-based; retries increment)
parent_generation_id        (causal link for re-generation, §18.4)
candidate_ids
```

## 3. Statuses (plan 04 §22 subset)

```text
PREPARED · SUBMITTING · GENERATING · RESULT_READY · DOWNLOADING · COMPLETED
FAILED_RETRYABLE · FAILED_TERMINAL · UNKNOWN_REQUIRES_RECONCILIATION
HUMAN_ACTION_REQUIRED · CANCELLED
```

## 4. Reconciliation matrix (plan 04 §23.1)

```text
lookup request_hash + provider + project mapping
├── COMPLETED                → REUSE_COMPLETED (candidate set intact)
├── active (SUBMITTING/GENERATING/RESULT_READY/DOWNLOADING) → RESUME_ACTIVE
├── UNKNOWN / terminal       → RECONCILE_UNKNOWN — never blind resubmit
├── failed retryable + budget → NEW_ATTEMPT (attempt+1, parent link)
└── missing                  → CREATE_PREPARED
```

`FlowJobRegistry.reconcile()` returns a `FlowReconcileDecision`; the
generator raises `FlowSubmitReconciledError` for `RECONCILE_UNKNOWN`.

## 5. Contract

- `SUBMITTING` intent is persisted before the click; evidence is recorded
  right after the observable transition. A crash between the two always
  lands in reconciliation.
- `next_attempt()` creates attempt+1 with `parent_generation_id` set
  (causal link kept — re-generation never overwrites the prior receipt).
- Status strings coerce back to the enum on reload.
