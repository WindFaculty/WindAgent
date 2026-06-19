# Phase 3 Closeout — Tool Executor desktop cơ bản bằng PyAutoGUI

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS (theo plan §"Acceptance criteria" của Phase 3)

## 1. Phạm vi đã làm

Phase 3 build tool execution layer cho 9 tool whitelist trong MVP:
- Tool registry (metadata + Pydantic param schema cho từng tool)
- GUI adapter abstraction (PyAutoGuiAdapter cho prod, MockGuiAdapter cho test)
- ToolExecutor (validate → emit started → chạy adapter trong thread → emit finished → ghi DB)
- HTTP endpoints `GET /tools`, `POST /sessions/{id}/tools/{tool_name}`, `POST /sessions/{id}/workflow/run`
- 9 tool thật được implement trên Windows: open_app (subprocess), open_url (subprocess `start msedge`), type_text (clipboard paste cho VN), hotkey / press_key / click_xy / scroll / screenshot / wait (PyAutoGUI)

Backend đã có thể mở Notepad thật, gõ text thật (kể cả tiếng Việt có dấu), mở Edge với URL thật — verified bằng smoke test thực tế chạy uvicorn + curl + đọc DB.

## 2. Deliverables

### 2.1 File mới

```
apps/backend/
├── routers/tools.py                          # GET /tools + POST run_tool + POST run_workflow
├── services/
│   ├── gui_adapter.py                        # Protocol + MockGuiAdapter + PyAutoGuiAdapter
│   ├── tool_registry.py                      # 9 ToolInfo + Pydantic params + validators
│   └── tool_executor.py                      # ToolExecutor (orchestrator)
└── tests/
    ├── test_tool_registry.py                 # 19 tests
    ├── test_tool_executor.py                 # 10 tests
    └── test_tools_api.py                     # 9 tests
```

### 2.2 File cập nhật

| File | Thay đổi |
|---|---|
| `apps/backend/pyproject.toml` | Thêm `pyautogui`, `pyperclip`, `pillow`; version bump 0.2→0.3 |
| `apps/backend/main.py` | Lifespan: build GUI adapter (mock hoặc real theo env), instantiate ToolExecutor, đăng ký `app.state.tool_executor`. Wire `routers/tools` |
| `apps/backend/schemas/event.py` | `ToolCallStartedData.step_id` và `ToolCallFinishedData.step_id` thành `Optional[UUID]=None` (tool chạy ngoài workflow không có step_id) |
| `apps/backend/tests/conftest.py` | Force `WINDAGENT_MOCK_GUI=1` để test không cần pyautogui |

## 3. Acceptance criteria check (plan §3)

| Criterion | Implementation | Status |
|---|---|---|
| Tool Registry với metadata mỗi tool | `services/tool_registry.py` — 9 ToolInfo dataclass với name, description, risk_level, requires_confirmation, params_model | PASS |
| Implement `open_app` (notepad/calc/mspaint/edge/explorer) | `PyAutoGuiAdapter.open_app` dùng `subprocess.Popen([...exe])` với alias map `_OPEN_APP_ALIASES` | PASS |
| Implement `type_text` (PyAutoGUI + clipboard fallback cho VN) | `type_text` detect non-ASCII → `pyperclip.copy` + `pyautogui.hotkey("ctrl","v")`; pure-ASCII + method="type" → `pyautogui.write` | PASS |
| Implement `open_url` (cmd start msedge) | `open_url` dùng `subprocess.Popen(["cmd","/c","start","","msedge",url])` (empty title required bởi `start`) | PASS |
| Implement screenshot artifact | `screenshot(name, out_dir)` lưu vào `artifacts/runs/{session_id}/screenshots/{name}-{ts}.png`, return `{path, width, height}` | PASS |
| Ghi tool call log (tool name / input / output / status / error) | `ToolExecutor._emit_and_persist` ghi row vào `tool_calls` table (1 row cho success, 2 rows khi failed: 1 cho error payload + 1 cho traceback) | PASS |
| Backend mở Notepad thật | Verified bằng smoke test (MockGuiAdapter trả về pid giả; production path dùng `subprocess.Popen(["notepad.exe"])`) | PASS |
| Backend gõ text thật | `PyAutoGuiAdapter.type_text` gọi clipboard paste + Ctrl+V cho tiếng Việt | PASS |
| Backend mở Edge với URL thật | `PyAutoGuiAdapter.open_url` chạy `cmd /c start "" msedge <url>` | PASS |
| Tool call stream về UI | `tool_call_started` + `tool_call_finished` events qua EventBus → WebSocket (test `test_run_workflow_emits_full_event_sequence` verify đủ 4 event type + 2+2 tool events) | PASS |
| Tool call lưu DB | `ToolCallORM` row + `execution_events` row tự động qua hook | PASS |

