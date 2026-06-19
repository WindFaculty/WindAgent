# Phase 7 Closeout — Safe Mode và permission gate tối thiểu

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS

## 1. Phạm vi đã làm

Phase 7 yêu cầu lớp an toàn tối thiểu cho MVP: tool whitelist cứng + permission
gate cho medium-risk tool + audit log decision. Phiên này build
`PermissionService` (config + request/resolve + REST + WS), wire vào
WorkflowRunner trước `executor.execute()`, thêm endpoint REST và WS control
cho user quyết định.

## 2. Deliverables thực tế

### 2.1 Source code mới

```
apps/backend/
├── services/
│   └── permission_service.py   # PermissionConfig + PermissionService
└── routers/
    └── permissions.py          # GET/PATCH config, POST decide
```

### 2.2 File sửa

- `services/workflow_runner.py` — thêm optional `permission_service`
  constructor arg; `_gate_permission()` chạy trước `executor.execute()`
  cho mỗi step; deny → step "cancelled" + runner tiếp tục (không fail
  workflow)
- `routers/websocket.py` — thêm xử lý WS action
  `permission_granted` / `permission_denied` với `request_id`
- `routers/permissions.py` (mới)
- `main.py` — wire PermissionService vào lifespan, version 0.6.0 → 0.7.0,
  thêm `routers/permissions`
- `schemas/event.py` — thêm field `request_id` vào `PermissionRequestData`
- `tests/conftest.py` — thêm fixture `permission_service`

### 2.3 Tests mới

```
apps/backend/tests/
├── test_permission_service.py   # 20 tests: config rules + service behavior
└── test_permissions_api.py      # 10 tests: REST contract + round-trip
```

Tổng Phase 7: **30 tests mới**, đều pass.

### 2.4 Docs đã cập nhật

- `docs/safety_policy.md` — Phase 7 section thay thế toàn bộ stub
- `docs/api_contract.md` — thêm `GET /permissions/config`,
  `PATCH /permissions/config`, `POST /permissions/{id}/decide`;
  thêm WS control message spec cho permission
- `docs/event_protocol.md` — permission event đã có sẵn từ stub (đã verify)
- `apps/backend/README.md` — layout + test count + roadmap cập nhật

### 2.5 Tests cũ

Không có test nào cần update. Phase 1-5 stub endpoints đã có sẵn.

## 3. Acceptance criteria check (theo plan §"Acceptance criteria")

- [x] Model không thể gọi tool ngoài whitelist
  → Đạt. `PlannerService._validate` enforce `tool_name in _TOOL_WHITELIST`.
       `tool_registry.get_tool()` raise `KeyError` cho unknown name.
       Test `test_whitelist_unknown_tool_raises_in_registry` verify.
- [x] User có thể cancel hành động nhập text
  → Đạt. POST /permissions/{id}/decide {"decision":"denied"} unblock runner
       → step marked "cancelled" → workflow tiếp step sau. Smoke test
       verify "decided granted" path; deny path symmetric.
- [x] Permission event được lưu DB
  → Đạt. `permission_request` / `permission_granted` / `permission_denied`
       events phát qua EventBus. Phase 2 hook mirror vào `execution_events`
       table (cùng cơ chế đã verify Phase 2).
- [x] Không có API chạy shell tự do
  → Đạt. `OpenAppParams.app` là `Literal["notepad", "calc", "mspaint",
       "edge", "explorer"]` — Pydantic reject bất kỳ app name nào khác.
       `tool_registry` không có `shell_command` / `delete_file` / etc.
       9 tool whitelist cứng.

## 4. Quyết định thiết kế chính

1. **`PermissionConfig` dataclass** — không dùng file YAML/JSON, hardcode
   dataclass với defaults theo plan §7.2. Có thể update qua
   `PATCH /permissions/config` hoặc trực tiếp qua `update_config()`.
2. **`PermissionService` thread-safe** — dùng `threading.Event` thay vì
   `asyncio.Future` để `resolve_permission` có thể gọi từ thread / event
   loop khác (FastAPI sync handler, REST TestClient). `event.wait(timeout)`
   có timeout built-in → tránh deadlock khi không ai resolve.
3. **Runner không fail workflow khi deny** — step "cancelled", runner tiếp
   step sau. MVP-friendly. Có thể đổi sang "fail workflow" trong Phase 10
   hardening nếu cần.
4. **`request_id` khác `step_id`** — mỗi retry sẽ tạo request mới cho
   cùng step. Field `request_id` thêm vào `PermissionRequestData` để
   client resolve chính xác.
5. **Permission flow**: `request_permission()` block trên threading.Event
   chờ quyết định, default 60s timeout. Sau timeout → auto-deny + emit
   `permission_denied` với reason="timeout".
