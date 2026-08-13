# Desktop Process Topology

Evidence: run.ps1, scripts/dev_api.ps1, scripts/dev_desktop.ps1, scripts/dev_frontend.ps1, apps/worker/windagent_worker/__main__.py, apps/desktop/sidecar_manager.py (orphan), apps/api/windagent_api/main.py.

## Runtime graph (actual, traced)

```
WindAgent Desktop (Tauri process: windagent_desktop_lib)   [IN_PROCESS: Rust shell, 2 IPC commands]
   |
   | webview loads apps/desktop/dist (prod) or vite :5173 (dev)
   v
React frontend (App.tsx)                                    [IN_PROCESS: same process, webview]
   |-- HTTP/WS  -> 127.0.0.1:8765   (client.ts BASE_URL; /health/live, /api/v2/*, /ws/conversations/*)
   |-- HTTP     -> localhost:8000    (StudioPage default; /api/v3/studio/*)  [port MISMATCH vs 8765]
   |-- Tauri IPC -> get_system_metrics (sysinfo + NVML, 2s)
   v
FastAPI backend (uvicorn, python -m windagent_api.main)     [EXTERNAL_PROCESS, LOCAL_SERVICE]
   |   started manually: scripts/dev_api.ps1 (port 8765, WINDAGENT_MODEL_BACKEND=mock default)
   |
   |-- DB (SQLite via windagent_storage, e.g. windagent.db)
   |-- OrchestrationV2Container / TaskManager / StudioRunService (in-process)
   |-- outbox -> worker lease polling
   v
Worker (python -m windagent_worker.__main__)                [EXTERNAL_PROCESS, LOCAL_SERVICE]
   |   started manually; DB-polling (no HTTP port)
   |-- WorkerContainer: ExecutionRuntimeRegistry, StudioRuntimeAdapter (story handlers),
   |   StudioCompletionRecovery, route lock service, provider adapters
   v
Provider/Model (Ollama or cloud vendor adapter)             [EXTERNAL_PROCESS / HTTP_SERVICE, OPTIONAL]
   (dev default: mock backend — WINDAGENT_MODEL_BACKEND=mock)

Hermes agent runtime (desktop UI "Hermes" badge)           [NOT CONNECTED]
   fetchHermesHealth() returns hardcoded {enabled:false, reachable:false} — badge can never be green.
```

## Node classification

| Node | Class |
|---|---|
| Tauri shell | IN_PROCESS |
| React frontend | IN_PROCESS (webview of shell) |
| FastAPI backend | EXTERNAL_PROCESS / LOCAL_SERVICE (manual start) |
| Worker | EXTERNAL_PROCESS / LOCAL_SERVICE (manual start) |
| Ollama / cloud provider | EXTERNAL_PROCESS / HTTP_SERVICE, OPTIONAL |
| Hermes runtime | UNKNOWN/UNWIRED (stub) |
| sidecar_manager.py SidecarManager | LEGACY, orphan (zero callers) |
| apps/web app | LEGACY (browser re-export of same App; own clients/state dead) |

## Startup sequence (real)

1. User starts backend: `scripts/dev_api.ps1` (uvicorn 127.0.0.1:8765).
2. User starts worker: `python -m windagent_worker` (independent).
3. User starts desktop: `scripts/dev_desktop.ps1` -> `npm run tauri dev` (vite 5173 + Tauri webview). Or browser: `scripts/dev_frontend.ps1` (apps/web vite, same App via @desktop alias).
4. Frontend mounts, polls /health/live (5s) + get_system_metrics (2s), StudioPage polls /api/v3/studio/capabilities + series.
5. No readiness gate between frontend and backend: frontend renders, backend badge flips to Offline if unreachable. Studio shows fail-closed "capability unavailable" per capability status.

## Shutdown (real)

Window close -> Tauri exits -> webview gone. Backend/worker NOT stopped (no hook, no supervisor) -> orphaned processes unless user Ctrl+C's the consoles. sidecar_manager.py's graceful shutdown (worker then api) is never called. REPORT ONLY.

## Risks

- Studio default port 8000 vs backend 8765: Studio UI offline until VITE_API_BASE=http://127.0.0.1:8765 set (only C7 cert script sets it).
- No supervisor: backend crash = permanent Offline badge; no restart.
- Process orphaning on desktop exit.
- Hermes badge permanently false (stub).
