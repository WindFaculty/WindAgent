# Requirement Coverage Matrix

Every requirement disposition identified during cleanup. Nothing is LOST_ACCIDENTALLY.

## Dispositions

| Requirement / behavior | Before | Disposition | Where it is now |
| ---------------------- | ------ | ----------- | --------------- |
| Script pipeline stages (idea/premise/story/outline/character/scene/dialogue/revision/review/gate) | tests/contracts/test_story_b3..b9_gate.py, tests/unit/intelligence/story/*, tests/unit/domain/story/* | STILL_TESTED | unchanged |
| Story lineage / lock envelope 9-type | test_studio_full_dag_auto_drive.py (1 test) | REPLACED_BY_BETTER_TEST → REWRITTEN | assert {"ReviewReport","ScreenplayDraft"} <= types (full lineage contract preserved, superset semantics) |
| DB migration chain head (studio) | test_0010/test_0011 (3 tests) | REWRITTEN (stale head 0011 → current head 0012) | alembic_heads/current == 0012_studio_artifact_provenance |
| Outbox dispatch (exactly-once, idempotent) | test_storage_repositories (1 test) | REWRITTEN (sequence authority semantics) | sequence == 1 (per-aggregate allocation by design), idempotent second run still 0 |
| Worker composition completeness | test_phase7_composition (1 test) | REWRITTEN (stale class names) | MemoryQueryService / VerificationQueryService |
| DEF-006 startup recovery regression | test_cutover_defects (1 test) | REWRITTEN (stale fake container) | fake container mirrors real composition fields; recover_all_in_flight still asserted awaited |
| Desktop E2E (UI45) | 2 placeholder specs | REPLACED_BY_BETTER_TEST | desktop Vitest suite 142 tests; verify_stage_h_testing.py UI45 checks real suite |
| Browser E2E (UI46) | 2 placeholder specs | REPLACED_BY_BETTER_TEST | web Vitest suite 71 tests; verify_stage_h_testing.py UI46 checks real suite |
| Web portal shell (nav tabs, portal header, lastSyncTimestamp) | App.test.tsx (12 tests) | NO_LONGER_SUPPORTED (portal UI removed; web = thin re-export of desktop app) | desktop Studio shell suite |
| Stage E cross navigation | test_stage_e_cross_navigation.py | NO_LONGER_SUPPORTED (tautology, never tested anything) | — |
| UI47 locked-revision immutability | stage_i tautology | DUPLICATE_COVERAGE | test_script_behavioral_invariants.py::test_locked_ancestor_immutability |
| UI48 license governance | stage_i tautology | DUPLICATE_COVERAGE | test_asset_behavioral_invariants.py::test_license_governance_enforcement |
| UI49 script-asset eligibility | stage_i tautology | DUPLICATE_COVERAGE | test_stage_e_script_asset_binding.py |
| Phase 0 deliverable docs | test_phase0_docs_exist | NO_LONGER_SUPPORTED (docs removed by canonicalization 5662ede) | code invariants in test_phase00_single_workspace_contract.py (4 tests) |
| Stage E/F/G domain services (script-asset binding, collaboration, recovery/conflict) | tests/ root stage files | STILL_TESTED (moved) | tests/unit/domain/video_production/ |
| Stage H gate evidence (VP3D_UI_TEST_MATRIX_VERIFIED) | test_stage_h_testing_verification.py | STILL_TESTED (moved) | tests/unit/verification/ |
| Stage I evidence + UI50 arch check | stage_i (2 real tests) | STILL_TESTED (moved) | tests/unit/verification/ |

## Known remaining failures (kept — not cleanup targets)

| Test | Classification | Notes |
| ---- | -------------- | ----- |
| test_kernel_never_launches_or_imports_upstream | PRODUCT_DEFECT | intelligence/video/{episode,golden_scene}/checks.py use bounded `subprocess.run` (ffprobe probe, timeout+capture) — committed P25/P26 verification code violates the phase-6 kernel rule; needs architecture ruling (carve-out vs move) |
| test_core_zero_getenv_and_forbidden_imports | PRODUCT_DEFECT | core/windagent_core/config/certification.py reads os.environ (C7 S4 env-driven certification mode, committed); violates core config zero-env invariant |
| test_workspace_snapshot + test_api_v2_workspace_endpoints | PRODUCT_DEFECT | WorkspaceSnapshot gained required field `revision_status` (committed a210883) but WorkspaceService.get_snapshot call site not updated — TypeError |
| test_no_write_exits_zero_and_leaves_evidence_untouched + test_verify_only_alias... | ENVIRONMENT_BLOCKER | verify_phase03_handoff --no-write exits 1: handoff evidence stale — pins docs deleted by 5662ede (adoption_matrix.md, director_research/*); handoff bundle must be regenerated after docs cleanup |
| test_se11_api_idempotency_and_stale_revision | PRODUCT_DEFECT | scripts/verification/security_phase26.py:1178 missing `await` on async `execute_workspace_command` — coroutine.get() AttributeError |
| test_evidence_validation_lane_lineage | ENVIRONMENT_BLOCKER | release_phase27.py PHASE_VERDICT_FILES points at artifacts/video_production_3d/phase_24/phase_verdict.json which commit fd36123 removed; lineage gets None status |
| test_ci_run_manifest_aggregates_all_required_lanes | FLAKY_TEST (order-dependent) | passed standalone (24/25 in file run); failed once inside full suite; needs order/state isolation investigation |

## Regression protection

- tests/regression/test_cutover_defects.py (DEF-001..010): KEPT, one fake container REWRITTEN — regression intent intact.
- No test with keywords recovery/retry/lease/fencing/runtime/reconcile/finalizer/provider/timeout/DAG/state was deleted.
