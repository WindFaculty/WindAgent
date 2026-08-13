# Desktop Build Pipeline

Evidence: apps/desktop/package.json, vite.config.ts, src-tauri/tauri.conf.json, scripts/dev_*.ps1, run.ps1, .github/workflows/ci.yaml.

## Commands

| Task | Command | Output |
|---|---|---|
| Frontend dev (standalone browser) | `cd apps/desktop && npm run dev` | vite dev server :5173 (strictPort), proxies /api+/ws -> 127.0.0.1:8765 (proxy strips `/api` prefix) |
| Web (browser) dev | `scripts/dev_frontend.ps1` -> apps/web `npm run dev` | same :5173 proxy; App re-exported from desktop src via `@desktop` alias |
| Desktop dev (Tauri) | `scripts/dev_desktop.ps1` -> `npm run tauri dev` | Tauri window + vite :5173 (devUrl) |
| Frontend build | `cd apps/desktop && npm run build` (= `tsc -b && vite build`) | apps/desktop/dist/ (index.html + assets; single 676 KB JS chunk, no code splitting) |
| Desktop build (installer) | `cd apps/desktop && npm run tauri build` (or `cargo tauri build`) | src-tauri/target/release/bundle/* (NSIS/MSI per target); frontendDist ../dist embedded via custom-protocol feature |
| Backend dev | `scripts/dev_api.ps1` | uvicorn 127.0.0.1:8765, WINDAGENT_MODEL_BACKEND=mock default, reload, log artifacts/logs/api.log |
| Worker | `python -m windagent_worker` | independent process, no port |
| Full launcher | `run.ps1 -Option N` | menu: Web UI / API / Desktop, ports 8765 + 5173 |

## CI (ci.yaml)

- desktop-test (ubuntu, :659): npm ci -> typecheck -> vitest -> `npm run build`; uploads apps/desktop/dist as `desktop-build` artifact + receipts `desktop-test-evidence`.
- desktop-test-windows (:730): same on Windows; evidence `desktop-test-windows-evidence`.
- web-test / web-test-windows (:521/:592): apps/web npm ci + vitest + build; evidence web-build artifact + web-test-evidence dirs.
- studio-roadmap-gates (:797): python checkers + studio contract/worker/API pytest suites. NO frontend studio tests here (they run under desktop-test vitest).
- final-evidence (:848): aggregates.

## Bundling answers

- Desktop dev: `npm run dev` (vite) + Tauri devUrl http://localhost:5173.
- Production build: `npm run tauri build`; frontend built by beforeBuildCommand `npm run build` -> ../dist (apps/desktop/dist) -> embedded.
- Sidecars: NONE bundled (no externalBin, no capabilities, sidecar_manager.py orphaned). Backend/worker ship/run independently of the desktop installer (manual python start). REPORT ONLY: a shipped desktop build has no bundled backend — installer-only users would see Backend: Offline.
- Repo evidence dirs desktop-build/, web-build/ = CI-uploaded dist snapshots; desktop-test-evidence/ = receipts (build receipt shows SUCCESS 7.4s, 676 KB chunk warning).
