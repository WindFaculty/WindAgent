# Phase 2 Closeout — SQLite persistence và audit log

Ngày: 2026-06-18
Trạng thái: COMPLETED (đã có sẵn trong tree từ phiên trước, được verify lại)
Acceptance criteria: PASS

## 1. Phạm vi đã làm

Phase 2 yêu cầu lưu session / message / workflow / step / event vào SQLite
để backend local-first. Toàn bộ acceptance criteria pass. Phiên này
chỉ verify và viết closeout — implementation thật đã có sẵn từ phiên
trước (cùng lúc với Phase 1), đã chạy ổn định với 50 tests.

## 2. Deliverables thực tế trong tree

### 2.1 Source code mới cho Phase 2

```
apps/backend/
├── db/
│   ├── __init__.py
│   ├── database.py             # Async SQLAlchemy wrapper (aiosqlite)
│   └── models.py               # 6 ORM models
└── services/
    └── event_hooks.py          # Publisher hook mirror event -> DB
```

### 2.2 File đã chỉnh sửa cho Phase 2

- `pyproject.toml` — thêm `sqlalchemy>=2.0.51`, `aiosqlite>=0.22.1`,
  `httpx-ws`, `pytest-timeout`
- `main.py` — lifespan khởi tạo DB + init_models, wire hook vào EventBus,
  truyền `db` vào SessionService/WorkflowService
- `services/session_service.py` — thêm `_db` optional, mirror session +
  message vào DB trong `create_session`, `add_user_message`,
  `update_status`
- `services/workflow_service.py` — thêm `_db`, mirror workflow + steps
  vào DB trong `create_for_message`
- `services/event_bus.py` — thêm `add_publisher_hook(callback)` để plugin
  DB mirror không phải sửa bus
- `tests/conftest.py` — thêm `db` fixture + reset DB trước mỗi test

### 2.3 Schema (6 bảng theo plan §2.2)

| Bảng | Cột chính | Index |
|---|---|---|
| `chat_sessions` | id (PK), created_at, updated_at, status | — |
| `messages` | id (PK), session_id (FK), sender, content, created_at | ix_messages_session_id_created_at |
| `workflows` | id (PK), session_id (FK), status, created_at, updated_at | — |
| `workflow_steps` | id (PK), workflow_id (FK), order_index, name, tool_name, params_json, status | ix_workflow_steps_workflow_id_order |
| `tool_calls` | id (PK), session_id, step_id, tool_name, input_json, output_json, status | ix_tool_calls_session_id_created_at |
| `execution_events` | id (PK), session_id, event_type, data_json, created_at | ix_execution_events_session_id_created_at |

UUID lưu dưới dạng `String(36)` (SQLite không có UUID native). JSON payload
lưu dưới `Text` (SQLite có JSON affinity nhưng giữ text cho đơn giản).

`tool_calls` table đã tồn tại nhưng Phase 3 mới fill data.

### 2.4 Tests mới cho Phase 2

`tests/test_db_persistence.py` — 9 tests, all pass:

1. `test_create_session_writes_to_chat_sessions_table` — Phase 2 §4.1
2. `test_update_status_writes_to_db`
3. `test_user_message_persisted` — Phase 2 §4.2
4. `test_workflow_and_steps_persisted` — Phase 2 §4.3
5. `test_events_mirrored_into_execution_events` — Phase 2 §4.4
6. `test_pause_emits_user_paused_event_in_db`
7. `test_data_survives_app_restart` — restart cycle, đọc lại từ file DB
8. `test_tool_calls_table_exists` — schema check
9. `test_all_six_tables_created_on_startup` — schema check

## 3. Acceptance criteria check (theo plan)

- [x] Tạo session → DB có row
  → Đạt. `test_create_session_writes_to_chat_sessions_table`.
- [x] Gửi message → DB có message
  → Đạt. `test_user_message_persisted`.
- [x] Workflow được tạo → DB có workflow + steps
  → Đạt. `test_workflow_and_steps_persisted` kiểm tra cả workflow row
       + 2 step rows với order_index đúng.
- [x] Event được stream và cũng được lưu vào DB
  → Đạt. `test_events_mirrored_into_execution_events` kiểm tra cả 4 event
       (`message_received`, `planning_started`, `planning_finished`,
       `workflow_created`) đều có trong `execution_events` với `data_json`
       round-trip JSON-safe.
- [x] Có test xác nhận event không bị mất khi workflow chạy
  → Đạt. `test_events_mirrored_into_execution_events` + 6 test khác
       trong `test_db_persistence.py`.
