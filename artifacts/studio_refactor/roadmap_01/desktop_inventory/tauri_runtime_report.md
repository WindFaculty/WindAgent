# Tauri / Desktop Shell Runtime Report

Evidence: `apps/desktop/src-tauri/{tauri.conf.json,Cargo.toml,src/main.rs,src/lib.rs}`, `apps/desktop/sidecar_manager.py`.

## Shell profile

- Tauri v2 (tauri.conf.json `$schema` v2, `tauri = { version = "2" }`).
- Crate: `windagent-desktop` 0.3.0, `windagent_desktop_lib` (staticlib/cdylib/rlib).
- Window: 1200x800, min 800x500, resizable, title "WindAgent". CSP: null (no security policy).
- Bundle: active, targets "all", single icon `icons/icon.png`. No `externalBin` -> NO sidecars bundled.
- Frontend: `frontendDist: "../dist"` (= apps/desktop/dist), `beforeDevCommand: "npm run dev"` (vite, 5173), `beforeBuildCommand: "npm run build"`.
- Capabilities: no custom `capabilities/*.json`; only generated `gen/schemas/` (default core perms: path/event/window/webview/app/image/resources/menu/tray). No shell/fs/process/http plugins enabled.
- Commands registered: `app_metadata`, `get_system_metrics` (lib.rs:224). Only `get_system_metrics` is invoked by the frontend (App.tsx:124, dynamic import, 2s interval). `app_metadata` has no frontend caller.

## Telemetry

- Real: sysinfo 0.31 (CPU/RAM) + nvml-wrapper 0.10 (NVIDIA GPU/VRAM; skips Intel/Microsoft devices; degrades to zeros + "N/A" on NVML errors). Startup marker + NVML debug logs written to `%TEMP%/windagent_*.log`.
- Browser fallback: App.tsx:156-181 random-walk mock metrics (DEV_ONLY).

## Business logic in shell

NONE. Shell is a thin window + 2 IPC commands. No backend spawn, no process management, no sidecar launcher, no updater, no tray, no window-state persistence.

## Sidecar manager (orphan)

`apps/desktop/sidecar_manager.py` (PHASE 7): SidecarManager with spawn_api_sidecar/spawn_worker_sidecar (mock_spawn=True default, fake PIDs 1234/5678), restart policy (5 restarts, 1s delay), health polling, graceful shutdown (worker->api), log collection. Evidence: repo-wide grep finds the class definition ONLY — zero importers/callers in apps/, scripts/, docs/. Tauri never invokes it (no command). README confirms: "Phase 9 sẽ wire Python sidecar launcher" — planned, unwired.

## Lifecycle answers

- Desktop = shell mỏng, no business logic. Rust manages NO processes.
- Backend/worker: NOT spawned by desktop. Started manually via `scripts/dev_api.ps1` (uvicorn, port 8765, mock model backend default) and `python -m windagent_worker` (independent worker process, DB-polling, no HTTP port).
- Health check: frontend polls `/health/live` every 5s (App.tsx). No desktop-side supervisor, no restart/recovery of backend (frontend just flips badge Offline).
- Ports: backend 8765 (run.ps1/dev_api.ps1 default; HARDCODED in client.ts:15), vite 5173 (strictPort), Studio default 8000 (MISMATCH, StudioPage.tsx:31 — needs VITE_API_BASE).
- Shutdown: window close kills Tauri+webview; backend/worker keep running (no lifecycle hook) — potential orphaned processes (REPORT ONLY).

## Verdict

Tauri shell: minimal, clean, telemetry-only. Redesign impact: near zero — keep Rust as-is; any new native surface (file dialogs, process supervision) would extend commands deliberately.
