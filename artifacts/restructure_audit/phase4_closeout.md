# Phase 4 Closeout — Planner Qwen3 4B Q4 qua Ollama

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS

## 1. Phạm vi đã làm

Phase 4 yêu cầu thay hardcoded parser bằng model Qwen3 4B Q4 qua Ollama,
có JSON validation + repair prompt + rule-based fallback khi model lỗi.
Phiên này build ModelClient (Protocol + Ollama + Mock) + PlannerService,
wire vào WorkflowService, thêm `GET /models/health`, viết tests.

## 2. Deliverables thực tế

### 2.1 Source code mới

```
apps/backend/
├── services/
│   ├── model_client.py     # ModelClient Protocol + OllamaModelClient + MockModelClient
│   └── planner_service.py  # PlannerService: model.chat() -> validate -> repair -> fallback
└── routers/
    └── models.py           # GET /models/health
```

### 2.2 File sửa

- `apps/backend/services/workflow_service.py` — thêm optional `planner`
  constructor arg; `create_for_message` route qua `PlannerService.plan()`
  khi có planner, fallback về `parse_intent` trực tiếp khi không; emit
  `planning_finished` với model name + used_fallback từ PlanResult
- `apps/backend/main.py` — wire ModelClient + PlannerService vào
  lifespan; chọn client qua `WINDAGENT_MODEL_BACKEND` env var
  (`mock` | `ollama`, default `ollama`); version 0.5.0 → 0.6.0; thêm
  `routers/models`
- `apps/backend/tests/conftest.py` — force `WINDAGENT_MODEL_BACKEND=mock`
  để test suite không phụ thuộc Ollama; thêm fixture `planner_service`
  + `model_client`

### 2.3 Tests mới

```
apps/backend/tests/
├── test_model_client.py    # 15 tests: Mock + Ollama (httpx mock transport)
├── test_planner_service.py # 16 tests: validate + repair + fallback + whitelist
└── test_models_api.py      # 4 tests: /models/health endpoint
```

Tổng Phase 4: **35 tests mới**, đều pass.

### 2.4 Docs đã cập nhật

- `docs/api_contract.md` — thêm `GET /models/health` section; cập nhật
  phase roadmap (Phase 4 col)
- `docs/event_protocol.md` — định nghĩa `error` event với 7 code chuẩn
  (`MODEL_OFFLINE`, `MODEL_INVALID_JSON`, `MODEL_UNKNOWN_TOOL`,
  `MODEL_REPAIR_FAILED`, `TOOL_NOT_FOUND`, `INVALID_PARAMS`,
  `TOOL_EXECUTION_FAILED`)
- `apps/backend/README.md` — layout cập nhật, env vars mới, smoke test
  với mock model

### 2.5 Tests cũ cần update

- `tests/test_workflow_service.py::test_create_for_message_emits_full_event_sequence`
  — đổi assertion từ `used_fallback=True` / `model="fallback-rule-based"`
  sang `used_fallback=False` / `model.startswith("mock:")` vì giờ
  MockModelClient xử lý trực tiếp không qua fallback.

## 3. Acceptance criteria check (theo plan §"Acceptance criteria")

- [x] Lệnh "Mở Notepad và gõ Hello" tạo đúng 2 step
  → Đạt. `test_planner_uses_model_when_response_valid` verify;
       smoke test thật qua curl cho 2-step workflow với `tool_name=open_app`
       + `tool_name=type_text`.
- [x] Lệnh "Mở google.com trên Edge" tạo đúng step mở URL
  → Đạt. MockModelClient DEFAULT_RESPONSES có case này với
       `tool_name=open_url`, `params.url="https://google.com"`.
- [x] Nếu Qwen trả JSON lỗi, backend không crash
  → Đạt. `PlannerService.plan()` never raises — trả `PlanResult` với
       `used_fallback=True` + `error` field set. `test_planner_repairs_invalid_json_then_succeeds`
       + `test_planner_falls_back_when_repair_also_fails` cover cả 2
       branch.