- [x] SQLite DB tự tạo khi backend khởi động
  → Đạt. `test_all_six_tables_created_on_startup` verify 6 bảng tồn tại
       sau lifespan.
- [x] Có thể xem lại workflow của session cũ
  → Đạt. `test_data_survives_app_restart` — restart engine, đọc lại
       cùng file DB, verify rows còn nguyên.

## 4. Quyết định thiết kế chính

1. **SQLAlchemy 2.0 async + aiosqlite** thay vì sqlite3 trực tiếp. Lý do:
   cần `async with` để không block event loop của FastAPI/uvicorn, và
   SQLAlchemy 2.0 typed API (`Mapped[str]`, `mapped_column`) dễ đọc hơn.
2. **`Database` class là thin wrapper** quanh `AsyncEngine` +
   `async_sessionmaker`. `session()` là `@asynccontextmanager` commit
   on clean exit, rollback on exception — quy ước rõ ràng cho mọi
   service dùng.
3. **EventBus hook qua `add_publisher_hook(callback)`** thay vì hardcode
   trong bus. Hook là async function `(session_id, envelope) -> None`.
   `make_execution_event_hook(db)` factory trả về hook ghi vào
   `execution_events`. Bus vẫn không biết về DB.
4. **Service API giữ nguyên shape, chỉ thêm `db` optional constructor arg.**
   Khi `db=None`, service chạy pure-RAM như Phase 1 — backward compatible
   với test cũ không cần DB.
5. **Mỗi test có fresh DB qua temp file.** `conftest.py` set
   `WINDAGENT_DB_URL` tới file `tempfile.mkstemp(...)` trước khi import
   `main`, rồi `drop_all + create_all` trước mỗi test. Test
   `test_websocket.py` cần file DB thật (không `:memory:`) vì engine
   phải reachable từ coroutine khác.
6. **UUIDs lưu `String(36)`** — SQLite không có UUID type, làm việc này
   tránh dialect-specific code.
7. **JSON payload lưu `Text`** — SQLite có JSON1 extension nhưng giữ text
   cho đơn giản, Pydantic model đảm bảo serialize sẵn.

## 5. Đầu ra của phase (theo plan §"Đầu ra của phase")

- [x] SQLite DB tự tạo khi backend khởi động → `init_models()` trong lifespan
- [x] Session/message/workflow/event được lưu → test_db_persistence.py
- [x] Có thể xem lại workflow của session cũ → `test_data_survives_app_restart`

## 6. Vấn đề phát hiện & xử lý trong lúc verify (phiên này)

| Vấn đề | Cách xử lý |
|---|---|
| Phiên trước để `_smoke.py` orphan ở apps/backend/ root | Verify không ai reference, xóa sạch. |
| Test count thực tế là 50 (gồm Phase 2 + Phase 5 stub test), không phải 41 như tôi estimate ban đầu | Cập nhật phase1_closeout.md cho chính xác. |
| Phiên trước không có closeout cho Phase 2 | Viết file này. |

## 7. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Không có DB migration tool (Alembic) | MVP chỉ cần create_all idempotent | Phase 10 hardening |
| Không có retry khi SQLite bị lock | WAL mode chưa bật | Phase 10 hardening |
| `tool_calls` table tồn tại nhưng Phase 3 mới fill data | Phase 3 scope | Phase 3 |
| Không có bulk delete / vacuum | MVP không cần | Post-MVP |
| SQLite file `windagent.db` mặc định ở working dir, không có path config | MVP chấp nhận được | Phase 9 (packaging) |

## 8. Sẵn sàng cho Phase 3

Phase 3 (Tool Executor PyAutoGUI) có thể bắt đầu ngay:
- `tool_calls` table đã có sẵn, schema đúng theo plan §2.3
- `event_bus` đã có hook mechanism, Phase 3 chỉ cần thêm hook mirror
  `tool_call_started`/`tool_call_finished`
- Service interface (`ToolRegistry`, `ToolExecutor`) sẽ được thêm ở
  `services/tool_registry.py`, `services/tool_executor.py` theo plan
  §3.1.

## 9. Lệnh kiểm tra nhanh

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv sync --extra dev
uv run pytest tests/test_db_persistence.py --timeout=10    # 9 passed
uv run uvicorn main:app --port 8765                       # lifespan tạo DB
ls windagent.db                                           # file SQLite xuất hiện
```

Kỳ vọng: 9 tests pass cho `test_db_persistence.py`, file `windagent.db`
được tạo tự động khi lifespan chạy.