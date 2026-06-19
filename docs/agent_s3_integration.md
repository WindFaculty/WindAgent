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

## Trạng thái hiện tại (Phase 12)

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| Agent-S3 config loader | ✓ | `services/agent_s3_config.py` đọc env, validate. |
| Adapter (package + external mode) | ✓ | `services/agent_s3_adapter.py` lazy-import official SDK. |
| Action translator (safety boundary) | ✓ | `services/agent_s3_action_translator.py` reject exec/eval/subprocess/os.system/... |
| Health endpoint `/agent-s3/health` | ✓ | `routers/agent_s3.py` — secret-scrubbed (SEC-002 fix). |
| Setup script `scripts/setup_agent_s3.ps1` | ✓ | Cài `gui-agents==0.3.2` (package) hoặc clone external. |
| 84 dedicated tests | ✓ | translator 31 + adapter 16 + config 27 + health 10. |
| **Wired into WorkflowRunner** | **✓ Phase 12** | `agent_s3_step` tool mới + `services/agent_s3_step_executor.py` orchestrator. |
| Production run with Agent-S3 → screen | **✓ Phase 12** | `agent_s3_step` chạy end-to-end qua permission gate + audit. |

Phase 12 đã wire `agent_s3_step` vào WorkflowRunner thật. Tool này có
thể là một step trong workflow, planner có thể emit nó, WorkflowRunner
sẽ gọi Agent-S3 propose → translate → execute mapped action qua tool
whitelist hiện tại + permission gate + audit. Phase 12 KHÔNG bật
multi-step Agent-S3 loop vô hạn — mỗi `agent_s3_step` chỉ chạy 1 action.

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
- **`agent_s3_step` wired vào `WorkflowRunner`** ✓ (Phase 12) — tool mới
  trong `tool_registry.py`, dispatch qua `ToolExecutor._execute_agent_s3_step`,
  orchestrator `services/agent_s3_step_executor.py` xử lý
  propose → translate → mapped tool → audit. Mỗi `agent_s3_step` chỉ
  chạy đúng 1 action.
- **Permission gate on `agent_s3_step`** ✓ — `requires_confirmation=True`
  nên WorkflowRunner chờ user approve TRƯỚC khi gọi adapter. Nếu
  deny/timeout → step cancelled, không execute mapped action.
- **Multi-step autonomous Agent-S3 loop** ✗ — chưa bật. Mỗi
  `agent_s3_step` chỉ chạy 1 action. Nếu cần multi-step, planner phải
  emit nhiều `agent_s3_step` steps trong workflow. Bounded loop là
  Phase 13 follow-up.
- **`OSWorldACI(env=None)` dormant** — adapter gọi `OSWorldACI(env=None)`
  khi propose() được trigger. Test runtime behaviour đã pin qua mock
  adapter trong test suite. Production smoke với real `gui-agents`
  SDK vẫn cần manual test trên Windows session có Accessibility.

## `agent_s3_step` tool (Phase 12)

Tool mới trong tool whitelist (`risk=high`, `requires_confirmation=True`).

### Schema

```json
{
  "instruction": "string, required, 1..2000 chars",
  "screenshot": "boolean, optional, default true",
  "dry_run": "boolean, optional, default false",
  "max_retries": "integer, optional, 0..2, default 0",
  "require_permission": "boolean, optional, default true",
  "timeout_ms": "integer, optional, 1..120000, default 30000"
}
```

### Execution flow

```
WorkflowRunner.step (tool_name=agent_s3_step)
  -> [runner] permission gate (if requires_confirmation=True)
  -> ToolExecutor._execute_agent_s3_step
    -> AgentS3StepExecutor.execute
      1. Validate Agent-S3 enabled + adapter available
      2. Capture screenshot via GuiAdapter.screenshot (if screenshot=true)
      3. await adapter.propose(instruction, observation)
      4. translator.translate(raw_actions)
      5. Re-validate mapped tool against AGENT_S3_MAPPED_TOOL_ALLOWLIST
         (= {click_xy, type_text, hotkey, press_key, scroll, wait, screenshot})
      6. validate_params(mapped.tool_name, mapped.params)  (Pydantic)
      7. emit agent_s3_action_proposed event (safety_status=accepted)
      8. If dry_run: return translated tool + params only (no GUI)
      9. Else: await asyncio.to_thread(self._run_mapped_tool, ...) 
         -> ToolExecutor._run dispatch to actual gui adapter
    -> ToolExecutor._emit_and_persist (tool_call_finished + tool_calls row)
```

### Error codes

| Code | Khi nào |
|---|---|
| `AGENT_S3_DISABLED` | `WINDAGENT_AGENT_S3_ENABLED=0` hoặc orchestrator chưa wire |
| `AGENT_S3_ADAPTER_NOT_READY` | adapter = None |
| `AGENT_S3_UNAVAILABLE` | adapter.is_available() = False (no config, no package, ...) |
| `AGENT_S3_PROPOSE_FAILED` | adapter.propose raised; last_error set |
| `AGENT_S3_PARSE_FAILED` | translator raised |
| `AGENT_S3_UNSAFE_ACTION` | raw action matched deny pattern (exec / os.system / ...) |
| `AGENT_S3_UNSUPPORTED_ACTION` | translator returned no accepted action |
| `MAPPED_TOOL_NOT_WHITELISTED` | defence-in-depth (should never happen) |
| `MAPPED_TOOL_INVALID_PARAMS` | translated params failed Pydantic |
| `MAPPED_TOOL_EXECUTION_FAILED` | inner mapped tool raised |
| `AGENT_S3_ORCHESTRATOR_RAISED` | orchestrator itself raised (defensive) |

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

## Phase 13 follow-up

Sau Phase 12, các bước sau sẽ được thực hiện ở Phase 13:

- Bounded multi-step Agent-S3 loop (e.g. `max_propose_per_step` ở
  workflow level, hoặc `agent_s3_session` tool cho phép nhiều action
  liên tiếp với hard cap).
- Frontend timeline event cho `agent_s3_action_proposed` (hiện event
  đã wire qua EventBus; UI chỉ cần subscribe + render).
- Real-GUI smoke test với PyAutoGUI + Windows Accessibility permission
  (SEC-001 closure).
- Better recovery: nếu mapped tool fail, cho phép Agent-S3 propose
  action khác (giới hạn retry theo `max_retries` param).
- Tích hợp `click_target` + `agent_s3_step`: dùng Agent-S3 để resolve
  target + locate element trước khi click.
- Tauri bundle verification (QA-001, cần Rust toolchain).

Xem `artifacts/agent_s3_integration/phase11_closeout_report.md` và
`artifacts/agent_s3_integration/phase12_workflow_wire_report.md` để
biết chi tiết Phase 11 + Phase 12 outcomes và verification evidence.