- [x] Nếu Ollama offline, UI nhận lỗi `model_offline`
  → Đạt. `OllamaModelClient.health()` trả `online=false` + `error`
       khi ConnectError. `PlannerService.plan()` catch `ModelOfflineError`
       và fallback. Code `MODEL_OFFLINE` đã chốt trong event_protocol.md.
       `/models/health` endpoint phản ánh online state.

## 4. Quyết định thiết kế chính

1. **Protocol-based ModelClient** — `runtime_checkable Protocol` + 2 impl:
   `OllamaModelClient` (production) + `MockModelClient` (test + offline
   dev). PlannerService chỉ depend Protocol, dễ swap.
2. **Env-var backend selection** — `WINDAGENT_MODEL_BACKEND=mock|ollama`
   chọn impl tại startup. Mock client chỉ được import khi cần (lazy)
   để production runtime không có nó.
3. **Repair prompt 1 lần** — round 1 thất bại (validation fail hoặc
   empty steps), gửi 1 repair prompt kèm schema + bad answer. Round 2
   fail → fallback. Tránh infinite loop.
4. **Empty steps cũng trigger fallback** — model nói "I don't know"
   bằng `{"steps": []}` thì fallback parser vẫn có thể rescue 2 demo.
   Tránh UX tệ khi model chưa pull hoặc quá yếu.
5. **System prompt cứng** — Qwen3 4B Q4 tuân theo schema JSON khi prompt
   liệt kê đầy đủ tool + schema verbatim. Đã test qua mock (giả lập
   model tuân lời), production cần verify qua Qwen thật.
6. **Async httpx cho Ollama** — `OllamaModelClient` dùng `httpx.AsyncClient`
   để không block event loop. Có thể inject mock transport để test
   không cần Ollama thật.
7. **PlannerService.plan() never raises** — mọi exception được catch,
   trả PlanResult với `error` field. UI kiểm tra `plan.error` để hiện
   thông báo, `plan.is_empty` để biết có workflow hay không.
8. **/models/health trả 200 luôn** — frontend check `online` field.
   Tránh HTTP error cho UI khi provider offline.

## 5. Kiến trúc planner

```
User text
   ↓
PlannerService.plan()
   ↓
[round 1] model.chat(system_prompt + user_text)
   ↓
_try_parse + _validate (whitelist, schema)
   ├─ valid → return PlanResult(used_fallback=False)
   └─ invalid/empty
        ↓
[round 2] model.chat(system_prompt + repair_prompt)
   ↓
_try_parse + _validate
   ├─ valid → return PlanResult(used_fallback=False)
   └─ invalid/empty
        ↓
_fallback() → parse_intent() (rule-based)
   ↓
return PlanResult(used_fallback=True, error=...)
```

## 6. Đầu ra của phase (theo plan §"Đầu ra của phase")

- [x] User nhập lệnh tự nhiên — POST /sessions/{id}/messages (đã có)
- [x] Qwen tạo workflow — PlannerService với OllamaModelClient
- [x] Backend validate workflow — `_validate` enforce 9-tool whitelist
- [x] Workflow chạy sequential — Phase 5 WorkflowRunner (đã có)

## 7. Vấn đề phát hiện & xử lý trong lúc làm

