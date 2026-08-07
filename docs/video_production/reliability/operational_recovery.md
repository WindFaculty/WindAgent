# Operational Recovery

Phase 25 (plan 07 §9.3, §26) — recovery objectives, observed baselines, and
operational procedures.

## 1. Recovery objectives (plan §9.3)

Before any recovery test, each scenario pins down:

- **max detection time / attempts** — observed per scenario in
  `recovery_timing_report.json` (`detection_time_ms` / `recovery_time_ms`);
- **safe expected state** — recorded in each receipt's `post_state`;
- **self-recovery vs human recovery** — typed outcome:
  - self: reattach/reconcile (CH01–CH03, CH11–CH14);
  - human: login/CAPTCHA/account challenge (CH04, CH09);
  - terminal/manual: project deleted, cancel unconfirmed (CH10, CH15);
- **allowed data loss** — durable state is never lost (I1);
- **cleanup requirement** — no temp/`.tmp` residue (soak leak check).

## 2. Observed baselines — no claimed RTO

The plan forbids publishing a single RTO without measurement. Phase 25 records
**observed** detection/recovery times per scenario as a release baseline; a
general RTO is only claimed after controlled live measurement (plan §27).

## 3. Soak / repeat (plan §9.4)

`soak_test_report.json` records repeated mocked production workflows:

- 20+ iterations by default (`MIN_SOAK_ITERATIONS = 10`);
- no duplicate outbox events across runs;
- all runs reach a terminal state;
- no leaked temp/state files;
- flaky races are classified (never silently closed).

Live Flow is not used for frequent soak; nightly/manual runs use bounded
credits (plan §20.2).

## 4. Operational procedures (plan §26)

### 4.1 Pre-flight

- backup/migration plan ready before release;
- browser runtime/profile setup documented;
- Flow login/takeover procedure (human states, CH04/CH09);
- credit/budget configuration enforced by `GenerationBudgetPolicy` (CH08).

### 4.2 During an incident

1. Open the circuit (`ProviderCircuitBreaker`) for duplicate-cost / account /
   artifact-corruption risk before any new run.
2. Pause/disable the Flow provider via feature flag/composition option —
   evidence and project data are never deleted.
3. Let the active run pause/reconcile; never blind-resubmit.

### 4.3 Recovery actions

- **Process killed** → new worker reconciles the same job (CH01).
- **Browser killed** → workflow pauses, reattach/inspect (CH02).
- **Network lost** → bounded retry, durable state (CH03).
- **Session/CAPTCHA** → human action required, safe resume (CH04/CH09).
- **Credits exhausted** → circuit open, workflow paused, ledger reconcile
  (CH08).
- **Cancel requested** → stop scheduling, reconcile external truth (CH10).
- **DB restart** → atomic replay idempotent (CH11).
- **Project deleted** → terminal/manual decision, never auto-replace (CH15).

### 4.4 Rollback / disable

- feature flag to stop the Flow provider without deleting project/artifact
  evidence;
- active runs pause and reconcile;
- API/provider port remains for future providers;
- no unsafe database downgrade.

## 5. Incident observation (plan §29)

Post-release, monitor browser/session health, selector drift, generation
success/failure/retry, duplicate prevention, human-action frequency, cost
estimate-vs-observed, recovery time and storage growth — feeding the next
release cycle.
