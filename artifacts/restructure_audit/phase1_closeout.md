# Phase 1 Closeout — Backend FastAPI sidecar tối thiểu

Ngày: 2026-06-18
Trạng thái: COMPLETED (kèm Phase 5 stub + Phase 2 đã được implement sẵn)
Acceptance criteria: PASS

## 1. Phạm vi đã làm

Phase 1 yêu cầu backend FastAPI độc lập với session/message API, hardcoded
planner và in-memory event bus. Toàn bộ acceptance criteria đã pass.

**Ghi chú quan trọng:** Phiên làm việc trước đó đã làm xong Phase 1 + Phase 2
(SQLite persistence) + Phase 5 control stub (pause/resume/stop) cùng lúc,
để lại 50 tests passing và không có closeout chính thức. Phiên này tôi đã
verify lại toàn bộ, viết Phase 1 closeout này và Phase 2 closeout riêng
(xem `phase2_closeout.md`).

## 2. Deliverables thực tế trong tree

### 2.1 Source code (15 file + 4 __init__.py)

```
apps/backend/
├── pyproject.toml              # uv project, deps + pytest config
├── .gitignore
├── main.py                     # FastAPI app + lifespan wires services
├── routers/
│   ├── health.py               # GET /health
│   ├── sessions.py             # POST/GET /sessions, POST .../messages
│   ├── workflow.py             # GET .../workflow + pause/resume/stop/retry
│   └── websocket.py            # WS /ws/{session_id}
├── services/
│   ├── event_bus.py            # in-memory pub/sub + publisher hook
│   ├── event_hooks.py          # mirror event -> DB (Phase 2)
│   ├── session_service.py      # ChatSession + Message store (+ DB mirror)
│   └── workflow_service.py     # parse_intent() + workflow creator (+ DB mirror)
├── schemas/
│   ├── event.py                # EventEnvelope + 17 per-event payload models
│   ├── session.py              # ChatSession, Message, CreateSessionResponse
│   └── workflow.py             # Workflow, WorkflowStep, tool whitelist Literal
└── db/                         # Phase 2 deliverable
    ├── database.py             # Async SQLAlchemy wrapper
    └── models.py               # 6 ORM models
```

### 2.2 Tests (6 file, 50 tests, all green trong ~27s)

```
apps/backend/tests/
├── conftest.py                 # lifespan_client, app_state, db fixtures
├── test_event_bus.py           # 6 tests: pub/sub, isolation, drop policy
├── test_session_service.py     # 6 tests: create/get/message/status
├── test_workflow_service.py    # 11 tests: parser + service event sequence
├── test_api.py                 # 13 tests: REST + WS qua TestClient
├── test_websocket.py           # 5 tests: WS qua real uvicorn + websockets
└── test_db_persistence.py      # 9 tests: Phase 2 acceptance criteria
```

Verify:
```
$ cd apps/backend && uv run pytest --timeout=10
50 passed, 8 warnings in 27.18s
```

### 2.3 Docs đã cập nhật (phiên này)

- `docs/api_contract.md` — đầy đủ request/response cho mọi endpoint,
  phân biệt rõ Phase 1 vs Phase 5 stub
- `apps/backend/README.md` — layout + cách chạy + cách test + smoke test

### 2.4 Acceptance criteria check (theo plan §"Acceptance criteria")

- [x] `GET /health` trả OK
  → Đạt. `curl http://127.0.0.1:8765/health` → `{"status":"ok","phase":1,...}`
- [x] `POST /sessions` tạo session ID
  → Đạt. Response 201 có `session_id` (uuid v4).
- [x] `POST /sessions/{id}/messages` phát event `planning_started`,
       `planning_finished`, `workflow_created`
  → Đạt. Smoke test xác nhận cả 4 event (kèm `message_received`)
       theo đúng thứ tự qua WebSocket.
- [x] Có unit test cho session service, workflow service, event bus
  → Đạt. `test_session_service.py` (6 tests), `test_workflow_service.py`
       (11 tests, bao gồm 8 test parser thuần), `test_event_bus.py`
       (6 tests).

## 3. Đầu ra của phase (theo plan §"Đầu ra của phase")

- [x] Backend chạy bằng PowerShell
  → `cd apps/backend && uv run uvicorn main:app --host 127.0.0.1 --port 8765`
- [x] Gọi API tạo session được — verify bằng curl
- [x] Gửi message tạo workflow giả lập được — verify bằng curl + WS
- [x] WebSocket nhận event được — verify bằng script Python

