# Local Desktop AI Agent (WindAgent)

Desktop AI computer-use agent local-first. Chạy trên Windows, dùng model
local qua Ollama, không gọi API cloud mặc định.

## Trạng thái hiện tại

**Phase 11 hoàn thành (v0.10.0 → Phase 11 prep).** MVP đã chạy được
end-to-end trên Windows:

- Backend FastAPI sidecar (`apps/backend/`) — ổn định, **295 tests pass**
  (273 Phase 10 + 22 Agent-S3 scaffold tests)
- Frontend React + Vite + Tauri shell (`apps/desktop/`) — Vite dev OK, Tauri bundle defer (cần Rust)
- SQLite persistence, audit log (DB + per-session JSONL), Mock GUI cho dev/CI
- Qwen3 4B planner (mock mode mặc định, Ollama thật khi có model)
- Workflow runner có Pause/Resume/Stop
- Safe mode + permission gate + 10 tool whitelist
- GUI grounding stub (`click_target` raise `VISION_STUB_MODE` thay vì click bừa)
- **Agent-S3 integration** (Phase 11): config / adapter / translator /
  health endpoint / setup script đều ready. WorkflowRunner chưa gọi
  `propose()` — Agent-S3 là **safe optional scaffold** chứ chưa drive
  workflow thật. Xem `docs/agent_s3_integration.md` và
  `artifacts/agent_s3_integration/phase11_closeout_report.md`.

Xem `artifacts/restructure_audit/phase{0..10}_closeout.md` và
`artifacts/agent_s3_integration/phase11_closeout_report.md` để biết chi
tiết từng phase.

## Demo MVP bắt buộc

> Người dùng gõ: "Mở Notepad và gõ Hello from local AI agent."

Agent tạo workflow:
1. Mở Notepad
2. Gõ nội dung
3. Báo hoàn thành

Executor thực thi bằng PyAutoGUI. UI hiển thị từng bước đang chạy, thành công hoặc lỗi.

## Cấu trúc

```
apps/
  desktop/                       # Vite + React + TypeScript + Tauri shell
    src/                         # React UI
    src-tauri/                   # Tauri shell (Cargo.toml + main.rs + tauri.conf.json)
  backend/                       # Python FastAPI sidecar (uv-managed)
    main.py
    routers/  services/  schemas/  db/  tests/
docs/
  mvp_scope.md                   # Scope, demo, acceptance criteria
  event_protocol.md              # WebSocket event contract + workflow schema
  api_contract.md                # REST + WS API
  safety_policy.md               # Tool whitelist + risk level
models/
  README.md                      # Hướng dẫn pull Qwen3 4B qua Ollama
scripts/
  dev_backend.ps1                # Phase 9 — khởi động backend (uv + uvicorn)
  dev_desktop.ps1                # Phase 9 — khởi động frontend (Vite)
  healthcheck.ps1                # Phase 9 — kiểm tra môi trường + service
artifacts/
  runs/                          # Sample workflow + runtime artifacts
  logs/                          # backend.log
  restructure_audit/             # Phase closeout reports
ban_ke_hoach.md                  # Kế hoạch 11 phase + acceptance criteria
```

## Yêu cầu môi trường (Windows)

| Thành phần | Bắt buộc | Tùy chọn | Mục đích |
|---|---|---|---|
| Python 3.10+ | ✓ | | Backend runtime |
| uv | ✓ | | Python package manager (Astral) |
| Node.js 18+ + npm | ✓ | | Vite dev server + frontend build |
| PyAutoGUI + Pillow | ✓ | | Desktop GUI adapter (mock OK cho dev) |
| Ollama + qwen3:4b-q4 | | ✓ | Model thật; mock planner dùng khi thiếu |
| Rust + Tauri CLI | | ✓ | Tauri bundle (Phase 9 defer) |
| PowerShell 5+ | ✓ | | Chạy script `scripts/*.ps1` |