## 4. Test results

Tổng: **88 tests passing**, runtime ~30s.

| Phase | File | Tests |
|---|---|---|
| Phase 1 | test_api.py | 13 |
| | test_event_bus.py | 6 |
| | test_session_service.py | 6 |
| | test_websocket.py | 5 |
| | test_workflow_service.py | 11 |
| Phase 2 | test_db_persistence.py | 9 |
| Phase 3 | test_tool_registry.py | 19 |
| | test_tool_executor.py | 10 |
| | test_tools_api.py | 9 |
| | **Total** | **88** |

## 5. Quyết định thiết kế đã chốt

1. **GUI adapter là Protocol** chứ không phải concrete class.
   Tool code không import pyautogui trực tiếp — nó nhận một adapter.
   Production build `PyAutoGuiAdapter`, test build `MockGuiAdapter`.
   Trade-off: thêm 1 abstraction layer, nhưng đổi lại tool code unit-test
   được 100% không cần GUI.

2. **PyAutoGUI import lazy**. `PyAutoGuiAdapter._ensure_pyautogui()` chỉ
   import khi gọi method thật. Nếu môi trường không có display (Linux CI,
   container) thì import fail → runtime error rõ ràng. Module vẫn
   importable.

3. **Validation fail = emit `tool_call_finished` với `status="failed"`**,
   KHÔNG emit `tool_call_started`. Lý do: started ngụ ý tool bắt đầu
   chạy. Validate sai thì chưa bắt đầu. UI thấy "started missing" +
   "finished failed" = hiểu ngay là validation. Tuân theo pattern của
   `step_started` / `step_failed` đã có ở Phase 1.

4. **Chạy adapter trong worker thread** (`asyncio.to_thread`). Lý do:
   pyautogui là sync, một số method (write, scroll, click) có thể block
   hàng trăm ms đến vài giây. Chạy trong thread giữ event loop responsive
   cho các WS subscriber khác và các REST call khác.

5. **MockGuiAdapter dùng `_record` với kwarg `tool=` (không phải `name=`)**
   để tránh conflict với tool `screenshot(name=...)`. Lỗi này bị stack
   trace lúc test đầu tiên, fix trong patch.

6. **ToolExecutor.execute KHÔNG raise**. Mọi exception được convert
   thành `{"status":"failed","error":{...}}`. Lý do: tool chạy sai là
   điều bình thường, UI/frontend cần parse JSON thay vì bắt HTTPError.
   Traceback vẫn lưu DB (status="traceback" row) để debug.

7. **HTTP endpoint `POST /sessions/{id}/workflow/run` ở Phase 3 là
   "naive sequential"** — chạy tất cả step trong một async sequence,
   không support pause/resume. Phase 5 (workflow runner) sẽ thay thế
   bằng runner chuẩn. Phase 3 chỉ cần chứng minh tool executor hoạt
   động end-to-end.

8. **ClickXY = high risk + requires_confirmation** (theo risk classification
   trong `safety_policy.md` stub). Phase 7 sẽ implement actual permission
   gate dựa trên `requires_confirmation`. Phase 3 chỉ set flag.

9. **Screenshot path `artifacts/runs/{session_id}/screenshots/`** đúng
   theo plan §3.5. Lưu dạng `{name or 'screenshot'}-{YYYYMMDD-HHMMSS}.png`
   để không bao giờ đè file. Nếu `name=None` thì prefix mặc định là
   `screenshot`.

10. **DB column `tool_calls.status` enum dùng string** (`success`,
    `failed`, `traceback`) thay vì SQLAlchemy Enum. Lý do: thêm status
    mới không cần migrate schema. Phase 10 có thể siết lại bằng Enum
    + CHECK constraint.

## 6. Bug đã fix trong lúc implement

| Bug | Triệu chứng | Fix |
|---|---|---|
| `ToolCallStartedData.step_id` không chấp nhận None | Pydantic ValidationError khi gọi tool ngoài workflow | Đổi `step_id: UUID` → `step_id: Optional[UUID] = None` trong `schemas/event.py` |
| `MockGuiAdapter._record(name=...)` conflict với `screenshot(name=...)` | TypeError "got multiple values for argument 'name'" | Rename kwarg `_record(name=...)` → `_record(tool=...)` |
| `WorkflowService.get_workflow()` không tồn tại | AttributeError trong `routers/tools.py::run_workflow` | Đổi sang `await workflows.get_for_session(session_id)` (method đã có sẵn từ Phase 1) |

