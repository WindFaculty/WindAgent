# Reconciliation Policy

Phase 25 (plan 07 §9.2) — how WindAgent reconciles truth sources after a
failure, and the ordering guarantee.

## 1. Truth-source order

The reconciler processes truth sources in this exact order:

```text
durable WindAgent intent/checkpoint
→ provider observable state
→ downloaded artifact/validation state
→ event/outbox state
→ cost ledger
→ workflow transition
```

A later source NEVER overrides an earlier one for the same fact: the durable
intent and provider observation win; UI/file existence is never used to infer
completion.

## 2. Rules

1. **Never infer COMPLETED from a file existing or a UI having shown a
   result.** Completion requires the durable state transition AND the
   provider observable state (CH02).
2. **Never blind-resubmit.** When the provider cannot confirm a pending
   external operation, the run lands in `RECONCILE_UNKNOWN` →
   `WAITING_PROVIDER` (manual/observable), never a resubmit (CH01, CH15).
3. **Order of application** for recovery decisions
   (`ProductionRecovery.decide`):
   - no checkpoint → safe fresh attempt (nothing submitted);
   - checkpoint, no pending op → safe fresh attempt (not yet submitted);
   - checkpoint + pending op + inspector available:
     - COMPLETED → resume ingestion (no resubmit);
     - GENERATING → reattach/poll (no resubmit);
     - FAILED → bounded new attempt within retry budget;
     - UNKNOWN → reconcile/pause.
4. **Download retries** are bounded and never resubmit
   (`decide_download_retry`, CH03/CH06).
5. **Stale revisions** block dependent work: a revision-hash change stales
   approvals/artifacts (`decide_revision_change` → `STALE_REVISION_BLOCK`).
6. **Cost ledger reconciliation** is append-only and dedup-key idempotent:
   replaying a provider result never double-debits (CH08/CH12).

## 3. Implementation

- `ProductionWorkflowEngine.recover()` / `recover_download()` apply
  `RecoveryDecision` from the durable checkpoint;
- `FlowJobRegistry.reconcile()` applies the same never-blind-resubmit policy
  for browser/provider jobs (CH05/CH15);
- the outbox journal guarantees an event is only published after the state
  commit lands (single atomic write, CH11).

## 4. Verification

The Phase 25 gate verifies reconciliation by checking every scenario receipt's
observed expectations, the duplicate side-effect audit (observed == 0) and the
soak report (no duplicate events across repeated runs).