Nếu cần `PyAutoGUI` thật (không mock), mở app ở chế độ không an toàn / cấp quyền Accessibility cho Python trên Windows.

## Hướng dẫn chạy MVP từ máy sạch

### 1. Cài đặt môi trường

Cài Python 3.10+ và Node.js 18+ từ trang chính thức. Sau đó:

```powershell
# uv (Astral) — quản lý Python deps
irm https://astral.sh/uv/install.ps1 | iex

# (Tùy chọn) Ollama + Qwen3 4B
# Tải: https://ollama.com/download
ollama pull qwen3:4b-q4_K_M
```

### 2. Healthcheck

```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1
```

Output sẽ liệt kê từng mục CRIT/OPT/WARN kèm PASS/FAIL. Tất cả CRIT phải PASS trước khi tiếp tục.

### 3. Khởi động backend (Terminal 1)

```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1
```

Mặc định chạy ở `http://127.0.0.1:8765` với:
- `WINDAGENT_MODEL_BACKEND=mock` (không cần Ollama)
- `WINDAGENT_MOCK_GUI=1` (không cần PyAutoGUI thật)

Log ghi ra `artifacts/logs/backend.log` (cộng dồn stdout + stderr).

Muốn dùng Ollama thật:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1 -Mock:$false
```

### 4. Khởi động frontend (Terminal 2)

```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1
```

Mặc định chạy Vite dev ở `http://localhost:5173`. Vite proxy forward `/api/*` + `/ws/*` tới backend, nên React app gọi same-origin không cần CORS.

Muốn mở trong Tauri shell (cần Rust + tauri-cli):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1 -Tauri
```

### 5. Test lệnh demo

Mở `http://localhost:5173` trong browser, gõ:

> Mở Notepad và gõ Hello from local AI agent.

Kỳ vọng (mock mode):
1. UI nhận message → backend tạo workflow 3 bước (mock planner)
2. WorkflowRunner chạy tuần tự, mỗi bước stream event `step_started` / `tool_call_started` / `step_completed` qua WebSocket
3. UI hiển thị tiến trình, status từng step, nút Stop/Pause/Resume hoạt động
4. Tool calls lưu vào SQLite (`windagent.db`)
5. Tất cả event log vào `artifacts/runs/{session_id}/events.jsonl`

## Trạng thái packaging

| Mục | Trạng thái | Ghi chú |
|---|---|---|
| `scripts/dev_backend.ps1` | ✓ | uv-managed, idempotent, mock default |
| `scripts/dev_desktop.ps1` | ✓ | Vite dev default, `-Tauri` opt-in |
| `scripts/healthcheck.ps1` | ✓ | 11 mục, CRIT/OPT/WARN |
| `apps/desktop/src-tauri/` (scaffold) | ✓ | main.rs + tauri.conf.json đầy đủ |
| Tauri bundle build (`.exe`/`.msi`) | ⏳ Defer | Cần Rust toolchain — Phase 9 ghi nhận, build ở môi trường có Rust |
| Python sidecar bundle (`uv run --no-dev ...`) | ⏳ Post-MVP | Hiện cần chạy backend bằng script riêng; gói thành exe để Tauri shell spawn sẽ làm sau |

## Phát triển

- Backend tests: `cd apps/backend && uv run pytest --timeout=15`
- Frontend type-check: `cd apps/desktop && node node_modules/typescript/bin/tsc --noEmit`
- Frontend build: `cd apps/desktop && npm run build`
- Log tail: `Get-Content artifacts\logs\backend.log -Wait`

Trước khi sửa bất kỳ thứ gì liên quan giao tiếp backend ↔ frontend, đọc
`docs/event_protocol.md`. Mọi thay đổi shape phải cập nhật doc trước.

Xem `ban_ke_hoach.md` để biết đầy đủ 11 phase và thứ tự ưu tiên.

## License

Nội bộ.
