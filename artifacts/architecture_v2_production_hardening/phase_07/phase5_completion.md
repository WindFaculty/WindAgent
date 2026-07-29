# Phase 5 — CI Matrix Completion Report

> **PROVISIONAL / LOCAL-ONLY.** This report is not authoritative promotion
> evidence until GitHub Actions completes on the exact clean candidate SHA.

## Verdict

```text
CI_IMPLEMENTATION_COMPLETE_LOCAL
REMOTE_VERIFICATION_PENDING
```

## Local gate assessment

| Gate | Local status | Evidence |
|---|---|---|
| Workflow syntax | PASS | `actionlint` reports no workflow errors |
| Required matrix | PASS | Policy tests verify exactly 14 jobs and the finalizer depends on the other 13 |
| Fail-closed behavior | PASS | No mandatory `continue-on-error` or exit masking |
| PostgreSQL integration | PASS (definition) | PostgreSQL 16 service, health check, async driver URL and dialect/schema preflight |
| Windows execution | PASS (definition) | Windows jobs explicitly use `pwsh` |
| Reproducible frontend installs | PASS | Web and desktop use tracked lockfiles with `npm ci` |
| Runtime/version gate | PASS | Fail-closed installed-package and CLI/API/worker version smoke passes locally |
| Evidence aggregation | PASS (implementation) | Final validator checks job conclusions, candidate SHA, receipt schemas and exact log hashes |
| Hosted execution | PENDING | No GitHub Actions run exists for a final candidate SHA |
| Branch protection | PENDING | Required checks have not been verified in repository settings |

## Required jobs

1. `artifact-protocol`
2. `version-consistency`
3. `architecture-boundaries`
4. `python-unit-sqlite`
5. `python-unit-windows`
6. `python-integration-sqlite`
7. `python-integration-postgres`
8. `runtime-smoke`
9. `cli-contract`
10. `web-test`
11. `web-test-windows`
12. `desktop-test`
13. `desktop-test-windows`
14. `final-evidence`

The same names must be configured as required checks for the protected target
branch.

## Local verification snapshot

- Workflow policy/version/CI-evidence tests: `17 passed`.
- Combined workflow and authoritative-pointer policy set: `53 passed`.
- Latest Phase 0-5 regression set: `271 passed, 1 skipped`.
- Full unit run in the local pipeline: `771 passed, 1 skipped`.
- Integration suite: `21 passed`.
- Web: `83 passed`, typecheck and production build passed.
- Desktop: `89 passed`, TypeScript check and production build passed.
- Runtime version smoke and version consistency check passed.

## Remaining completion actions

1. Prepare a clean candidate commit and generate evidence for its exact SHA.
2. Push the candidate and let all 14 jobs run without rerunning only a subset.
3. Download and validate all job evidence with
   `scripts/verification/validate_ci_evidence.py`.
4. Verify branch protection requires all 14 checks.

Only then may this report transition from provisional to authoritative PASS.
