# Agent-S3 Integration

WindAgent có thể chạy [Agent-S3](https://github.com/simular-ai/Agent-S)
(Simular AI's screen-grounded computer-use agent) như một optional
planner. Đây là **additive**, không thay thế mock planner / Ollama
Qwen3 hiện có.

## Mục tiêu tích hợp

- Đa-dạng hoá planner: thêm screen-grounded LLM planner để xử lý tác vụ
  GUI phức tạp mà rule-based mock không cover hết.
- Tận dụng official SDK của upstream — **không vendor source**.
- Giữ nguyên safety guarantee: mọi GUI action phải qua WindAgent tool
  whitelist + permission gate, không thực thi raw action code.

## Trạng thái hiện tại (Phase 11 closeout)

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| Agent-S3 config loader | ✓ | `services/agent_s3_config.py` đọc env, validate. |
| Adapter (package + external mode) | ✓ | `services/agent_s3_adapter.py` lazy-import official SDK. |
| Action translator (safety boundary) | ✓ | `services/agent_s3_action_translator.py` reject exec/eval/subprocess/os.system/... |
| Health endpoint `/agent-s3/health` | ✓ | `routers/agent_s3.py` — secret-scrubbed (SEC-002 fix). |
| Setup script `scripts/setup_agent_s3.ps1` | ✓ | Cài `gui-agents==0.3.2` (package) hoặc clone external. |
| 84 dedicated tests | ✓ | translator 31 + adapter 16 + config 27 + health 10. |
| **Wired into WorkflowRunner** | **✗ — armed but not loaded** | `INT-001` finding — Phase 12 follow-up. |
| Production run with Agent-S3 → screen | ✗ | `agent_s3_step` tool chưa tồn tại trong registry. |

**Quan trọng:** Agent-S3 hiện tại là **safe optional scaffold**. Code,
tests, config và health endpoint đều ready, nhưng WorkflowRunner chưa
gọi `adapter.propose()` — Agent-S3 không thực sự chạy workflow nào ở
runtime. Mọi workflow hiện tại vẫn dùng mock / Ollama planner.

## Optional / Disabled mặc định

Agent-S3 mặc định **disabled** (`WINDAGENT_AGENT_S3_ENABLED=0`). Backend
vẫn load config (cheap env reads) và expose health endpoint, nhưng
không construct adapter và không pull bất kỳ dependency nào vào import
graph. Operator phải opt-in bằng cách set env vars.

## Hai install mode

### 1. package mode (khuyến nghị, mặc định)

Cài PyPI package `gui-agents==0.3.2` vào backend venv qua uv.

```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\setup_agent_s3.ps1 -Mode package
```

Verify import thành công:

```powershell
.apps\backend\.venv\Scripts\python.exe -c "import gui_agents; print('OK', gui_agents.__version__)"
```

### 2. external mode (clone upstream repo)

Clone [https://github.com/simular-ai/Agent-S](https://github.com/simular-ai/Agent-S)
vào `external/Agent-S/` và prepend vào `sys.path` lúc runtime.

```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\setup_agent_s3.ps1 -Mode external
```

Hoặc dùng git submodule (idempotent):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_agent_s3.ps1 -Mode external -UseSubmodule
```

Backend sẽ tự detect presence của `external/Agent-S/gui_agents/` (post-v0.2
layout) hoặc `external/Agent-S/agent_s/` (older layout).

## Environment variables

| Biến | Bắt buộc khi enable | Mặc định | Mục đích |
|---|---|---|---|
| `WINDAGENT_AGENT_S3_ENABLED` | — | `0` | Bật/tắt toàn bộ integration. |
| `WINDAGENT_AGENT_S3_SOURCE` | — | `package` | `package` (PyPI) hoặc `external` (clone). |
| `WINDAGENT_AGENT_S3_EXTERNAL_PATH` | khi source=external | `external/Agent-S` | Đường dẫn tới checkout. |
| `WINDAGENT_AGENT_S3_PROVIDER` | ✓ | `openai` | Worker LLM provider key cho Agent-S3 SDK. |
| `WINDAGENT_AGENT_S3_MODEL` | ✓ | `gpt-5-2025-08-07` | Worker LLM model id. |
| `WINDAGENT_AGENT_S3_MODEL_URL` | tùy provider | `""` | Base URL cho worker (trống = provider default). |
| `WINDAGENT_AGENT_S3_MODEL_API_KEY` | tùy provider | `""` | Worker LLM API key — **không bao giờ log/return**. |
| `WINDAGENT_AGENT_S3_GROUND_PROVIDER` | ✓ | `""` | Grounding LLM provider key. |
| `WINDAGENT_AGENT_S3_GROUND_MODEL` | ✓ | `""` | Grounding LLM model id. |
| `WINDAGENT_AGENT_S3_GROUND_URL` | tùy provider | `""` | Base URL cho grounding LLM. |
| `WINDAGENT_AGENT_S3_GROUND_API_KEY` | tùy provider | `""` | Grounding LLM API key — **không bao giờ log/return**. |
| `WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV` | — | `0` | **Bị force về `0` bởi WindAgent safety policy**, kể cả khi user set 1. |

## Cách bật / tắt

```powershell
# Bật (package mode, OpenAI worker + HuggingFace UI-TARS ground)
$env:WINDAGENT_AGENT_S3_ENABLED         = '1'
$env:WINDAGENT_AGENT_S3_SOURCE          = 'package'
$env:WINDAGENT_AGENT_S3_PROVIDER        = 'openai'
$env:WINDAGENT_AGENT_S3_MODEL           = 'gpt-5-2025-08-07'
$env:WINDAGENT_AGENT_S3_MODEL_API_KEY   = 'sk-...'
$env:WINDAGENT_AGENT_S3_GROUND_PROVIDER = 'huggingface'
$env:WINDAGENT_AGENT_S3_GROUND_MODEL    = 'ui-tars-1.5-7b'
$env:WINDAGENT_AGENT_S3_GROUND_API_KEY  = 'hf_...'

# Tắt
$env:WINDAGENT_AGENT_S3_ENABLED = '0'
```

Sau đó chạy backend như thường. Healthcheck sẽ tự báo mode / config_missing
/ last_error để debug.

## Cách chạy healthcheck

```powershell
# Sau khi backend đang chạy
curl http://127.0.0.1:8765/agent-s3/health | python -m json.tool
```

Response shape (Phase 11, sau SEC-002 fix):

```json
{
  "mode": "package",
  "enabled": true,
  "source": "package",
  "package_available": true,
  "external_repo_available": false,
  "config_missing": [],
  "last_error": null,
  "config": {
    "external_path": "D:\\antigaravity_code\\WindAgent\\external\\Agent-S",
    "provider": "openai",
    "model": "gpt-5-2025-08-07",
    "ground_provider": "huggingface",
    "ground_model": "ui-tars-1.5-7b",
    "enable_local_env": false,
    "notes": [],
    "adapter_initialised": true,
    "last_actions": []
  }
}
```

Lưu ý: response **không bao giờ** chứa `model_api_key`, `ground_api_key`,
`bearer`, `token`, `password`, hay bất kỳ secret nào. Nếu env đã set
nhưng field tương ứng không xuất hiện trong response, đó là scrub layer
hoạt động đúng. Xem `services/agent_s3_health.py::scrub_secrets()`.

## Giới hạn hiện tại

- **Agent-S3 adapter instantiated** ✓ (khi `is_available()` pass) — adapter
  được build khi lifespan chạy nếu config hợp lệ. `adapter_initialised=true`
  trong health response xác nhận.
- **Safe translator exists** ✓ — `agent_s3_action_translator.translate()`
  nhận list raw action strings, trả về `TranslationResult(accepted, rejected)`.
  11/11 malicious input patterns bị reject.
- **`agent_s3_step` chưa wire vào `WorkflowRunner`** ✗ — đây là Phase 12
  follow-up (finding `INT-001`). Translator có sẵn, nhưng WorkflowRunner
  không gọi `adapter.propose()` ở step boundary. Do đó Agent-S3 không
  thực sự drive workflow nào ở runtime.
- **`OSWorldACI(env=None)` dormant** — adapter gọi `OSWorldACI(env=None)`
  khi propose() được trigger. Vì propose() chưa wired, code path này
  chưa chạy lần nào trong MVP. Trước khi wire vào runner, cần test
  runtime behaviour của `OSWorldACI(env=None)`.

## Safety guarantees

Bốn safety guarantees mà WindAgent giữ nguyên khi Agent-S3 được wire
vào runner (Phase 12+):

1. **Không raw exec/eval.** `agent_s3_action_translator.translate()`
   nhận raw action strings, parse bằng regex whitelist + AST shape check,
   reject mọi pattern không match. Translator **không bao giờ** gọi
   `exec()` / `eval()` / `compile()` lên raw strings — `ast.parse(line,
   mode="exec")` chỉ inspect shape, result bị discard.
2. **Action phải qua translator.** Adapter chỉ trả raw strings + info
   dict; workflow runner phải gọi `translate()` trước khi map sang tool.
3. **Action phải map sang tool whitelist.** Recognised patterns:
   - `pyautogui.click(x, y[, button])` → `click_xy`
   - `pyautogui.{leftClick,rightClick,middleClick,doubleClick,tripleClick}(x, y)` → `click_xy`
   - `pyautogui.{typewrite,write}("text")` → `type_text`
   - `pyautogui.hotkey(...)` → `hotkey`
   - `pyautogui.press("key")` → `press_key`
   - `pyautogui.scroll(n)` / `hscroll(n)` → `scroll`
   - `time.sleep(n)` (0 < n ≤ 60) → `wait`
   - `pyautogui.screenshot()` → `screenshot`
   Reject patterns: `import` / `from x import y` / `open(` / `subprocess`
   / `os.system` / `os.popen` / `exec(` / `eval(` / `__import__(` /
   `requests.` / `urllib` / `socket` / multi-line statements.
4. **Action phải qua permission gate/audit.** Mọi `TranslatedAction` rơi
   vào `ToolExecutor.execute()`, nơi `PermissionService.request_permission()`
   chạy trước khi thực thi. `permission_request` / `permission_granted`
   / `permission_denied` events được mirror vào audit log (DB + JSONL).

Ngoài ra: `WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV` luôn bị force về `0` ở
config layer bất kể env — Agent-S3 không được phép exec arbitrary Python
+ bash qua local coding sandbox.

## Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `mode=disabled` | `WINDAGENT_AGENT_S3_ENABLED` không set / =0 | Set =1 trước khi start backend. |
| `mode=misconfigured`, `config_missing` liệt kê env vars | Một số required env vars trống (provider / model / ground_*). | Set đầy đủ theo bảng env vars. |
| `package_available=false` | `gui-agents` chưa cài trong backend venv. | Chạy `scripts\setup_agent_s3.ps1 -Mode package`. |
| `external_repo_available=false` | `external/Agent-S/` không tồn tại hoặc không có `gui_agents/`. | Chạy `scripts\setup_agent_s3.ps1 -Mode external`. |
| `last_error="build agent failed: ..."` | Upstream SDK raise lúc construct (network, import error). | Check log `artifacts/logs/backend.log` để biết stacktrace. |
| `last_error="predict failed: ..."` | Worker LLM hoặc grounding LLM endpoint offline / auth fail. | Verify `WINDAGENT_AGENT_S3_MODEL_URL` và `*_API_KEY` reachable. |
| Backend vẫn chạy nhưng Agent-S3 không xuất hiện trong workflow | **Bình thường** — Phase 11 chỉ arm scaffold. WorkflowRunner chưa gọi `propose()` (INT-001). | Đây là Phase 12 follow-up. |

## Phase 12 follow-up

Sau Phase 11 closeout, các bước sau sẽ được thực hiện ở Phase 12:

- Add `agent_s3_step` tool vào `tool_registry.py` (`risk=high`,
  `requires_confirmation=True`).
- Wire WorkflowRunner để gọi `adapter.propose()` tại step boundary khi
  per-session flag bật.
- Pipe `TranslationResult.accepted` qua `ToolExecutor` để mỗi tool call
  còn chạy qua permission gate.
- Per-session flag `use_agent_s3` ở `POST /sessions/{sid}/messages`.
- Audit event `agent_s3_action_rejected` mirror vào JSONL log.
- Integration test: full mock propose → translate → execute path.

Xem `artifacts/agent_s3_integration/phase11_closeout_report.md` để biết
chi tiết Phase 11 outcomes và verification evidence.