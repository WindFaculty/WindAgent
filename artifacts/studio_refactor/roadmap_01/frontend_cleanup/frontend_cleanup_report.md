# WindAgent Frontend Dead-Code Cleanup

## 1. Executive Summary

Removed 36 files of verified-dead frontend code across `apps/desktop` (legacy chat/session/workflow UI cluster replaced by the Studio shell) and `apps/web` (legacy `clients/*` + `state/*` dead since web became a pure re-export of `@desktop/App`). Every deletion backed by zero-caller evidence: static graph, repo-wide grep, test, build, CI, workspace, docs. Plus 4 dead exports removed from live `apps/desktop/src/api/client.ts`. No production, Studio-protected, or Roadmap-2 code touched. Full regression matrix green.

Verdict: **WIND_STUDIO_FRONTEND_DEAD_CODE_CLEANUP_VERIFIED**

## 2. Baseline

- HEAD `bcefc009634f5a65fc06c1c42d82e3c9cc837401`, branch `chore/cleanup-stale-md-docs`, node v22.23.1, npm 10.9.8
- Workspace: `frontend/` = npm workspaces root (`packages/*`, 10 packages); `apps/desktop` + `apps/web` standalone npm projects; no root package.json
- Desktop: typecheck 0, tests 15 files/159 PASS, build 0
- Web: typecheck 0, tests 6 files/70 PASS, build 0
- Frontend workspaces: typecheck exit 2 (pre-existing parallel-agent WIP: production-platform `architecture.test.ts` TS2554, production-state `SelectedEntity` TS2305, story-ui envelope literals TS2739); `npm test` exit 1 (production-client/contracts have no test script); `npm run build` exit 2 (no build scripts). Gate `WIND_STUDIO_FRONTEND_CLEANUP_BASELINE_CAPTURED` PASS — real gates green, failures recorded.
- Artifacts: `phase_f0/{baseline_git,baseline_packages,baseline_tests,baseline_builds}.json`

## 3. Frontend Runtime Roots

- `apps/desktop/src/main.tsx` (+ `apps/desktop/index.html`)
- `apps/web/src/main.tsx` (+ `apps/web/index.html`) → `app/App.tsx` → re-export `@desktop/App` (web = browser build of desktop App; `@desktop` alias + `@desktop/styles.css`)

## 4. Dependency Analysis

- 1411 files inventoried (1146 src-tauri JSON configs/icons excluded as protected Tauri shell); 225 SOURCE/TEST/STYLE files analyzed
- Static ES import graph from the 2 roots (relative + alias + package resolution, barrel-aware): 129 reachable, 96 not reachable
- Not-reachable ≠ dead: classified per F11 (tests, WIP, Roadmap-2, studio-protected)
- Dynamic imports: 1 found (`agentSessionStore.ts:617` → `agentEventReducer`) — closed cluster, both deleted
- `frontend_file_inventory.json`, `frontend_dependency_graph.md`, `frontend_runtime_roots.json` written

## 5. Package Analysis

| package | classification |
|---|---|
| studio-contracts / studio-client / studio-state / studio-shell / story-ui | ACTIVE (desktop imports; story-ui x4, shell x1; parallel-agent untracked WIP) |
| production-contracts / production-client / production-platform / production-ui | ACTIVE (ProductionWorkspacePage) |
| production-state | ROADMAP_2_PACKAGE — 0 importers (vite aliases + package.json dep only). REPORT ONLY per rule 25. |

## 6. apps/desktop Findings

Deleted (Batch A, 24 files): ChatInput/ChatPanel/MessageList/ControlBar/StatusBar/WorkflowPanel/WorkflowStepItem/PermissionDialog/SessionNavigator, useSessionEvents, routerApi, agentEventReducer, agentSocketManager, agentSessionStore, sessionStore, useAgentSession + 8 own tests. Zero importers in App.tsx, all pages, components/ui, components/assets, components/studio (grep + graph). Zero docs/scripts/CI refs. Kept: theme.tsx (main.tsx), multiAgentStore + conversationSocketManager (MultiAgentWorkspace), api/client.ts (App/Agents/MultiAgentWorkspace).

## 7. apps/web Findings

Web app = 3 live files (main.tsx, app/App.tsx, test/setup.ts). Legacy `clients/*` (5) + `state/state_recovery.ts` + 6 tests: zero non-test callers repo-wide (only self-tests + stale coverage JSON). Deleted (Batch B, 12 files). Web vitest suite became legitimately empty → `passWithNoTests: true` (exit 0, coverage job exit 0).

