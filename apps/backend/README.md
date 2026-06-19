## apps/backend

Python FastAPI sidecar cho Local Desktop AI Agent.

## Trạng thái hiện tại

- **Phase 1** — REST + WebSocket + in-memory event bus + hardcoded parser
  cho 2 demo. ✓
- **Phase 2** — SQLite persistence (6 bảng theo plan §2.2). ✓
- **Phase 3** — Tool Executor PyAutoGUI (9 tool) + tool registry + tools
  API endpoint. ✓
- **Phase 4** — Qwen3 4B planner qua Ollama + MockModelClient + repair
  prompt + rule-based fallback. ✓
- **Phase 5** — Sequential Workflow Runner với Pause/Resume/Stop/Retry +
  WS control message. ✓
- **Phase 7** — Safe mode + permission gate: tool whitelist runtime,
  `PermissionService` với config + REST + WS resolve, runner check trước
  mỗi step. ✓
- **Phase 8 stub** — `services/gui_adapter.py` có placeholder cho vision
  grounding (chưa thật).

## Layout

```
apps/backend/
├── pyproject.toml          # uv project, deps + pytest config
├── .gitignore              # .venv, __pycache__, *.sqlite
├── main.py                 # FastAPI app, lifespan wires services + runner
├── routers/
│   ├── health.py           # GET /health
│   ├── models.py           # GET /models/health (Phase 4)
│   ├── permissions.py      # Phase 7: GET/PATCH config, POST decide
│   ├── sessions.py         # POST /sessions, GET /sessions/{id}, POST .../messages
│   ├── workflow.py         # GET .../workflow, pause/resume/stop, retry, runner state
│   ├── tools.py            # POST .../tools/{name}, POST .../workflow/run
│   └── websocket.py        # WS /ws/{session_id} + client control messages
├── services/
│   ├── event_bus.py        # in-memory pub/sub + publisher hook
│   ├── event_hooks.py      # mirror event -> DB
│   ├── session_service.py  # session + message store (+ DB mirror)
│   ├── workflow_service.py # planner-aware workflow creator (+ DB mirror)
│   ├── tool_registry.py    # 9 MVP tool metadata + Pydantic param schemas
│   ├── tool_executor.py    # run a single tool, audit DB, emit events
│   ├── gui_adapter.py      # Protocol + PyAutoGui + MockGuiAdapter
│   ├── model_client.py     # ModelClient Protocol + Ollama + Mock (Phase 4)
│   ├── planner_service.py  # planner with model + repair + fallback (Phase 4)
│   ├── permission_service.py # Phase 7: gate + REST/WS resolve
│   └── workflow_runner.py  # Phase 5 — sequential runner + control
├── schemas/
│   ├── event.py            # EventEnvelope + 17 per-event payload models
│   ├── session.py          # ChatSession, Message, CreateSessionResponse
│   └── workflow.py         # Workflow, WorkflowStep, tool whitelist
├── db/
│   ├── database.py         # Async SQLAlchemy wrapper
│   └── models.py           # 6 ORM models
└── tests/                  # 162 tests
```

## Chạy backend local

Yêu cầu: Python 3.10+, [uv](https://docs.astral.sh/uv/).

```powershell
cd apps/backend
uv sync --extra dev

# Production: real PyAutoGUI + Ollama
uv run uvicorn main:app --host 127.0.0.1 --port 8765 --reload

# Dev/test: mock GUI + mock model (không cần desktop/Ollama)
$env:WINDAGENT_MOCK_GUI=1
$env:WINDAGENT_MODEL_BACKEND=mock
uv run uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

Biến môi trường:
- `WINDAGENT_DB_URL` (mặc định `sqlite+aiosqlite:///./windagent.db`)
- `WINDAGENT_MOCK_GUI` (`1` → MockGuiAdapter)
- `WINDAGENT_MODEL_BACKEND` (`mock` | `ollama`, mặc định `ollama`)
- `WINDAGENT_OLLAMA_URL` (mặc định `http://localhost:11434/v1`)
- `WINDAGENT_OLLAMA_MODEL` (mặc định `qwen3:4b-q4`)

## Chạy test

```powershell
cd apps/backend
uv run pytest --timeout=15
```

162 tests, all green (~50s).

## Smoke test thủ công

```powershell
# 1. Health
curl http://127.0.0.1:8765/health

# 2. Model provider health
curl http://127.0.0.1:8765/models/health

# 3. Tạo session + gửi message
$sid = (curl -X POST http://127.0.0.1:8765/sessions | ConvertFrom-Json).session_id
curl -X POST http://127.0.0.1:8765/sessions/$sid/messages `
  -H "Content-Type: application/json" `
  --data-raw '{"content":"M Notepad va go Hello"}'

# 4. Inspect workflow (MockModelClient trả 2 step cho demo này)
curl http://127.0.0.1:8765/sessions/$sid/workflow
```

## Phase tiếp theo

| Phase | Sẽ thay đổi gì ở backend |
|---|---|
| 6 | Tauri UI + WebSocket client (đã có endpoint) |
| 8 | GUI grounding thật (Qwen2.5-VL) |
| 9 | Packaging + developer runbook |
| 10 | Hardening + test e2e + release note |

## Liên kết

- Event shape: `../../docs/event_protocol.md`
- API contract chi tiết: `../../docs/api_contract.md`
- MVP scope: `../../docs/mvp_scope.md`
- Ollama setup: `../../models/README.md`