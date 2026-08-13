# WindAgent Desktop Current Architecture

Inventory for Roadmap 1 (WindAgent Studio) redesign baseline.
Evidence: code paths + symbols cited inline. All findings read-only; NO source modified.

## 1. Executive Summary

Desktop = Tauri 2 (thin Rust shell, 2 IPC telemetry commands) + React 18 frontend in `apps/desktop` (vite, port 5173). `apps/web` is a browser re-export of the SAME App via `@desktop` alias (its own clients/state are dead). Frontend is a single-file shell (`App.tsx`, 593 lines): hardcoded sidebar, `activeTab` useState routing, hash routing only for Studio. Studio (Roadmap 1 core) is REAL: `HttpStudioApiClient` -> `/api/v3/studio/*` -> `StudioStore` -> `StudioPage` with full story read path (idea -> bibles -> outline -> screenplay -> review -> lock -> READY_FOR_PRODUCTION), 142 passing tests. Production UI is FAKE-WIRED: `ProductionWorkspacePage` hardcodes `FakeProductionApiClient` + `proj-alpha`, `ProductionShell` renders 3 placeholders with hardcoded sync/backend status; the rich screenplay component suite is dead export. Backend/worker run as independent external processes (no supervisor, no sidecar bundling; `sidecar_manager.py` orphaned). Mixed real/fake across system pages (Agents stub-broken, Browser/Files/Memory hardcoded). Redesign impact concentrates in App.tsx + StudioPage + ArtifactViews + styles.css; studio-* packages and Tauri shell are reusable as-is.

## 2. Desktop Entry Points