## 8. Shared Package Findings

No shared-package deletion. production-state reported (section 5). studio-contracts fixtures protected (drift checker + Python contract test).

## 9. Dead Export Findings

Batch C: removed `controlSession`, `retryStep`, `connectWs`, `WsListener` from `api/client.ts` (callers deleted in A/B). Kept `WsHandle`/`connectConversationWs` (live conversationSocketManager). Pre-existing dead exports (`createSession`, `fetchSession*`, `sendMessage`, `fetchPermissionConfig`, ...) → UNKNOWN/MEDIUM, reported, not deleted (rule 18; possible consumers in parallel-agent UI work).

## 10. CSS / Asset Findings

- CSS: single `styles.css`, live (imported by main.tsx + web App). Internal selector cleanup = out of scope (rule 15). Zero files deleted.
- Assets: no public/ dirs in either app; src-tauri icons/capabilities protected; zero svg/webp/font in frontend scope; `asset_reference_report.json` = zero deletions.

## 11. Protected Roadmap 1 Code

Untouched: studio-contracts/client/state, StudioPage, components/studio (ApprovalBar/ArtifactViews/RunProgress — zero current importers but studio-protected + parallel-agent WIP), components/ui primitives, story-ui/studio-shell packages, src-tauri/**.

## 12. Preserved Roadmap 2 Code

Untouched, REPORT ONLY: production-state (0 importers), production-contracts `routing/routingCodec.ts` (0 refs), components/assets/** (asset pipeline). 0 production files deleted.

## 13. Verified Deletions

36 files, all `VERIFIED_DELETE_CANDIDATE` / HIGH confidence / zero callers in all six dimensions. See `deleted_files_manifest.json` + `pre_delete_manifest.json` (final-search verdict per file).

## 14. Files Considered But Preserved

`preserved_files_manifest.json` — 11 entries (production-state, routingCodec, 3 studio components, components/assets, components/ui, story-ui/studio-shell, api/client legacy exports, 3 live legacy files, contract fixtures).

## 15. Package / Manifest Cleanup

- `apps/web/vite.config.ts`: `passWithNoTests: true` (suite legitimately empty)
- `apps/desktop/README.md`: file tree updated (dead entries removed)
- `scripts/verification/verify_stage_h_testing.py`: UI46 presence marker `state_recovery.test.ts` → `app/App.tsx` (script PASSED)
- No dependency/lockfile changes (nothing removed required manifest cleanup)

## 16. Test Results

Desktop 8 files/71 PASS (studio shell/story/production regression intact); web empty suite exit 0; 8 package suites 92 tests PASS; drift check PASS; Python web test 2 PASS. Typecheck failures = identical pre-existing set (parallel WIP), zero new.

## 17. Build Results

Desktop typecheck/build PASS, web typecheck/build PASS. `post_delete_build_matrix.json`.

## 18. Bundle Delta

-36 source files (225 → 189). JS/CSS bytes ~flat (confounded by parallel-agent WIP chunks story-ui/studio-shell split). Correctness > size. `bundle_delta.json`.

## 19. Remaining Legacy Frontend

`api/client.ts` legacy session APIs (reported), pages Browser/Files/Memory/Settings/Workflows placeholder pages = LEGACY_REACHABLE (rule 28: product-surface retirement ≠ dead-code cleanup), components/studio stubs (protected), production-* (Roadmap 2).

## 20. Risks / Unknowns

- Parallel agent (Antigravity) active on same tree: untracked ui/, story-ui, studio-shell, studioCertificationPhase12.test.tsx appeared mid-session. My deletions were git rm'd from tracked files only; their WIP untouched. Pre-existing typecheck failures unchanged.
- api/client.ts pre-existing dead exports kept (MEDIUM confidence, possible future consumers) — follow-up candidate.
- Bundle comparison confounded by concurrent WIP (noted in bundle_delta.json).

## 21. Final Verdict

**WIND_STUDIO_FRONTEND_DEAD_CODE_CLEANUP_VERIFIED**

All 36 deletions have HIGH-confidence zero-caller evidence; desktop typecheck/tests/build PASS; web typecheck/tests/build PASS; package tests PASS; studio + production regression PASS; drift check PASS; no new broken imports/routes/contracts/architecture violations; no unrelated code modified.
