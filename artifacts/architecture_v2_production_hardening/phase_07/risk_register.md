# Phase 0-5 Repair — Risk Register

No statement that “all critical risks are closed” is valid while an OPEN or
PENDING_REMOTE P0/P1 entry remains below.

| ID | Risk | Priority | Current control | Status |
|---|---|---:|---|---|
| R11 | Artifact schema integrity | P0 | One canonical artifact schema referencing the receipt schema; semantic, candidate-SHA, hash and negative-fixture checks | `MITIGATED_LOCAL`: recursive production-root validation passes for all 18 JSON files |
| R12 | Evidence publication integrity | P0 | Validate-before-publish, immutable `runs/<id>`, atomic `latest.json`, failed runs isolated in quarantine | `PENDING_CANDIDATE`: implementation and tamper tests pass; no clean candidate bundle exists |
| R13 | Command receipt authenticity | P0 | Secrets redacted before persistence; stdout, stderr and combined hashes are recomputed from exact bytes | `PENDING_CANDIDATE`: local tests pass; final CI receipts do not yet exist |
| R14 | CLI architecture exit contract | P1 | Typed JSON failures and stable exits for violation, root missing, missing checker, crash and timeout | `MITIGATED_LOCAL`: architecture/regression suite passes |
| R15 | CLI runtime truthfulness | P1 | Read commands do not initialize schema; runtime-backed status/providers/replay/eval; explicit unavailable and mismatch states | `MITIGATED_LOCAL`: CLI contract and negative-path tests pass |
| R16 | Cross-platform CI integrity | P1 | 14-job fail-closed matrix; PowerShell on Windows; PostgreSQL health/dialect preflight; `npm ci`; final receipt aggregation | `PENDING_REMOTE`: workflow lint and policy tests pass, hosted jobs have not run |
| R17 | Candidate identity drift | P0 | Candidate SHA recorded in environment, bundles and final validator | `OPEN`: current worktree is dirty and is not a candidate |
| R18 | Required-check bypass | P1 | Documented exact required-check list | `OPEN`: repository branch-protection configuration has not been verified |

## Risk transition rules

- `MITIGATED_LOCAL` means implementation risk is covered by local tests; it
  does not authorize promotion.
- `PENDING_CANDIDATE` closes only when a clean immutable bundle validates for
  the exact candidate SHA.
- `PENDING_REMOTE` closes only from a successful GitHub Actions run on that
  candidate SHA.
- R11 may close for promotion only after the same recursive gate passes on the
  clean candidate; the current local mitigation is not remote evidence.
