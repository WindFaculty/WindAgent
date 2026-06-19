# Phase 6 Enhancement Closeout — Dark/Light toggle + GUI grounding stub

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS

## 1. Phạm vi đã làm

User yêu cầu enhance Phase 6 frontend. Tôi chọn 2 enhancement ổn định nhất
trong số 3 options được liệt kê (Playwright / dark-light toggle / click_xy
highlight). Skip Playwright (browser binaries ~500MB, download chậm) và
click_xy highlight thật (cần Qwen2.5-VL thật). Thay vào đó:

1. **Dark/light toggle** (frontend UX) — ThemeProvider context, localStorage
   persist, OS preference detection, theme toggle button trong StatusBar.
   Mọi CSS color thông qua biến nên tự respect theme.
2. **Mock GuiGroundingService** (backend, Phase 8 prep) — Protocol +
   Mock impl + VisionModelGroundingService stub. Wire vào lifespan với
   env var `WINDAGENT_GROUNDING_BACKEND=mock|vision`. Phase 8 sẽ thay
   mock bằng Qwen2.5-VL thật.

## 2. Deliverables thực tế

### 2.1 Backend

```
apps/backend/
├── services/
│   └── gui_grounding.py       # Mới — Protocol + Mock + VisionModel stub
├── tests/
│   └── test_gui_grounding.py  # Mới — 12 tests
└── main.py                     # Sửa — wire grounding_service vào lifespan
                                # + env var GROUNDING_BACKEND
```

### 2.2 Frontend

```
apps/desktop/src/
├── state/
│   └── theme.tsx              # Mới — ThemeProvider + useTheme hook
├── components/
│   └── StatusBar.tsx          # Sửa — theme toggle button
├── main.tsx                    # Sửa — wrap <App> in <ThemeProvider>
└── styles.css                  # Sửa — :root[data-theme="light"] variant
```

### 2.3 Tests mới (12)

- `test_gui_grounding.py` (12 tests, all pass):
  - `test_mock_locate_returns_gui_point`
  - `test_mock_locate_deterministic_for_same_target`
  - `test_mock_locate_different_for_different_targets`
  - `test_mock_records_calls`
  - `test_mock_fail_on_raises`
  - `test_mock_health_online` / `test_mock_health_offline`
  - `test_screenshot_path_ignored_by_mock`
  - `test_vision_stub_raises_not_implemented`
  - `test_mock_satisfies_protocol`
  - `test_grounding_service_wired_via_lifespan`
  - `test_grounding_service_default_is_mock`

## 3. Verify

```
$ cd apps/backend && uv run pytest --timeout=15
174 passed, 10 warnings in 47.33s   # 162 + 12 mới

$ cd apps/desktop && node node_modules/typescript/bin/tsc --noEmit
(no errors)

$ vite build
✓ 43 modules transformed
dist/index.html        0.39 kB │ gzip:  0.26 kB
dist/assets/index-*.css 5.77 kB │ gzip:  1.75 kB
dist/assets/index-*.js  154.41 kB │ gzip: 49.80 kB
✓ built in 981ms

$ vite dev + uvicorn backend
frontend: 200
api health: 200
api models: 200
api permissions cfg: 200
```

## 4. Quyết định thiết kế chính

1. **Theme qua CSS variables, không theme prop drilling** — `:root` +
   `:root[data-theme="light"]` chỉ là 2 set biến. Mọi component
   tự respect theme vì CSS cascade. ThemeProvider chỉ toggle
   `data-theme` attribute trên `<html>`.
2. **localStorage persistence với OS preference fallback** — explicit
   user choice lưu vào `windagent:theme`. Nếu chưa có, dùng
   `prefers-color-scheme`. Default dark cho máy dev, light cho user
   bình thường.
3. **GuiGroundingService Protocol với 2 impl** — `Mock` cho dev/CI
   (deterministic, hash-based coordinates), `VisionModelGroundingService`
   stub raise `NotImplementedError` cho Phase 8 sẽ wire. Lựa chọn qua
   `WINDAGENT_GROUNDING_BACKEND` env var.
4. **Grounding service wire-up KHÔNG thay đổi tool_executor** — chỉ
   thêm `app.state.grounding_service` để Phase 8 runner có thể dùng
   khi cần. Không breaking change.
5. **Mock coordinates deterministic** — `hash(target) % spread` cho cùng
   target luôn ra cùng point. Hữu ích cho test + dev (click button A
   luôn ở góc cố định).