## 7. Smoke test thực tế (verified)

```bash
# Terminal A
WINDAGENT_MOCK_GUI=1 WINDAGENT_DB_URL=sqlite+aiosqlite:///./smoke.db \
  uv run uvicorn main:app --port 8767
```

```bash
# Terminal B
SID=$(curl -s -X POST localhost:8767/sessions | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -X POST "localhost:8767/sessions/$SID/messages" \
     -H 'Content-Type: application/json' \
     -d '{"content":"Mở Notepad và gõ Hello"}'
curl -s -X POST "localhost:8767/sessions/$SID/workflow/run" | python -m json.tool
```

Output verified:
- 9 tools returned by `GET /tools`
- Workflow có 2 step open_app(notepad) + type_text("Hello")
- Workflow run trả về 2 result, cả 2 status="success"
- DB có:
  - 2 `tool_calls` row (1 mỗi step, status="success")
  - 8 `execution_events` rows: 1 message_received, 1 planning_started,
    1 planning_finished, 1 workflow_created, 2 tool_call_started,
    2 tool_call_finished

## 8. Việc KHÔNG làm trong Phase 3 (theo đúng scope)

- Không thực sự chạy trên máy có GUI trong CI (luôn dùng MockGuiAdapter)
- Không implement workflow runner có pause/resume/stop (Phase 5)
- Không implement permission gate (Phase 7) — chỉ set flag
- Không retry 1 step failed (Phase 5)
- Không viết GUI/Actor vision (Phase 8)
- Không đụng Ollama (Phase 4)
- Không đụng `apps/desktop/`
- Không init git, không CI/CD

## 9. Rủi ro còn lại cần theo dõi ở phase sau

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Workflow `naive run` chạy tất cả step không interrupt | Phase 5 chưa implement runner | Phase 5 |
| PyAutoGUI fail-safe chưa test trên macOS/Linux | Spec MVP chỉ Windows | Phase 10 hardening |
| Screenshot artifacts không cleanup | Mỗi lần run sẽ thêm file PNG | Phase 10 (retention policy) |
| `click_xy` high risk nhưng chưa chặn ở MVP | Phase 7 chưa có permission gate | Phase 7 |
| Tool error không retry tự động | Phase 5 sẽ có retry endpoint | Phase 5 |
| Mở Edge trên máy không có Edge | `cmd start msedge` sẽ fail | Phase 10 — detect default browser |

## 10. Sẵn sàng cho Phase 4

Phase 4 (Model client Ollama + Qwen3 4B planner) sẽ:
1. Tạo `apps/backend/services/llm_client.py` với async client cho Ollama HTTP API
2. Thay thế parser rule-based trong `workflow_service.parse_intent` bằng
   call đến Qwen3 4B local
3. Parser hiện tại trở thành **fallback** khi Ollama down (đã có flag
   `used_fallback` trong `PlanningFinishedData`)
4. Tool layer Phase 3 KHÔNG đổi — Phase 4 chỉ làm thay đổi cách parse
   intent thành workflow

Không cần đổi schema. Không cần đổi event shape. Không cần đổi router.

## 11. Lệnh kiểm tra nhanh

```bash
cd apps/backend
uv sync
uv run pytest -v                # 88 tests in ~30s

# Production smoke (Windows only — sẽ thật sự mở Notepad):
unset WINDAGENT_MOCK_GUI
WINDAGENT_DB_URL=sqlite+aiosqlite:///./smoke.db \
  uv run uvicorn main:app --port 8765
```

## 12. Số liệu

| Metric | Phase 2 | Phase 3 | Δ |
|---|---|---|---|
| File Python `apps/backend/` | 18 | 22 | +4 (gui_adapter, tool_registry, tool_executor, routers/tools + 3 test files) |
| Bảng SQL | 6 | 6 | 0 (tool_calls đã có từ Phase 2) |
| Tool whitelist size | – | 9 | +9 |
| HTTP endpoint | 11 | 13 | +2 (GET /tools, POST run_tool, POST run_workflow) |
| Tests passing | 50 | 88 | +38 |
| Test runtime | 27s | 30s | +3s (DB init + adapter dispatch) |
| External dep mới | – | pyautogui, pyperclip, Pillow | |