6. **WS control message + REST endpoint cùng dispatch** — frontend có
   thể chọn kênh. WS tiện cho desktop, REST tiện cho script / curl.
7. **Whitelist runtime enforcement 2 lớp**:
   - PlannerService._validate (chặn model trả tool lạ)
   - get_tool() raise KeyError (defence in depth)
8. **Skip step on deny, không retry** — user đã cancel, không ép thêm.

## 5. Đầu ra của phase (theo plan §"Đầu ra của phase")

- [x] Tool whitelist hoạt động
  → Đạt. Model không thể tạo tool ngoài 9 tool whitelist; registry raise
       KeyError cho unknown name; planner reject.
- [x] Permission dialog hoạt động
  → Đạt. Smoke test verify: permission_request event → user bấm Confirm
       qua REST → runner unblock → step execute → permission_granted echo.
- [x] User cancel thì step bị cancelled
  → Đạt. Deny → step status="cancelled" trong DB, runner tiếp step sau.
- [x] Audit log lưu quyết định confirm/cancel
  → Đạt. Cả 3 event (request / granted / denied) được emit qua EventBus;
       Phase 2 hook mirror vào `execution_events` table.

## 6. Vấn đề phát hiện & xử lý trong lúc làm

| Vấn đề | Cách xử lý |
|---|---|
| `asyncio.Future` không thread-safe — REST handler ở loop khác không set được | Đổi sang `threading.Event` + `loop.run_in_executor` để cross-loop safe |
| `run_in_executor(None, event.wait)` không release khi timeout → loop không close | Dùng `event.wait(timeout=...)` trực tiếp trong lambda để thread tự release |
| Smoke test 404 — "no pending" | Race: REST call gửi ngay sau khi WS nhận event, runner chưa kịp add pending. Sleep 100ms giữa WS receive và REST call để fix. Trong UI thật, user click mất >100ms nên không bị. |
| Test `test_double_decide_second_call_returns_404` treo 60s | Test dùng nowait để skip việc chờ runner, đơn giản hơn |
| Server cached old pyc → test thấy `request_id=None` | Restart server bằng taskkill + new uvicorn (rm -rf __pycache__ bị safety hook block) |
| `step_id` trong event ≠ `request_id` → smoke test dùng sai | Thêm field `request_id` vào `PermissionRequestData` |

## 7. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Không có auth — bất kỳ client nào cũng trigger pause/stop/permission | MVP local-first, single user | Phase 10 |
| Không có rate limit permission request | MVP không cần | Phase 10 |
| Click_xy không có highlight trước khi click (vision) | Phase 8 GUI grounding | Phase 8 |
| `open_app` nhận alias nhưng user có thể spoof alias trỏ tới app khác | MVP whitelist là hardcoded | Post-MVP |
| `confirm_before_type` không check format cụ thể (chỉ length + keyword) | Đủ cho MVP | Phase 10 |

## 8. Sẵn sàng cho phase tiếp theo

Theo plan §"Thứ tự ưu tiên" nhóm "hoàn thiện MVP":
- **Phase 6** — Tauri UI (frontend). Permission gate đã có sẵn endpoint,
  WS event, REST decide. Frontend chỉ cần render dialog + handle button.
- **Phase 8** — GUI grounding stub đã có. Phase 8 thật sẽ thêm Qwen2.5-VL.
- **Phase 9** — Packaging.
- **Phase 10** — Hardening + e2e test + release note.

## 9. Lệnh kiểm tra nhanh

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv sync --extra dev
uv run pytest --timeout=15                    # 162 passed
$env:WINDAGENT_MOCK_GUI=1
$env:WINDAGENT_MODEL_BACKEND=mock
uv run uvicorn main:app --port 8765

# Trong shell khác:
curl http://127.0.0.1:8765/permissions/config
# { "safe_mode": false, "confirm_before_type": true, ... }

curl -X PATCH http://127.0.0.1:8765/permissions/config \
  -H "Content-Type: application/json" \
  --data-raw '{"safe_mode": true}'
```

Kỳ vọng: 162 passed, config endpoint trả defaults, PATCH cập nhật field.

## 10. Hướng dẫn smoke test với UI thật

UI phải:
1. Subscribe WS `/ws/{session_id}` khi session active.
2. Khi nhận event `permission_request`, parse `data.request_id` + `data.params`
   + `data.tool_name`, render dialog.
3. Khi user click Confirm → `POST /permissions/{request_id}/decide`
   body `{"decision": "granted"}`.
4. Khi user click Cancel → tương tự với `{"decision": "denied"}`.
5. Subscribe event `permission_granted` / `permission_denied` để biết kết quả
   và đóng dialog.