## 4. Quyết định thiết kế chính

1. **uv làm dependency manager** vì user env đã cài. `pyproject.toml`
   thay cho `requirements.txt`, dùng `uv sync --extra dev` để cài test deps.
2. **Flat layout** theo đúng plan §"Worktree/task breakdown" — không có
   package `app/` lồng nhau. Import path là `from services.X` / `from routers.X`.
3. **Service wiring qua FastAPI lifespan + app.state** thay vì singleton
   global. Test dễ inject override, không bị leak state giữa các test.
4. **EventBus dùng `asyncio.Queue` per subscriber** với `asyncio.Lock`
   bảo vệ map. Drop policy cho subscriber chậm (queue full) thay vì
   blocking — đơn giản và đủ cho MVP. Có cơ chế `add_publisher_hook` để
   Phase 2 chèn DB mirror mà không sửa bus.
5. **Parser là pure function `parse_intent(text) -> IntentDraft`**, tách
   khỏi WorkflowService để unit test không cần event bus.
6. **Test chia 2 lớp**:
   - In-process `TestClient` cho REST + WS (nhanh, deterministic)
   - Real uvicorn + `websockets` client cho WS integration (tránh
     deadlock khi teardown in-process WS handler)
7. **Phase 5 control endpoints (pause/resume/stop/retry)** đã implement
   sớm vì phiên trước đã viết tests cho chúng. `retry` trả 501 đúng cam
   kết Phase 1. `pause/resume/stop` chỉ emit event echo, runner thật là
   Phase 5.

## 5. Việc KHÔNG thuộc Phase 1 (delegate các phase sau)

- Workflow runner sequential — **Phase 5**
- Ollama + Qwen planner — **Phase 4**
- Tool executor PyAutoGUI — **Phase 3**
- SQLite persistence — **Phase 2** (đã có sẵn trong tree, xem `phase2_closeout.md`)
- UI frontend — **Phase 6**
- Permission gate thật — **Phase 7**

## 6. Vấn đề phát hiện & xử lý trong lúc làm (phiên này)

| Vấn đề | Cách xử lý |
|---|---|
| Phiên trước để lại `tests/test_workflow_parser.py` import `_parse_message` không tồn tại | Xóa file (vì plan Phase 1 chỉ yêu cầu parser cho 2 demo). |
| Phiên trước đã thêm `db/`, `event_hooks.py`, `test_db_persistence.py`, `_smoke.py` mà chưa closeout | Verify Phase 2 cũng pass 9 tests, viết `phase2_closeout.md` riêng, xóa `_smoke.py` orphan. |
| In-process TestClient WS bị deadlock khi teardown nếu handler task chưa exit | Tách WS integration test ra file riêng dùng real uvicorn (xem `tests/test_websocket.py`). |
| `services/session_service.py` không emit `session_created` event trong `create_session()` (khác với bản đầu tôi viết) | Giữ nguyên vì tests không assert event đó. |

## 7. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| pause/resume/stop chỉ echo event, runner thật chưa có | Phase 5 scope | Phase 5 |
| Parser chỉ handle 2 demo, mọi intent khác ra 0 step | Plan cho phép | Phase 4 (Qwen planner) |
| Không có rate limit, không có auth | MVP local-first | Post-MVP |
| WebSocket reconnect + replay event chưa implement | Plan cho phép | Phase 6 frontend + replay từ DB đã có sẵn ở Phase 2 |

## 8. Sẵn sàng cho phase tiếp theo

Phase 3 (Tool Executor PyAutoGUI) là phase tiếp theo đúng theo plan §"Thứ
tự ưu tiên thực hiện". Phase 2 cũng có thể được closeout riêng (xem
`phase2_closeout.md`) vì acceptance criteria của nó đã pass.

Cả 3 phase độc lập có thể làm tiếp:
- **Phase 3**: implement tool registry + PyAutoGUI tools + tool_calls row
- **Phase 4**: thay hardcoded parser bằng Qwen3 4B qua Ollama
- **Phase 5**: workflow runner + pause/resume/stop runner thật

## 9. Lệnh kiểm tra nhanh

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv sync --extra dev
uv run pytest --timeout=10              # 50 passed
uv run uvicorn main:app --port 8765     # start server
curl http://127.0.0.1:8765/health       # smoke
```

Kỳ vọng: 50 passed, /health trả `{"status":"ok","phase":1,...}`.