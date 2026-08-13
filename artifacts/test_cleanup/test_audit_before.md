# Test Suite Audit — Before Cleanup

Repository: WindAgent (D:\code_ca_nhan\WindAgent)
Branch: chore/cleanup-stale-md-docs
HEAD: 40bb97c87f7e2e63cb35352ed0b4a8a0d25ada5d

## Test Frameworks

- Python: pytest 8.x (`uv run pytest`), asyncio_mode=auto, testpaths=["tests"]
- Frontend: Vitest (apps/web `npm test`, apps/desktop `npm test`, frontend root `npm test` workspace)
- E2E: none configured (no Playwright config, no @playwright/test dependency)

## Current Test Layout

- tests/architecture/ — 52 files, phase canonical + boundary invariants
- tests/contracts/ — 10 files, API/contract/story-gate freeze suites
- tests/integration/ — 15 files, E2E/multiprocess/chaos flows
- tests/regression/ — 1 file (test_cutover_defects.py, DEF-001..010)
- tests/unit/ — ~215 files, per-package unit suites (api/cli/core/domain/...)
- tests/root — 6 files (test_stage_e..i), orphan layout
- apps/*/e2e/ — 4 spec files, never collected
- apps/*/src + frontend/packages — 31 vitest files

## Collection Summary

- Python collected: 3654
- Frontend collected: 83 (web) + 142 (desktop) + 59 (packages) = 284

## Decision Matrix

Full per-file matrix generated in `_matrix.json` (335 rows). Default decision per file:
KEEP / HIGH — every test file maps to a live production target (verified: zero missing
import targets across all 300 python test files). Exceptions detailed below.

### Special rows

| File | Type | Target | Decision | Confidence | Reason |
| ---- | ---- | ------ | -------- | ---------- | ------ |
| apps/web/e2e/browser_golden_flow.spec.ts | E2E | none | DELETE | HIGH | Fake placeholder: imports @playwright/test (not installed), asserts literals, never collected (no config/CI), referenced only as existence-check by verify_stage_h_testing.py |
| apps/web/e2e/browser_negative_lanes.spec.ts | E2E | none | DELETE | HIGH | same as above |
| apps/desktop/e2e/desktop_golden_flow.spec.ts | E2E | none | DELETE | HIGH | same as above |
| apps/desktop/e2e/desktop_negative_lanes.spec.ts | E2E | none | DELETE | HIGH | same as above |
| apps/web/src/app/__tests__/App.test.tsx | UNIT | removed portal UI | DELETE | HIGH | Asserts UI text ("WindAgent V2 Architecture - Web Portal", TASKS/OVERVIEW/PROVIDERS tabs) absent from all production src; web App.tsx is now 3-line re-export of @desktop/App; current UI covered by desktop suite (142 tests) |
| tests/test_stage_e_cross_navigation.py | UNIT | none | DELETE | HIGH | 27-line tautology: asserts literal dict equals itself, no production import |
| tests/test_stage_i_final_acceptance.py (3 tests) | UNIT | none | DELETE | HIGH | test_ui47/48/49 assert hand-built literals (hash of literal, dict inequality); no production code exercised; behaviors covered by test_script_behavioral_invariants.py + test_asset_behavioral_invariants.py |
| tests/test_stage_i_final_acceptance.py (2 tests) | UNIT | check_video_workspace_architecture + produce_stage_i_evidence | REWRITE/MOVE | MEDIUM | real checks, but live in root-level file; see audit |
| tests/test_stage_e_script_asset_binding.py | UNIT | video_production domain services | MOVE | HIGH | real tests, wrong location (tests/ root) |
| tests/test_stage_f_human_agent_collaboration.py | UNIT | collaboration domain + API | MOVE | HIGH | real tests, wrong location (tests/ root) |
| tests/test_stage_g_recovery_conflict.py | UNIT | recovery/conflict domain + API | MOVE | HIGH | real tests, wrong location (tests/ root) |
| tests/test_stage_h_testing_verification.py | UNIT | stage_h gate verification | KEEP | HIGH | validates VP3D_UI_TEST_MATRIX_VERIFIED evidence bundle; currently passing; needs verify_stage_h_testing.py reference fix after e2e spec deletion |

## Fixture Inventory

- tests/fakes/ — 6 modules, all referenced by live tests
- tests/fixtures/ — artifacts + studio_contracts + video_production (incl. videoclaw_characterization golden fixtures) — all referenced
- No conftest.py in repo (fixtures are explicit imports) — no dead conftest
- No snapshot/golden drift found

## Known Pre-Cleanup Findings

1. 12 web tests failing (App.test.tsx) — stale portal-UI tests (see matrix)
2. 4 e2e specs are unexecutable placeholders
3. verify_stage_h_testing.py existence-checks the e2e specs (must update references)
4. frontend packages (11 test files) not wired into CI — OUT_OF_SCOPE_CI_FINDING
5. tests/integration/phase13/ empty dir (untracked leftovers)