| Entry | Path | Responsibility | Who calls | Initializes / Launches |
|---|---|---|---|---|
| Rust main | apps/desktop/src-tauri/src/main.rs | calls windagent_desktop_lib::run() | cargo/tauri | window + webview |
| Tauri runtime lib | apps/desktop/src-tauri/src/lib.rs | builder + 2 commands (app_metadata, get_system_metrics) | main.rs | sysinfo/NVML telemetry; loads dist or devUrl |
| React entry | apps/desktop/src/main.tsx | createRoot + ThemeProvider + App | index.html (vite) | React tree |
| App shell | apps/desktop/src/App.tsx | header/sidebar/render-switch; health poll 5s; metrics poll 2s; studio cert deep-link | main.tsx | all 16 page tabs |
| Studio route | apps/desktop/src/pages/StudioPage.tsx | hash router (#/studio, series, episodes) + all studio actions | App.tsx (tab studio) | HttpStudioApiClient + StudioStore |
| Web entry | apps/web/src/main.tsx | re-exports @desktop/App | apps/web index.html | same App (browser build) |

## 3. Repository Structure

- apps/desktop — Tauri + React app (own npm workspace; vite/vitest; dist/; src-tauri/; sidecar_manager.py orphan).
- apps/web — browser build of same App; dead legacy clients/state dirs.
- apps/api/windagent_api — FastAPI V2 + V3 routers (routers/v3/studio/*), services/studio_application_service.py, lifespan, health.
- apps/worker/windagent_worker — independent worker: runner, lease, studio_runtime (StudioRuntimeAdapter + StudioCompletionRecovery), studio_model_port.
- frontend/packages — 8 shared TS packages: production-contracts/client/platform/state/ui + studio-contracts/client/state. story-ui + studio-shell NOT_IMPLEMENTED.
- scripts — dev_api.ps1, dev_desktop.ps1, dev_frontend.ps1, studio_roadmap/* (evidence producers), run.ps1 launcher.
- .github/workflows/ci.yaml — web/desktop test+build jobs (evidence: desktop-build/, web-build/, desktop-test-evidence/, web-test-evidence/), studio-roadmap-gates job.

## 4. Tauri / Native Shell

Thin shell, no business logic (tauri_runtime_report.md). Tauri v2; window 1200x800; csp null; no externalBin, no shell/fs/process plugins, default core permissions only; bundle targets all. Rust manages NO processes; backend/worker started manually (dev_api.ps1 port 8765 / python -m windagent_worker). No health check from Rust (frontend polls /health/live), no restart/recovery/supervisor, no updater. Hardcoded localhost ports: client.ts 8765, vite 5173 strictPort, Studio default 8000 (mismatch). sidecar_manager.py (Phase 7 supervisor, restart policy, graceful shutdown) has ZERO callers — orphan.

## 5. Process Topology

(desktop_process_topology.md) Desktop(Tauri+webview) -> HTTP 8765 (V2 REST+WS) + 8000 (V3 studio) -> FastAPI (external) -> outbox -> Worker (external, DB-poll) -> provider (Ollama/cloud, optional; mock default). Hermes node: UNWIRED (fetchHermesHealth hardcoded false). No desktop-owned process lifecycle; shutdown orphans backend/worker. REPORT ONLY.

## 6. Frontend Architecture

React 18 + TS, no router lib, no CSS framework, no component lib. State: useState + useReducer (legacy sessionStore) + Zustand (agentSession/multiAgent stores) + Context (theme) + custom class store (StudioStore). Redux Toolkit present (production-state) but dead. 676 KB single JS chunk. Studio stack (contracts/client/state) is the cleanest layer and Roadmap-1-ready.

## 7. Routing

No react-router. App.tsx `activeTab` switch (state routing, no URL, no deep links) + StudioPage `window.location.hash` + hashchange listener for `#/studio`, `#/studio/series/<id>`, `#/studio/episodes/<id>` (deep-link + refresh rehydration). Certification deep-link via VITE_STUDIO_CERTIFICATION_EPISODE_ID (App.tsx:36-53). Full route table: route_inventory.json.

## 8. Navigation

HARDCODED JSX in App.tsx:311-518: Dashboard, Agents, Agent Workspace, Workflows, Browser, Files, Memory, Models (expandable: Model Library/Endpoints), Router, Studio, Production (expandable: 📜 Script Workspace, 🎨 Asset Library, 🎬 Video Workspace), Settings. No config, no permissions, no flags. Sidebar bottom hardcodes "WindAgent v1.2.0" (mismatches tauri.conf 0.3.0) + WindUser/Administrator. Dead tab: render switch keys `asset-library` (App.tsx:584) but nav never sets it. Full table: navigation_inventory.json.

## 9. Layout System

```
App (app-container)
├── header.top-header (brand, Localhost/Backend/Hermes/Local-First badges, CPU/RAM/GPU/VRAM metrics + sparklines, fake window controls)
└── div.workspace-wrapper
    ├── aside.left-sidebar (nav + version box + user profile)
    └── div.main-content (render switch -> page)
```
StudioPage renders its own minimal layout inside main-content (h2 + capability badges + error/loading + sections). ProductionShell adds its own 220px inner sidebar + header. No layout components, no responsive behavior, no workspace-level shell. Theme via Context + styles.css classes.

## 10. Studio Current Implementation

StudioPage (548 lines) — REAL, C2-C5 gate-backed:
- Route views: list (series), series (episodes), episode (detail).
- Real client: `new HttpStudioApiClient({baseUrl: VITE_API_BASE || 'http://localhost:8000'})` (StudioPage.tsx:80) + `StudioStore` (server-authority).
- Capability badges: durable_db, studio_orchestration, story_engine, worker (+ model_route tracked, not rendered).
- Create Series / Create Episode: real POST with idempotency keys, pending markers, navigate on success.
- Start/resume run; selectIdea (candidate id + revision hash + optimistic version, server-validated); ApprovalBar at awaiting_checkpoint (IDEA/STORY_BIBLE/OUTLINE/SCREENPLAY); Lock screenplay (hash-bound) at SCREENPLAY_REVIEW; READ_ONLY_STATES LOCKED/READY_FOR_PRODUCTION banner; RunProgress polling (2s, cursor from server next_after, sessionStorage hydration); artifacts list with ScreenplayDiffView for >=2 drafts; ERROR_LABEL map incl. fail-closed capability_unavailable.
- Create Series dùng API THẬT (v3 studio), không fake. Series list từ server. Episode UI có. Story workflow UI có (read path).

## 11. Production Current Implementation

ProductionWorkspacePage (34 lines): `route.projectId = 'proj-alpha'` HARDCODED (line 13), `new FakeProductionApiClient()` HARDCODED (line 21; comment claims HTTP fallback — none exists), `TauriDesktopAdapter` real. ProductionShell renders ScriptEditorPlaceholder / AssetLibraryPlaceholder / VideoWorkspacePlaceholder with hardcoded `syncStatus="synced"` `backendStatus="online"` (ProductionShell.tsx:90-91). HttpProductionApiClient exists (real /api/v2/video-production/{projects,workspace,commands}) but listProjects hardcodes vp_001 and the class has ZERO app callers. Rich screenplay suite (ScreenplayWorkspaceView, StructuredEditor, TextEditor, SceneTree, SceneInspector, ValidationGatePanel, AIProposalView, conflict/collaboration/recovery panels) exported but imported by nothing outside tests (dead exports). AssetWorkspace (components/assets) calls real /api/v2/video-production/assets but sits behind the unreachable asset-library tab. Roadmap status: PRESERVE/ISOLATE/ROADMAP_2.

## 12. API Client Architecture

(client table in api_client_inventory.json):
- client.ts: V2 REST+WS, base 127.0.0.1:8765 hardcoded. Real: sessions CRUD/snapshot/events/messages/cancel/archive, conversations agents/task-graphs/stop, events replay, task cancel, browser control, WS session + conversation streams. STUBS: v2Unavailable throwers (agent registry, permission config/decide, pause/resume/retry, task-node/edge CRUD, retryStep) + hardcoded fetchHermesHealth {enabled:false,...} + fetchRunner {runner:null}.
- routerApi.ts: real legacy routing surface (/api/models/routing/*, /api/router/runtime/*, /api/v2/providers), base VITE_API_BASE||''.
- HttpStudioApiClient: real V3, idempotency-key mutations, 15s timeout, typed errors, GET retry-once.
- ProductionApiClient: Fake wired; Http dead.
- production-state + ProductionSyncClient + apps/web clients/state: dead exports (TEST_ONLY).

## 13. State Management

state_management_report.md. Studio: server-authority class store (no optimistic durability, pending markers, cursor persistence) — REUSE. Rest: patchwork (useState/useReducer/Zustand/Context). production-state Redux: dead.

## 14. Runtime Telemetry

Header badges + metrics: backendOnline via fetchHealth /health/live 5s poll (real); hermesOnline via fetchHermesHealth (HARDCODED false — never real); CPU/RAM/GPU/VRAM via Tauri invoke get_system_metrics 2s (real sysinfo+NVML, NVIDIA-only, degrades to 0/N/A) with random-walk mock fallback in plain browser; sparklines from history arrays. StatusBar component (legacy) shows modelsOnline/session. Dashboard receives metrics via props.

## 15. Design System

styles.css (4826 lines, single global stylesheet, 23 font-family declarations): :root CSS custom props = dark theme tokens (--bg-darker #07090e, --bg-dark #0b0f19, --bg-panel, --border-color, --color-primary #3b82f6, --color-success/warning/danger/accent, glows). No Tailwind/modules/SCSS, no component library, no icon lib (inline SVGs + emoji), no chart lib (SVG polylines). production-ui uses inline hex (#0f1117 etc.) — bypasses tokens. Redesign: reuse/extend existing tokens; replace ad-hoc inline styling.

## 16. Component Inventory

component_inventory.json (47 entries). Reuse HIGH: studio artifact views + RunProgress/ApprovalBar + ChatInput/MessageList + ImportFileDialog. DO_NOT_REUSE: App shell as-is, placeholders. PRESERVE_FOR_ROADMAP_2: production-ui suite + assets/*.

## 17. Fake / Mock / Hardcoded Runtime Findings

hardcoded_fake_runtime_audit.json (27 findings). Headlines: FakeProductionApiClient wired into production tabs + proj-alpha + vp_001 in Http client + prj_default; fetchHermesHealth stub; 22 v2Unavailable stubs (Agents page BROKEN: fetchAgents throws); Browser/Files/Memory/Workflows/Endpoints/Settings = hardcoded demo UI; random mock metrics fallback; version/identity hardcoding (v1.2.0 vs 0.3.0); Studio port 8000 vs backend 8765 mismatch; sidecar mock PIDs 1234/5678 (orphan).

## 18. Test Architecture

desktop_test_inventory.json. apps/desktop vitest: 13 files / 142 tests — PASSED locally 2026-08-13 (incl. studioShellTests 6, studioStoryTests 30, productionPackageTests 14). Packages vitest: 11 files / 60 tests. apps/web legacy suites (6 files) test dead code. e2e specs (apps/desktop/e2e, apps/web/e2e, web App.test) staged for DELETION on this branch. CI: desktop-test + desktop-test-windows (npm ci/typecheck/vitest/build) + web-test* + studio-roadmap-gates (python suites; no frontend studio tests). No Rust test suite.

## 19. Build & Packaging

desktop_build_pipeline.md. Dev: npm run dev (vite 5173, proxy /api+/ws->8765) / npm run tauri dev. Prod: npm run tauri build -> src-tauri/target/release/bundle (frontend dist embedded, custom-protocol). Frontend build: tsc -b && vite build -> apps/desktop/dist (676 KB chunk warning). CI evidence dirs at repo root (desktop-build/, web-build/, desktop-test-*). No sidecars bundled — installer-only deployment has no backend. REPORT ONLY.

## 20. Roadmap 1 Gap Analysis

(desktop_roadmap_mapping.md + story_frontend_gap_matrix.md) Read path complete; presentation missing: Episode Workspace tabs (IDEA/STORY/OUTLINE/SCREENPLAY/REVIEW/REVISIONS/ACTIVITY), story-ui + studio-shell packages (extraction), bible/outline editors (viewers exist; write = deriveRevision via runs per contract), review findings UX, screenplay editor decision (production-ui suite vs new), design token pass, nav restructure. Port 8000/8765 mismatch is an infra defect to fix before certification-style flows (only C7 script sets VITE_API_BASE).

## 21. Reusable Architecture

Tauri shell (lib.rs/main.rs/tauri.conf) unchanged; studio-contracts (frozen) + studio-client + studio-state; StudioPage action layer (idempotency/version logic); ArtifactViews renderers; RunProgress/ApprovalBar; theme.tsx; WS managers; vite proxy pattern; dev scripts.

## 22. Legacy Architecture

apps/web legacy clients/state (dead); apps/web App re-export shim; client.ts v2Unavailable stubs; fetchHermesHealth/fetchRunner hardcoded; sessionStore useReducer MVP; fake system pages (Browser/Files/Memory/Workflows/Settings/Endpoints); ProductionShell placeholder pipeline + hardcoded statuses; sidecar_manager.py (orphan, candidate for future deletion after proving zero callers); dead asset-library tab; production-ui dead exports.

## 23. Redesign Impact Surface

desktop_redesign_impact_map.md (A: modify — App.tsx, StudioPage, ArtifactViews, RunProgress/ApprovalBar, styles.css, client.ts, ProductionWorkspacePage/ProductionShell, SYSTEM pages regroup; B: reuse unchanged — studio-* packages, src-tauri, theme, WS managers; C: wrap — artifact views into story-ui, action handlers into hooks, ProductionShell behind PRODUCTION group; D: preserve Roadmap 2 — production-* packages, assets/*, Router, sidecar_manager.py, apps/web leftovers; E: must not touch — frozen contracts/fixtures, v3 backend, worker runtime, gate tests, CI desktop jobs).

## 24. Recommended UI Migration Order

1) Extract studio-shell layout (header/sidebar/nav data) from App.tsx. 2) Move components/studio/* to story-ui. 3) Data-driven nav groups STUDIO/PRODUCTION/SYSTEM (nothing deleted). 4) Episode Workspace tabs over existing views. 5) Design token pass (kill inline hex). 6) Fix VITE_API_BASE/8000 mismatch (infra). 7) Collapse Production behind group until Roadmap 2.

## 25. Risks / Unknowns

- UNKNOWN: exact render content of Dashboard charts, ChatPanel internals beyond API usage (not needed for studio redesign).
- UNKNOWN: whether production-ui screenplay suite will be reused for studio screenplay editing (Roadmap 2 decision).
- Port mismatch studio 8000 vs backend 8765 — Studio offline by default unless VITE_API_BASE set (verified only C7 script sets it).
- No supervisor: backend/worker not managed; shutdown orphans processes (REPORT ONLY).
- Fake production wiring + hardcoded statuses would ship in any installer build today.
- Hermes badge always false (stub) — misleading UI.
- Agents page broken (stub-backed) — visible defect, not in Roadmap 1 scope.
- UNKNOWN: `ThreeDPreviewViewer` library (three.js?) — not verified (not read).
- app_metadata command has no frontend caller — harmless.

## 26. Final Desktop Architecture Verdict

Desktop is a healthy thin Tauri shell carrying a mixed frontend: an exemplary real Studio stack (contract/client/store/page, fully server-authority, tested 142+60) alongside legacy/fake system pages and an unplugged production UI. Roadmap 1 does not require backend or shell changes — it requires reorganizing presentation: shell decomposition, story-ui/studio-shell extraction, Episode Workspace layout, and design tokens, all while preserving the frozen V3 contract path.
