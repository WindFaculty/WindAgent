# B8 Evidence — LOCKED_SCREENPLAY_GATE

Gate owner: Plan B. Baseline: B1 review/lock models + validators, B7 review
thresholds + iteration budget, A6 hash-bound approval/lock command
(`LockScreenplayCommand`, `derive_revision`), C5 hash-bound lock UI.
Fixtures: `fixtures/studio_contract_v0.1/story_lock/` (golden + corpus).

## 1. Deterministic lock policy (versioned, provider-free)

- Policy `lock_policy/v1`: the A-issued `LockedScreenplayReceipt` is
  the authority; assembly refuses unless: state is `READY_FOR_PRODUCTION`,
  receipt binds the target draft, approval mode is one of
  ['AUTO', 'HUMAN_REQUIRED', 'QUALITY_GATE_ONLY'], `HUMAN_REQUIRED` binds a policy id, the review
  verdict is PASS/PASS_WITH_WARNINGS with no blocking findings, `AUTO`
  requires a clean PASS, the iteration budget is not exceeded, and the
  lineage covers every required artifact type.
- Hash binding: the A ref hash of draft/report/receipt must equal the live
  canonical content hash — a post-lock mutation is refused (`HASH_MISMATCH`)
  and requires a derived revision instead. The package is assembled from
  immutable refs only, never copied mutable state (rule 7), and reassembles
  byte-identically (idempotent double lock).

## 2. Golden lock trace (Vietnamese rabbit/kite, 240s, 11-artifact lineage)

- **AUTO** — receipt `rcpt_auto_draft_rabbit_kite` (policy `—`), package `pkg_rcpt_auto_draft_rabbit_kite_draft_rabbit_kite`, 11 manifest refs, hash `012e7bfffc7528aa…`, idempotent=True.
- **HUMAN_REQUIRED** — receipt `rcpt_human_required_draft_rabbit_kite` (policy `approval_policy_v1`), package `pkg_rcpt_human_required_draft_rabbit_kite_draft_rabbit_kite`, 11 manifest refs, hash `2a258ccfce33c368…`, idempotent=True.
- **QUALITY_GATE_ONLY** — receipt `rcpt_quality_gate_only_draft_rabbit_kite` (policy `—`), package `pkg_rcpt_quality_gate_only_draft_rabbit_kite_draft_rabbit_kite`, 11 manifest refs, hash `b9f6c46f42628945…`, idempotent=True.

- Every package passes `validate_locked_package` with the issued receipt and
  exposes a presentation-safe `to_summary()` (manifest count + types).

## 3. Negative corpus results (real LockService)

| Case | Outcome | Refusal codes |
|---|---|---|
| `missing_approval` | `refused` | `LOCK_STATE` |
| `stale_receipt_draft` | `refused` | `RECEIPT_DRAFT_MISMATCH` |
| `unknown_approval_mode` | `refused` | `APPROVAL_MODE` |
| `human_required_without_policy` | `refused` | `APPROVAL_POLICY` |
| `auto_with_warnings` | `refused` | `APPROVAL_MODE` |
| `review_not_pass` | `refused` | `REVIEW_THRESHOLD` |
| `stale_review_draft` | `refused` | `REVIEW_STALE` |
| `iteration_budget_exhausted` | `refused` | `REVISION_BUDGET` |
| `incomplete_lineage` | `refused` | `MANIFEST_MISSING_REF` |
| `duplicate_lineage_ref` | `refused` | `MANIFEST_DUPLICATE` |
| `hash_mismatch_report` | `refused` | `HASH_MISMATCH` |
| `post_lock_edit_rejection` | `refused` | `HASH_MISMATCH` |
| `concurrent_lock_revision` | `refused` | `HASH_MISMATCH,RECEIPT_DRAFT_MISMATCH,REVIEW_STALE` |

## 4. Handler surface

- Registered B8 handler: `studio.story.lock` (ScreenplayDraft + ReviewReport
  -> LockedScreenplayReceipt + LockedScreenplayPackage) — matches
  `story_task_io.json`; the A atomic `READY_FOR_PRODUCTION` transition is
  requested by A's orchestrator command (`LockScreenplayCommand`, hash-bound
  with optimistic version), and the A-issued receipt is accepted as authority.
- No storage/queue/API/provider imports in the handler; lock assembly is
  deterministic and provider-free.

## 5. No tolerant free-text parsing on canonical paths

Tolerant-parser scan (reused from B2 over `core/.../domain/story/`,
`intelligence/.../story/`, incl. review + runtime_handlers):
**0 violation(s)**.

## 6. Gate verdict

**`LOCKED_SCREENPLAY_GATE`: PASS (B-side evidence).**

- Golden: `lock_golden.json` (checksum `c15cb58c349a49fd…`)
  — valid immutable package + receipt under all three approval modes.
- Corpus: `invalid_lock_results.json` (checksum
  `958c17e8648c3adc…`);
  checksums: `checksums.json`.
- A-side (atomic lock transition, optimistic version, post-lock read-only
  UI) and C-side (receipt/package display fields) halves are co-signed by
  their plan owners at contract review.
