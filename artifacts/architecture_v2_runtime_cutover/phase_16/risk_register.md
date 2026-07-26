# Phase 16 Risk Register

| ID | Severity | Classification | Evidence | Required action |
|---|---|---|---|---|
| P16-001 | P0 | implementation/test-suite defect | Full pytest: 58 failed, 667 passed, 2 skipped | Resolve every failure or formally remove stale baseline tests through an reviewed policy change; rerun the complete suite |
| P16-002 | P0 | implementation defect | Migration suite has 21 failures covering checksum, lock, backup, registry, and legacy-data integrity | Repair migration utilities and schema/fixture contract drift, then repeat migration, rollback, and restore rehearsals |
| P16-003 | P0 | implementation defect | Phase 12 doctor: 4 failed, 4 passed; API/CLI dependency-bundle parity fails | Implement profile/component arguments, stable invalid-invocation exit code 3, and shared bundle behavior |
| P16-004 | P0 | release blocker | Worktree was already dirty before Phase 16 artifacts; remote branch does not exist | Reconcile and commit intended changes, rerun from a clean clone, then publish the audited SHA |
| P16-005 | P1 | implementation defect | Desktop: 4 failed, 85 passed | Fix sequence monotonicity, permission idempotency, session switching, and refresh recovery |
| P16-006 | P1 | packaging/test harness defect | Web `npm test` cannot find `vitest` | Declare and lock the test runner, install from the lockfile, and rerun |
| P16-007 | P1 | test policy drift | Phase 0 reproduction tests still assert that repaired defects must occur | Convert the baseline-only reproductions into archived evidence or invert them into regression assertions |
| P16-008 | P1 | test/runtime contract drift | Six legacy integration tests expect active endpoints that now return HTTP 410 | Decide and encode the compatibility policy consistently in routes and tests |
| P16-009 | P2 | lifecycle contract debt | API shutdown still uses runtime `hasattr` probing for closeability | Replace probing with the declared lifecycle contract from Phase 1 |
| P16-010 | P2 | harness reliability defect | Isolation scripts can print SUCCESS after a native `uv`/Python failure because native exit codes are not checked | Check `$LASTEXITCODE` after every native command and fail closed |

No unresolved sandbox error was used as a reason to fail a functional gate: package isolation and full pytest were rerun with the required access.
