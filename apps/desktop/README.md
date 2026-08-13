# apps/desktop

Tauri + React + TypeScript desktop app cho WindAgent.

## Trạng thái hiện tại

- **Frontend (React + Vite + TS)** — scaffold xong, có thể chạy standalone
  bằng `npm run dev`. Không cần Rust.
- **API integration** — Vite proxy `/api` + `/ws` tới Architecture V2 API ở
  `http://127.0.0.1:8765`. Chạy `scripts/dev_api.ps1` trước khi mở desktop.
- **Tauri shell (Rust)** — scaffold xong (`src-tauri/`) nhưng cần Rust
  toolchain để build. Phase 9 sẽ wire Python sidecar launcher.

## Frontend layout

```
apps/desktop/
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx              # React entry
│   ├── App.tsx               # Root component (state + actions)
│   ├── styles.css
│   ├── api/
│   │   ├── client.ts         # REST + WS client
│   │   └── types.ts          # mirrors backend Pydantic schemas
│   ├── components/
│   │   ├── assets/           # production asset workspace
│   │   ├── studio/           # studio artifact views
│   │   └── ui/               # design-system primitives
│   ├── pages/                # Studio shell pages (Dashboard, Studio, ...)
│   ├── lib/
│   │   └── apiBase.ts        # single API base authority (UI0-INFRA-01)
│   ├── services/
│   │   └── conversationSocketManager.ts
│   └── state/
│       ├── theme.tsx
│       └── multiAgentStore.tsx
└── src-tauri/                # Tauri shell (build later)
    ├── Cargo.toml
    ├── build.rs
    ├── tauri.conf.json
    └── src/
        ├── main.rs
        └── lib.rs
```

## Cách chạy dev (frontend standalone)

Yêu cầu: Node 18+.

```powershell
cd apps/desktop
npm install
npm run dev
```

Mở `http://localhost:5173`. Architecture V2 API phải chạy ở port 8765.

Để chạy API với provider/runtime mock:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_api.ps1
```

## Cách build Tauri (cần Rust)

Yêu cầu:
- Rust toolchain (`rustup` + `cargo`)
- Windows: Visual Studio Build Tools với C++ workload + WebView2
- macOS: Xcode Command Line Tools
- Linux: build-essential + webkit2gtk

```powershell
# One-time
cargo install tauri-cli --version "^2.0"

# Run full desktop shell (API runs separately via scripts/dev_api.ps1)
cargo tauri dev

# Production build → apps/desktop/src-tauri/target/release/bundle/
cargo tauri build
```

## Tính năng MVP

- [x] Tạo session mới
- [x] Gửi message (nhập tự nhiên)
- [x] Chat panel: hiển thị user message + tool call log
- [x] Workflow panel: hiển thị step status real-time
- [x] Control bar: Pause / Resume / Stop / Retry (auto-enable theo runner state)
- [x] Permission dialog: render khi có `permission_request`, Confirm → grant, Cancel → deny
- [x] Status bar: model online/offline, session active/inactive
- [x] Periodic poll `/sessions/{id}/workflow` + `/runner` để state luôn fresh
- [x] WebSocket reconnect with exponential backoff

## Phase tiếp theo

| Phase | Sẽ thay đổi gì |
|---|---|
| 8 | Highlight click_xy với confidence (Qwen2.5-VL) |
| 9 | Build Tauri bundle + Python sidecar launcher |
| 10 | Hardening + e2e + release note |
