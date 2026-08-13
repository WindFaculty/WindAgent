# Desktop Redesign Impact Map

What a WindAgent Studio UI redesign touches. Ordered by impact.

## A. Modify directly (highest impact first)

| # | Path | Reason | Impact |
|---|---|---|---|
| 1 | apps/desktop/src/App.tsx | Shell god-file: header, sidebar (hardcoded nav), activeTab routing, health/metrics polling, version/user hardcoding | Every nav/route/layout change lands here today; must be decomposed (studio-shell extraction) |
| 2 | apps/desktop/src/pages/StudioPage.tsx | Studio surface: list/series/episode views + all actions (create series/episode, startRun, selectIdea, approval, lock) | Redesign of Studio Home/Series/Episode Workspace rewrites this page's render; data layer (store) reusable |
| 3 | apps/desktop/src/components/studio/ArtifactViews.tsx | 800-line artifact renderer suite (idea/bibles/beats/outline/screenplay/review/lock/diff) | Split into story-ui package components; content renderers reusable, layout changes |
| 4 | apps/desktop/src/components/studio/RunProgress.tsx, ApprovalBar.tsx | Story workflow status + approval controls | Restyle/extend; logic server-authority, reusable |
| 5 | apps/desktop/src/styles.css | Single 4826-line global stylesheet, :root tokens, 23 font-family declarations | Redesign styling base; tokens exist but need extension/reorganization |
| 6 | apps/desktop/src/api/client.ts | V2 REST/WS module with 22 dead-end stubs + 2 hardcoded stubs | Needed for SYSTEM pages (workspace/agents/models/router); stub cleanup is separate from redesign but surfaces in any "broken page" audit |
| 7 | apps/desktop/src/pages/ProductionWorkspacePage.tsx + production-ui ProductionShell | Fake client + placeholders + hardcoded statuses | Collapse to PRODUCTION group; hide for Roadmap 1 or keep as-is behind group |
| 8 | frontend/packages/studio-* (contracts/client/state) | Frozen contract surface | DO NOT change APIs; only consume. Impact: none in redesign except importing |
| 9 | apps/desktop/src/pages/{Dashboard,Agents,Models,Endpoints,Memory,Workflows,Browser,Files,Router,Settings,MultiAgentWorkspace}.tsx | SYSTEM pages | Keep reachable; regroup under SYSTEM. Dashboard/Models/MultiAgentWorkspace/Router = real; Browser/Files/Memory/Workflows/Endpoints/Settings = fake/placeholder (report only, no fix here) |
| 10 | apps/web (vite config + App re-export) | Browser build of same App | Any App.tsx change propagates; web-specific tsconfig/vite stay |

## B. Reuse unchanged

| Path | Reason |
|---|---|
| frontend/packages/studio-contracts | frozen contract, drift-checked |
| frontend/packages/studio-client (HttpStudioApiClient) | production-grade V3 client |
| frontend/packages/studio-state (StudioStore) | server-authority store, polling, cursors |
| apps/desktop/src-tauri/* (main.rs, lib.rs, tauri.conf.json, Cargo.toml) | thin shell + telemetry; no UI coupling |
| apps/desktop/src/state/theme.tsx | theme context (extend, not replace) |
| apps/desktop/src/services/{agentSocketManager,conversationSocketManager}.ts | WS singletons |
| apps/desktop/src/api/types.ts | type mirror |

## C. Wrap/adapt

| Path | Reason | Target abstraction |
|---|---|---|
| ArtifactViews sub-views (IdeaSetView, StoryBibleView, WorldBibleView, CharacterCanonView, BeatsView, OutlineView, ScreenplayView, ReviewReportView, RevisionProposalView, LockReceiptView, LockPackageView, ScreenplayDiffView) | content renderers are layout-agnostic | story-ui package components taking artifact envelope + callbacks |
| RunProgress | poll/event logic in store; presentational now | story-ui status card component |
| ApprovalBar | decision submit contract | story-ui approval component (checkpoint-typed) |
| StudioPage action handlers (createSeries/createEpisode/startRun/selectIdea/submitApproval/lockScreenplay) | idempotency-key + optimistic-version logic | extract to hooks or StudioPage-level controller reused by workspace tabs |
| ProductionShell | production surface for Roadmap 2 | keep; hide behind PRODUCTION group (collapsed) |
| ChatPanel/MessageList/ChatInput/WorkflowPanel | agent workspace UI | keep for SYSTEM Agent Workspace; restyle via tokens |

## D. Preserve for Roadmap 2 (do not redesign now)

| Path | Reason |
|---|---|
| frontend/packages/production-* (client, contracts, platform, state, ui) | Production video pipeline surface; fake-wired; keep untouched to avoid breaking Roadmap 2 scope |
| components/assets/* (AssetWorkspace, AssetInspector, AssetAcquisitionWizard, AssetJobMonitor, AssetVersionImpactModal, ThreeDPreviewViewer, NonThreeDPreviewViewer) | real V2 asset API behind dead tab; production domain |
| Router page + lib/routerApi.ts | legacy routing console; real, keep working |
| sidecar_manager.py | orphan; decide lifecycle later (candidate for deletion after proving zero callers — not now) |
| apps/web/src/clients/*, apps/web/src/state/* | dead code; candidate for cleanup, NOT redesign scope |

## E. Must not touch yet

| Path | Reason |
|---|---|
| @windagent/studio-contracts fixtures/schemas + generated types | frozen contract; CI gates + drift checker |
| apps/api/windagent_api/routers/v3/studio/* + services/studio_* | backend; contract-frozen; UI redesign does not need backend changes |
| apps/worker/windagent_worker/studio_runtime.py | worker story runtime; out of scope |
| tests/contracts/test_story_b*.py + gate evidence | gate chain 0-26; touch only via roadmap phases |
| .github/workflows/ci.yaml desktop jobs | build/test contract; only extend if redesign adds packages (frontend workspace already covers new packages) |

## Suggested migration order (report only)

1. Extract studio-shell layout primitives (header/sidebar/nav data) from App.tsx.
2. Move components/studio/* into story-ui package (pure moves, keep imports).
3. Restructure navigation data-driven (STUDIO/PRODUCTION/SYSTEM groups) — all pages stay reachable.
4. Build Episode Workspace tab container over existing views (Overview/Idea/Story/Outline/Screenplay/Review/Revisions/Activity).
5. Design token pass (extend styles.css :root vars; kill inline hex in studio/production components).
6. Wire VITE_API_BASE consistently (fix 8000/8765 mismatch) — infra fix, not UI.
7. Production: collapse into PRODUCTION group; leave fake client as-is until Roadmap 2.
