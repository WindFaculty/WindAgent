# Deletion Justification

Repository: WindAgent
Branch: chore/cleanup-stale-md-docs
HEAD: 40bb97c87f7e2e63cb35352ed0b4a8a0d25ada5d

Every deletion below: Decision=DELETE, Confidence=HIGH, Evidence=PRESENT, Requirement disposition=KNOWN.
No test was deleted because it failed. No test was deleted to make the suite green.

| Deleted test | Requirement | Reason | Evidence | Replacement |
| ------------ | ----------- | ------ | -------- | ----------- |
| apps/desktop/e2e/desktop_golden_flow.spec.ts | UI45 "desktop E2E" | Placeholder spec: imports `@playwright/test` which is not a dependency of any package; no playwright.config exists; no CI job runs it; vitest include globs (`src/**/*.test.*`) exclude `e2e/`; body asserts hardcoded literals (`expect(appLoaded).toBe(true)`); referenced only as an existence check by scripts/verification/verify_stage_h_testing.py | grep @playwright across package.json files = 0 hits; vitest configs; ci.yaml jobs; file content | Desktop Vitest suite (142 tests) + verify_stage_h_testing.py UI45 check re-pointed to real suite files |
| apps/desktop/e2e/desktop_negative_lanes.spec.ts | UI45 negative lanes | same as above | same | same |
| apps/web/e2e/browser_golden_flow.spec.ts | UI46 "browser E2E" | same as above | same | Web Vitest suite (71 tests) + verify_stage_h_testing.py UI46 check re-pointed to real suite |
| apps/web/e2e/browser_negative_lanes.spec.ts | UI46 negative lanes | same as above | same | same |
| apps/web/src/app/__tests__/App.test.tsx (12 tests) | Old web portal shell: header "WindAgent V2 Architecture - Web Portal", nav tabs TASKS/OVERVIEW/PROVIDERS, lastSyncTimestamp state, portal recovery banner | Tests UI that no longer exists: the strings it queries appear ONLY in the test file, never in production src; apps/web/src/app/App.tsx is now a 3-line re-export of @desktop/App; current UI (Studio shell) is covered by the desktop suite | grep of all strings in apps/web/src + apps/desktop/src = 0 production hits; App.tsx content | Desktop suite: studioShellTests.test.tsx, studioStoryTests.test.tsx, state/*.test.ts (142 tests) |
| tests/test_stage_e_cross_navigation.py | "Stage E cross navigation" | 27-line tautology: asserts a hardcoded dict literal equals itself (`route_params["projectId"] == "vp_01"` where route_params is defined in the test); zero production imports; can never fail | file content (no `from windagent_`/`from scripts` import) | none needed — nothing was ever tested |
| tests/test_stage_i_final_acceptance.py::test_ui47_script_golden_workflow_invariants | UI47 locked-revision invariants | Tautology over hand-built literals: computes sha256 of a literal, asserts two distinct literals differ; no production code exercised | file content; production coverage exists elsewhere | tests/unit/domain/video_production/test_script_behavioral_invariants.py::test_locked_ancestor_immutability |
| tests/test_stage_i_final_acceptance.py::test_ui48_asset_golden_workflow_invariants | UI48 license/approval invariants | Tautology: asserts `candidate_asset["approved"] is False` on a literal, and raises ValueError inside the `pytest.raises` block itself (the test manufactures its own exception); no production code exercised | file content | tests/unit/domain/video_production/test_asset_behavioral_invariants.py::test_license_governance_enforcement |
| tests/test_stage_i_final_acceptance.py::test_ui49_script_asset_integrated_e2e | UI49 eligibility gate | Tautology: builds a literal requirements dict, mutates it, asserts the mutation; no production code exercised | file content | tests/unit/domain/video_production/test_stage_e_script_asset_binding.py (AssetEligibilityService / AssetRequirementResolver) |
| tests/architecture/test_phase00_single_workspace_contract.py::test_phase0_docs_exist | Phase 0 doc deliverables | The three pinned deliverables (docs/adr/0006-multi-agent-workspace-aggregates.md, docs/architecture/g1_g9_test_matrix.md, docs/architecture/multi_agent_schema_mapping.md) were ALL deliberately removed by the docs canonicalization commit 5662ede "chore(docs): remove 163 stale .md files" on this branch; no deliverable docs remain in the canonical tree; the file's code-invariant tests (workspace mount, store normalization) remain and pass | git log 5662ede; ls docs/architecture + docs/adr (absent); remaining 4 tests in file pass | code-invariant tests in same file |

## DELETION GATE CHECKLIST

- Decision = DELETE: yes, per row
- Confidence = HIGH: yes
- Evidence = PRESENT: yes (content greps, config reads, commit history)
- Requirement disposition = KNOWN: yes (REPLACED_BY_BETTER_TEST x8, NO_LONGER_SUPPORTED x1)
- No deletion because of: failing, flaky, slow, hard-to-understand, fixture work, old path, refactor need, release blocking, pass percentage, looks, count
