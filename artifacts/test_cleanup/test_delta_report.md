# Test Delta Report — Before vs After Cleanup

Repository: WindAgent
Branch: chore/cleanup-stale-md-docs
HEAD: 40bb97c87f7e2e63cb35352ed0b4a8a0d25ada5d

| Metric          | Before | After | Delta |
| --------------- | -----: | ----: | ----: |
| Python test files | 300 | 299 | -1 (test_stage_e_cross_navigation.py deleted; 5 moved) |
| Frontend test files | 35 | 30 | -5 (4 e2e placeholder specs + App.test.tsx) |
| Python collected | 3654 | 3649 | -5 |
| Web tests collected | 83 | 70 | -13 (App.test.tsx) |
| Desktop tests collected | 142 | 142 | 0 |
| Frontend package tests collected | 59 | 59 | 0 |
| Python passed | 3373 | 3406 | +33 |
| Python failed | 17 | 8 | -9 (7 fixed by rewrite, 1 deleted, 1 flaky passed) |
| Python skipped | 5 | 5 | 0 |
| Web passed | 71 | 70 | -1 (13 tests in deleted file, 12 of which were FAILING) |
| Desktop passed | 142 | 142 | 0 |
| Packages passed | 59 | 59 | 0 |
| Fixtures | 16 tracked (6 fakes + 10 fixture dirs) | 16 | 0 |
| Duplicate tests | 0 confirmed | 0 | 0 |

## Every count decrease explained

- Python -5 collected: 1 tautology file (test_stage_e_cross_navigation.py),
  3 stage-i tautology tests, 1 doc-deliverable test whose deliverables were
  removed by docs canonicalization (5662ede). All justified in
  deletion_justification.md.
- Web -13: apps/web/src/app/__tests__/App.test.tsx (old portal UI suite;
  12 failing + 1 passing, all asserting UI removed from production).
- Python files -1: one file deleted; 5 files moved (3 stage domain tests to
  tests/unit/domain/video_production/, 2 stage verification tests to
  tests/unit/verification/) — moves do not change counts.

## Rewrites (7 tests across 6 files)

- tests/unit/storage/migrations/test_0010_studio_persistence_migration.py — head 0011 → 0012
- tests/unit/storage/migrations/test_0011_studio_run_nodes_migration.py — head 0011 → 0012 (2 tests)
- tests/unit/orchestration/test_studio_full_dag_auto_drive.py — lock envelope: exact set → superset (9-type lineage contract)
- tests/unit/storage/test_storage_repositories.py — outbox sequence 10 → 1 (per-aggregate allocation by design)
- tests/unit/test_phase7_composition.py — MemoryService/VerificationService → MemoryQueryService/VerificationQueryService
- tests/regression/test_cutover_defects.py — DEF-006 fake container gains studio_* fields

## Test config changes

- scripts/verification/verify_stage_h_testing.py — UI45/UI46 existence checks
  re-pointed from deleted placeholder specs to the real desktop/web Vitest suites.

## Remaining failures (all kept, none deleted for being red)

See requirement_coverage_matrix.md "Known remaining failures": 2 product defects
(kernel subprocess rule, core certification env), 2 product defects (workspace
snapshot revision_status x2 tests), 2 environment blockers (handoff evidence
stale vs docs cleanup), 1 product defect (security_phase26 missing await),
1 environment blocker (phase24 VP3D verdict removed by fd36123), 1 flaky
(ci_run_manifest, order-dependent).
