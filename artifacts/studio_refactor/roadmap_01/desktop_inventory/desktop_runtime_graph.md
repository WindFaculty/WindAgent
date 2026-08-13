# Desktop Runtime Graph

## Graph A — Desktop structural

```
main.rs (Rust entry) -> windagent_desktop_lib::run()
  -> tauri::Builder + generate_handler![app_metadata, get_system_metrics]
  -> webview loads apps/desktop/dist (prod) | http://localhost:5173 (dev)

main.tsx (React entry) -> ThemeProvider -> <App/>
  -> App.tsx (header + sidebar + main-content switch)   [EXISTS, hardcoded]
     -> pages/* (16 tabs)                                [EXISTS, mixed real/fake]
     -> components/studio/* (RunProgress, ApprovalBar, ArtifactViews)  [EXISTS, real]
     -> @windagent/studio-* packages                     [EXISTS, real]
     -> @windagent/production-* packages (ProductionShell + placeholders) [EXISTS, fake-wired]
```

## Graph B — Runtime

```
Desktop UI (App.tsx) 
  |-- fetchHealth/fetchHermesHealth -> 127.0.0.1:8765/health/live  [REAL / STUB]
  |-- invoke('get_system_metrics') -> Tauri sysinfo+NVML            [REAL]
  |-- MultiAgentWorkspace -> client.ts -> /api/v2/conversations/* + WS /ws/conversations/<id> [REAL]
  |-- Router page -> routerApi.ts -> /api/models/routing/*          [REAL, legacy surface]
  |-- StudioPage -> HttpStudioApiClient -> /api/v3/studio/*         [REAL]
  |       -> StudioStore (state) -> components                      [REAL]
  |-- ProductionWorkspacePage -> FakeProductionApiClient -> ProductionShell -> placeholders [FAKE]
  v
FastAPI backend :8765 (external, manual start)
  |-- orchestrator (StudioRunService) -> outbox -> worker lease
  v
Worker (external, manual start) -> StudioRuntimeAdapter -> story handlers -> provider adapter
  v
Ollama / cloud provider (optional; mock backend default)
```

## Graph C — Studio UI (Roadmap 1 flow)

```
Studio (#/studio)                                   EXISTS (list + create series)
  -> Series (#/studio/series/<id>)                  EXISTS (episodes + create + start run)
       -> Episode (#/studio/episodes/<id>)          EXISTS
            -> Idea        IdeaSetView + select     EXISTS
            -> Story       StoryBibleView/WorldBibleView/CharacterCanonView/BeatsView  PARTIAL (viewers only)
            -> Outline     OutlineView + approval   EXISTS
            -> Screenplay  ScreenplayView + Diff    EXISTS (read-only)
            -> Review      ReviewReportView + RevisionProposalView + ApprovalBar  EXISTS
            -> Lock        lockScreenplay + LockReceiptView/LockPackageView + read-only banner  EXISTS
            -> READY_FOR_PRODUCTION                 EXISTS (terminal state, banner)
```

Status legend: EXISTS / PARTIAL / MISSING as annotated. All studio nodes are server-driven (no fake data in the studio path).