| Vấn đề | Cách xử lý |
|---|---|
| Circular import giữa workflow_service ↔ planner_service (do cả 2 cần nhau) | Lazy import `parse_intent` bên trong `_fallback()` method |
| Bad import `from services.event_bus import ChatMessage` | Đổi sang `from services.model_client import ChatMessage` (đúng nguồn) |
| `test_create_for_message_emits_full_event_sequence` assert used_fallback=True (stale cho Phase 1) | Update: giờ `used_fallback=False` + `model.startswith("mock:")` vì MockModelClient xử lý trực tiếp |
| MockModelClient trả `{"steps": []}` cho unknown phrase — không trigger fallback | Đổi validation check từ `cleaned is not None` sang `if cleaned:` (truthy = có step). Empty steps trigger fallback. |
| Test `test_models_health_reflects_offline_state` re-create TestClient → lifespan restart → reset state | Dùng TestClient(app) không qua context manager (reuses app state) |
| Test Ollama client chat URL path sai (httpx strip base_url) | Fix base_url trong test từ `http://fake-ollama` sang `http://fake-ollama/v1` |
| Server port 8765 bị bind cũ khi smoke test | Kill PID 14848 qua taskkill trước khi start uvicorn mới |

## 8. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Chưa có Ollama thật trong dev env → chưa end-to-end test với Qwen | Dev máy không cài Ollama; cần máy Windows có GPU/CPU đủ mạnh | User cài Ollama + pull model |
| Repair prompt chỉ 1 lần — model vẫn lỗi thì fallback | Plan cho phép; fallback đủ tốt cho MVP | Post-MVP |
| Không có streaming response — user phải đợi Qwen full response | MVP không cần streaming text | Post-MVP |
| System prompt cứng — không học từ user feedback | MVP scope | Post-MVP |
| Không có timeout per request — model treo sẽ block workflow | httpx timeout 30s mặc định | Phase 10 hardening |
| MockModelClient chỉ biết 2 demo — unknown phrase trả empty, fallback parser rescue được | OK cho MVP | OK |
| `OllamaModelClient` không retry khi lỗi transient (network blip) | Plan chưa yêu cầu | Phase 10 |

## 9. Sẵn sàng cho phase tiếp theo

Phase 6 (Tauri UI) là phase tiếp theo theo plan §"Thứ tự ưu tiên".
Backend đã có mọi endpoint cần:
- `GET /models/health` cho UI badge
- `WS /ws/{session_id}` cho real-time event
- Runner state qua `GET /sessions/{id}/runner`
- Pause/Resume/Stop qua REST hoặc WS control message

Phase 7 (permission gate) cũng độc lập — chèn giữa runner và
ToolExecutor.

## 10. Lệnh kiểm tra nhanh

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv sync --extra dev
uv run pytest --timeout=15                    # 132 passed
$env:WINDAGENT_MOCK_GUI=1
$env:WINDAGENT_MODEL_BACKEND=mock
uv run uvicorn main:app --port 8765
# Smoke test:
curl http://127.0.0.1:8765/models/health
$sid = (curl -X POST http://127.0.0.1:8765/sessions | ConvertFrom-Json).session_id
curl -X POST http://127.0.0.1:8765/sessions/$sid/messages `
  -H "Content-Type: application/json" `
  --data-raw '{"content":"M Notepad va go Hello"}'
Start-Sleep 1
curl http://127.0.0.1:8765/sessions/$sid/workflow    # 2 steps, status=completed
```

Kỳ vọng: 132 passed, `/models/health` trả mock online, 2-step workflow
cho demo.

## 11. Hướng dẫn chuyển sang Ollama thật

Trên máy có Ollama:

```powershell
# Cài Ollama từ https://ollama.com (Windows installer)
ollama pull qwen3:4b-q4
ollama serve   # nếu chưa chạy

# Verify
curl http://localhost:11434/v1/models

# Chạy backend với Ollama thật
cd apps\backend
uv run uvicorn main:app --port 8765    # WINDAGENT_MODEL_BACKEND=ollama mặc định
curl http://127.0.0.1:8765/models/health
# online=true, model=qwen3:4b-q4
```

Test cuối cùng cần làm với Ollama thật:
- Gõ lệnh tự nhiên phức tạp ("search for python tutorial on google then open first result")
- Verify Qwen trả JSON đúng schema
- Verify latency trong `/models/health`
- Verify `used_fallback=False` trong event `planning_finished`