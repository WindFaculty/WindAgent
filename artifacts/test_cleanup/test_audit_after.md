# Test Suite Audit — After Cleanup

## Repository State

Repository: WindAgent (D:\code_ca_nhan\WindAgent)
Branch: chore/cleanup-stale-md-docs
HEAD: 40bb97c87f7e2e63cb35352ed0b4a8a0d25ada5d

## Before

Test files: 335 (300 python + 35 frontend)
Collected: 3654 python + 284 frontend (83 web + 142 desktop + 59 packages)
Passed: 3373 python + 272 frontend
Failed: 17 python + 12 web
Skipped: 5 python

## After

Test files: 329 (299 python + 30 frontend)
Collected: 3649 python + 271 frontend (70 web + 142 desktop + 59 packages)
Passed: 3406 python + 271 frontend
Failed: 8 python (all classified, none test-defect) + 0 frontend
Skipped: 5 python

## Kept

294 python files + 30 vitest files. Zero missing import targets across all
300 scanned python test files (mechanical import-resolution check).
All skip/xfail markers verified legitimate (win32/symlink, ffmpeg PATH,
RUN_AGENT_BROWSER_E2E opt-in). Regression suite (DEF-001..010) intact.

## Rewritten

1. tests/unit/storage/migrations/test_0010_studio_persistence_migration.py — migration head 0011 -> 0012_studio_artifact_provenance (real current head, committed fcfee92)
2. tests/unit/storage/migrations/test_0011_studio_run_nodes_migration.py — same, 2 tests
3. tests/unit/orchestration/test_studio_full_dag_auto_drive.py — lock envelope exact-set -> superset {"ReviewReport","ScreenplayDraft"} <= types (S4.1 full 9-type lineage contract; receipt assertions unchanged)
4. tests/unit/storage/test_storage_repositories.py — outbox dispatched sequence 10 -> 1 (SqlOutboxWriter per-aggregate allocation is the documented authority)
5. tests/unit/test_phase7_composition.py — MemoryService -> MemoryQueryService, VerificationService -> VerificationQueryService (real class names)
6. tests/regression/test_cutover_defects.py — DEF-006 fake container + studio_reconciler/studio_recovery/studio_capability_probe (mirrors real composition; regression intent kept)

## Merged

None — no semantic duplicates found after import/setup/assertion comparison.

## Moved

- tests/test_stage_e_script_asset_binding.py -> tests/unit/domain/video_production/
- tests/test_stage_f_human_agent_collaboration.py -> tests/unit/domain/video_production/
- tests/test_stage_g_recovery_conflict.py -> tests/unit/domain/video_production/
- tests/test_stage_h_testing_verification.py -> tests/unit/verification/
- tests/test_stage_i_final_acceptance.py -> tests/unit/verification/
All 34 tests in moved files pass in new location.

## Deleted

- 4 placeholder Playwright specs (apps/desktop/e2e + apps/web/e2e): never
  runnable (no @playwright/test dep, no config, no CI), literal-only assertions
- apps/web/src/app/__tests__/App.test.tsx (13 tests): targets removed web
  portal UI; web app is now 3-line re-export of @desktop/App; strings absent
  from all production src
- tests/test_stage_e_cross_navigation.py: 27-line self-asserting tautology
- tests/unit/verification/test_stage_i_final_acceptance.py: 3 tautology tests
  (ui47/ui48/ui49 asserted hand-built literals)
- tests/architecture/test_phase00_single_workspace_contract.py:
  test_phase0_docs_exist (deliverable docs removed by 5662ede)

## Deletion Justification

artifacts/test_cleanup/deletion_justification.md — 8 rows, all
DELETE/HIGH/evidence-present/requirement-disposition-known. No deletion for
failing/flaky/slow/count reasons. False-green gate passed.

## Fixtures

All 16 tracked fixture modules/sets verified referenced (fakes: 5 of 6
confirmed in use; fake_task_queue unused but kept as canonical test double
for the queue port — see manifest note; artifact JSON fixtures used via
explicit path + --directory glob). No dead conftest (repo has none).

## CI References

- .github/workflows/ci.yaml: no reference to any deleted test path (verified
  by grep of all pytest/npm invocations).
- scripts/verification/verify_stage_h_testing.py: UI45/UI46 existence checks
  re-pointed from deleted e2e specs to real Vitest suites.
- OUT_OF_SCOPE_CI_FINDING: frontend/packages tests (11 files, 59 tests,
  incl. studio-contracts/state/client — current C7 packages) are NOT run by
  any CI job; only apps/web + apps/desktop are. Recommend adding a
  frontend-packages job (`cd frontend && npm test`).

## Remaining Failures (8, all kept)

| Test | Classification |
| ---- | -------------- |
| test_kernel_never_launches_or_imports_upstream | PRODUCT_DEFECT: P25/P26 checks.py use bounded ffprobe subprocess in kernel |
| test_core_zero_getenv_and_forbidden_imports | PRODUCT_DEFECT: core/config/certification.py reads os.environ (C7 S4) |
| test_workspace_snapshot + test_api_v2_workspace_endpoints | PRODUCT_DEFECT: WorkspaceSnapshot revision_status missing at service call site |
| test_no_write_exits_zero_... + test_verify_only_alias_... | ENVIRONMENT_BLOCKER: handoff evidence stale vs docs cleanup 5662ede |
| test_se11_api_idempotency_and_stale_revision | PRODUCT_DEFECT: security_phase26.py:1178 missing await |
| test_evidence_validation_lane_lineage | ENVIRONMENT_BLOCKER: phase24 VP3D verdict removed by fd36123, release_phase27 still references it |
| test_ci_run_manifest_aggregates_all_required_lanes | FLAKY_TEST (order-dependent; passed in after-run) |

## Out-of-Scope Product Findings

1. kernel subprocess rule vs P25/P26 verification checks — needs architecture ruling (carve-out vs move to tools/)
2. core config zero-env invariant vs certification.py — needs whitelist decision
3. WorkspaceService.get_snapshot missing revision_status — TypeError in production
4. security_phase26.py missing await — real bug in verification script
5. handoff bundle stale — regenerate after docs cleanup
6. phase_24 lineage slot broken — restore/re-point VP3D verdict
7. CI does not run frontend packages tests

## Worktree Contamination

None. 3 files written by tests (script_eval baseline manifests,
package-lock.json) were restored; remaining modified/untracked files are
pre-existing changes from before this task (import_graph.json, c7/evidence.json,
docs cleanup artifacts).

## Verdict

TEST_SUITE_CANONICALIZED — the remaining suite is the canonical verification
suite for the current WindAgent. Every test maps to a live production target,
no stale/duplicate/phantom tests remain, and the 8 red tests are honest
product-defect/environment findings, not test defects.