6. **Theme toggle button trong StatusBar** — luôn visible, gọn. Icon
   `☀` (sun) khi đang dark = switch to light, `☾` (moon) khi đang
   light = switch to dark.

## 5. Cách dùng

### Theme toggle (frontend)

1. Mở app.
2. Click icon `☀` / `☾` ở góc phải StatusBar.
3. Theme đổi ngay, persist vào localStorage.
4. Reload app → theme giữ nguyên.

### Grounding service (backend dev)

Mặc định `WINDAGENT_GROUNDING_BACKEND=mock` được dùng khi chạy dev. Phase 8
sẽ:

```python
# services/workflow_runner.py (Phase 8 sẽ thêm)
if self._grounding and step.tool_name == "click_xy":
    target = step.params.get("target")
    if target:
        point = await self._grounding.locate(target)
        # Highlight point for confirmation, then call gui.click_xy(point.x, point.y)
```

Hiện tại không có step nào gọi service. Phase 8 full implementation sẽ thêm
tool `click_target(target: str)` mới vào registry.

## 6. Vấn đề phát hiện & xử lý

| Vấn đề | Cách xử lý |
|---|---|
| Phase 6 đã có closeout — không re-do UI scaffold, chỉ thêm 2 enhancement | Skip base files, chỉ modify theme.tsx + StatusBar + main.tsx + styles.css |
| PowerShell killing cũ để lại process cũ | taskkill PID trước khi start mới |

## 7. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Không có E2E test (Playwright) | Download browser binary chậm | Phase 10 hardening |
| `data-theme` không persist khi user dùng private mode | localStorage có thể throw | Đã try/catch trong ThemeProvider |
| `prefers-color-scheme` check lúc SSR — không có ở client only | App là client-only | OK vì detectInitialTheme chỉ chạy trong useState initializer |
| Mock grounding hash function phụ thuộc Python `hash()` randomization per-process | Có thể đổi sang sha256 nếu cần stable | Post-MVP |

## 8. Sẵn sàng cho phase tiếp theo

Theo plan §"Thứ tự ưu tiên" nhóm "hoàn thiện MVP":
- **Phase 8** — GUI grounding thật (Qwen2.5-VL). Interface đã có,
  `VisionModelGroundingService` stub raise NotImplementedError để
  nhắc implement. WorkflowRunner cần thêm click_target tool.
- **Phase 9** — Build Tauri bundle + Python sidecar. Frontend standalone
  dev đã OK, chỉ cần `cargo tauri build` khi user cài Rust.
- **Phase 10** — Hardening + e2e + release note.

## 9. Lệnh kiểm tra nhanh

```powershell
# Backend
cd D:\antigaravity_code\WindAgent\apps\backend
uv run pytest tests/test_gui_grounding.py --timeout=10    # 12 passed

# Frontend (dev)
cd D:\antigaravity_code\WindAgent\apps\desktop
node node_modules\typescript/bin\tsc --noEmit              # OK
PATH="C:\Program Files\nodejs;%PATH%" vite                # http://localhost:5173
```

Trong browser: click icon `☀` / `☾` ở StatusBar → theme đổi.

## 10. Tổng kết MVP status sau enhancement

| Phase | Trạng thái | Note |
|---|---|---|
| 0 — Scope + protocol | ✓ | |
| 1 — Backend FastAPI | ✓ | |
| 2 — SQLite persistence | ✓ | |
| 3 — Tool Executor PyAutoGUI | ✓ | MockGuiAdapter cho dev/CI |
| 4 — Qwen planner qua Ollama | ✓ | MockModelClient cho dev/CI |
| 5 — Workflow Runner + control | ✓ | |
| 6 — Tauri UI | ✓ | Tauri bundle build defer (cần Rust) |
| 6+ — Enhancement (theme + grounding stub) | ✓ | Phiên này |
| 7 — Safe mode + permission gate | ✓ | |
| 8 (prep) — GUI grounding stub | ✓ | Phiên này — VisionModelGroundingService stub raise NotImplementedError |
| 9 — Packaging + sidecar | ⏳ Pending | Tauri shell đã scaffold |
| 10 — Hardening + e2e + release note | ⏳ Pending | |

Còn lại: Phase 8 full (Qwen-VL thật), Phase 9 (build Tauri bundle), Phase 10.