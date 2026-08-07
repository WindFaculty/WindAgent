# Recovery Invariants

Phase 25 (plan 07 §9.1) — the invariants every failure/chaos scenario must
satisfy, and the evidence files that prove them.

## 1. Invariant list

Every failure-injection scenario (see `failure_injection_runbook.md`) checks
ALL of the following:

| # | Invariant | Evidence source |
|---|---|---|
| I1 | project/revision/workflow state stays reachable and consistent after failure | `failure_injection_receipts/*.json` pre/post state |
| I2 | no duplicate generation / TTS / cost debit caused by WindAgent | `duplicate_side_effect_audit.json` (observed = 0) |
| I3 | approvals are never auto-generated and never reuse a wrong revision/hash | engine approval ledger checks (CH01–CH15 receipts) |
| I4 | an artifact `VALID/APPROVED` always exists and its hash matches the manifest | `evidence_manifest.json` (content-addressed) |
| I5 | outbox/event replay is idempotent | CH11/CH12 receipts; soak `duplicate_events_total == 0` |
| I6 | a stale worker never overwrites state | CH13/CH14 receipts (lease + version CAS) |
| I7 | human-required/error states carry a reason and evidence | CH04/CH09 receipts (human action records) |
| I8 | retry never exceeds the retry/credit budget | CH03/CH06/CH08 receipts |

## 2. How each invariant is enforced

- **I1 — durable aggregate**: `ProductionRunStore` writes each run state,
  checkpoint and outbox journal in ONE atomic write
  (`ProductionUnitOfWork.commit`); a restart (CH11) reloads the same file and
  the version/CAS guard preserves optimistic concurrency.
- **I2 — no duplicate side effects**: the engine persists the SUBMITTING
  intent BEFORE any provider side effect; a crash after submit lands in
  reconciliation (`ProductionRecovery`) which inspects the provider and never
  blind-resubmits. External result ingestion is idempotent by external id
  (CH12). The quota ledger is append-only and dedup-key idempotent (CH08).
- **I3 — approvals bound to revision/hash**: `ApprovalLedger.has_current_approval`
  requires the exact current `revision_id + target_hash`; stale approvals
  never re-open a gate (`ProductionWorkflowEngine.approve`).
- **I4 — artifact validity**: media is validated by real bytes and a real tool
  (`FfprobeVideoInspector` + `VideoInspectionPolicy`), and the content
  addressed `evidence_manifest.json` records per-file SHA-256.
- **I5 — idempotent replay**: `OutboxJournal.append`/`ingest_external_result`
  are dedup-key idempotent; `replay_pending` republishes nothing after an
  atomic commit (CH11).
- **I6 — stale-write rejection**: unexpired lease rejects another worker
  (CH13); on-disk version CAS rejects a stale writer (CH14).
- **I7 — human states typed**: human login/CAPTCHA/account challenges are
  typed `FlowHumanState` records with redacted evidence, reason and
  safe-resume state (CH04/CH09).
- **I8 — bounded budgets**: `ProductionRecovery.decide_download_retry` and
  `GenerationBudgetPolicy.can_submit` bound retries and credits; exhaustion is
  terminal, never a blind loop.

## 3. Fail-closed principle

A scenario is only "recovered" when the invariant assertions pass with REAL
observations. Missing evidence, placeholder hashes, or simulated media fail
closed — the Phase 25 verifier reports BLOCKED/FAILED, never PASSED.

## 4. Controlled environment receipts

Browser/session scenarios (CH02, CH04, CH05, CH09, CH15) must carry a
`controlled_environment` block describing the mock browser/account used; live
Flow is never used in PR CI (plan §4).
