# Error handling audit — WindAgent MVP (Phase 10.2)

This document inventories every failure mode the user can plausibly
hit during MVP, where it is caught, and what the user sees. It exists
so future contributors know what's already covered (don't re-implement)
and where the gaps are.

Canonical event shape: `docs/event_protocol.md`.
Canonical REST shape: `docs/api_contract.md`.

## 1. Network / connectivity

| Failure | Where caught | Surface to user |
|---|---|---|
| Backend not running when frontend loads | `apps/desktop/src/api/client.ts` `jsonFetch` throws on `fetch` rejection; `App.tsx` shows `"poll failed: ..."` in StatusBar | Red banner in StatusBar; chat input remains usable |
| Vite proxy target offline (`/api` 502/504) | Same `jsonFetch` path; status text is `API 502: ...` | Red banner |
| Backend /health returns 5xx | Healthcheck script marks `[FAIL]`; not surfaced in-app (no auto-retry) | Operator sees it in `scripts/healthcheck.ps1` output |
| WebSocket disconnect | `apps/desktop/src/api/client.ts` `connectWs` reconnects with exponential backoff (1s → 15s max) | Silent reconnect; no user-visible error unless reconnect exhausts indefinitely |
| WebSocket reconnect hits unknown session | Server `apps/backend/routers/websocket.py` closes with `code=4404` | Client logs to console; user starts a new session |

## 2. Model (planner)

| Failure | Where caught | Surface to user |
|---|---|---|
| Ollama offline | `apps/backend/services/model_client.py` raises `ModelOfflineError` | `PlannerService.plan()` falls back to rule-based parser; emits `planning_finished` with `used_fallback=True`. UI shows workflow (if rule matches) or "empty workflow" if rule does not match. |
| Ollama returns HTTP 4xx/5xx | `ModelResponseError` | Same fallback path |
| Ollama returns malformed JSON | `PlannerService._try_parse` strips fences then `json.loads`; falls through to repair prompt |
| Repair prompt also bad | Falls through to fallback parser; never raises |
| Empty workflow produced | `workflow_created` event with `steps: []` | UI shows "Workflow rỗng — model không match được intent" |
| `ModelClient.chat()` times out (>30s) | `httpx.ReadTimeout` -> `ModelOfflineError` | Fallback path as above |
| Model present but wrong model id (`qwen3:4b-q4` not pulled) | `/models/health` returns `online: true, error: "model not found"` | StatusBar shows red banner with model not found message (via `fetchModelsHealth` -> `setModelsOnline`) |

## 3. Tool execution

| Failure | Where caught | Surface to user |
|---|---|---|
| Unknown tool name (model hallucinates) | `apps/backend/services/tool_registry.py` `get_tool()` raises `KeyError` | `ToolExecutor.execute()` catches, emits `tool_call_finished` with `status: failed, error.code: INVALID_TOOL`; runner marks step `failed` |
| Invalid params (e.g. `open_app` app not in allowlist) | `validate_params()` raises `ValidationError` | Same path; error message includes Pydantic field detail |
| `open_app` for unknown app alias | `PyAutoGuiAdapter.open_app` raises `ValueError` listing supported apps | step `failed`; error message lists `{notepad, calc, mspaint, edge, explorer}` |
| PyAutoGUI import fails (no display, no pywin32, etc.) | `PyAutoGuiAdapter._ensure_pyautogui` raises `RuntimeError("pyautogui is not available...")` | step `failed`; user told to set `WINDAGENT_MOCK_GUI=1` for dev |
| PyAutoGUI permission denied (Windows UAC / interactive desktop) | Adapter call raises `pyautogui.FailSafeException` or similar | step `failed`; error message surfaced in `tool_call_finished.data.error.message` |
| `click_target` in mock grounding mode | `ToolExecutor._execute_click_target` returns `VISION_STUB_MODE` error | step `failed` with clear message "GUI grounding service is not configured. Use click_xy with manual coordinates for MVP." |
| Subprocess for `open_app`/`open_url` not found | `subprocess.Popen` raises `FileNotFoundError` | step `failed`; `error.code: TOOL_FAILED`, message includes the underlying exception |
| Screenshot path not writable | `out_dir.mkdir` raises `PermissionError` / `OSError` | step `failed`; `error.code: TOOL_FAILED` |

## 4. Workflow runner / control

| Failure | Where caught | Surface to user |
|---|---|---|
| User clicks Stop on a non-running session | `WorkflowRunner.stop()` returns `False` | UI silently ignores (button disabled when `task_done`) |
| User clicks Pause on a finished session | `WorkflowRunner.pause()` returns `False` | Button disabled in UI; no error |
| User clicks Retry with no failed step | `WorkflowRunner.retry()` returns `False` | Button disabled in UI |
| `permission_denied` from user | `WorkflowRunner._gate_permission` returns `"user_denied"` | Step marked `cancelled`; workflow continues with next step |
| Permission request timeout | `PermissionService.request_permission` waits `request_timeout_s` (default 30s) then resolves `granted=False` | Same as user denied |
| Tool raised mid-runner uncaught exception | `WorkflowRunner._run` `except Exception` block emits `session_finished` with `final_status: "failed"` | Status bar shows error; workflow marked failed |
| WebSocket control message with malformed JSON | `routers/websocket.py` `_read_control_messages` catches `JSONDecodeError`, continues | Silent |
| WebSocket control message with unknown action | Skipped | Silent |

## 5. Database / persistence

| Failure | Where caught | Surface to user |
|---|---|---|
| SQLite file not writable | `apps/backend/db/database.py` raises on init | Backend exits with non-zero code; healthcheck shows `[FAIL]` |
| `execution_events` insert fails (e.g. DB locked) | `apps/backend/services/event_hooks.py` `except Exception` | Logged at ERROR; live WebSocket still receives event; user sees no error |
| Session lookup missing (stale UUID in URL) | `routers/sessions.py` raises `HTTPException(404)` | Frontend shows `API 404: session not found` in StatusBar |
| WebSocket connect to unknown session | `routers/websocket.py` closes with `code=4404` | Client reconnects; if user expects to see live data, no events arrive (start a new session) |

## 6. Frontend

| Failure | Where caught | Surface to user |
|---|---|---|
| Any REST call rejects | `App.tsx` try/catch wraps every action; sets `error` state | Red banner in `<StatusBar error={...} />` |
| WebSocket onmessage with non-JSON frame | `apps/desktop/src/api/client.ts` `connectWs` `try/catch` around `JSON.parse` | Silent (treat as keepalive) |
| User sends empty message | `ChatInput` button disabled when input empty | UI prevents submit |
| User sends before creating a session | `ChatPanel.onSend` triggers `newSession` first | First click creates session; subsequent clicks send messages |

## 7. Operating without Ollama (MVP default)

`scripts/dev_backend.ps1` defaults to `-Mock:$true`, which sets
`WINDAGENT_MODEL_BACKEND=mock` and `WINDAGENT_MOCK_GUI=1`. In this mode
the planner returns canned responses for the two demo phrases, and the
GUI adapter records calls without touching the screen. This is the
recommended path for first-time setup so the demo runs end-to-end
without any model install.

If a user wants real model behaviour they:
1. Install Ollama from <https://ollama.com/download>.
2. `ollama pull qwen3:4b-q4`.
3. Start backend with `scripts/dev_backend.ps1 -Mock:$false`.

## 8. Known gaps

These are explicitly NOT covered in MVP — see `docs/mvp_release_note.md`
§"Known issues":

- No automatic backend reconnect on the frontend; user must refresh.
- No disk-space check for `artifacts/runs`; long sessions fill disk.
- Tool timeouts are 30s (httpx default) but no upper bound per step;
  a hung subprocess blocks the runner forever (Stop still works).
- Planner repair prompt is sent unconditionally; on slow models this
  doubles worst-case latency on bad output.

## 9. Test coverage

Every row above has a corresponding test in `apps/backend/tests/`:

- Network: `test_websocket.py` covers reconnect + close-on-unknown.
- Model: `test_model_client.py`, `test_planner_service.py`,
  `test_models_api.py`.
- Tool: `test_tool_executor.py`, `test_tool_registry.py`,
  `test_tools_api.py`.
- Runner: `test_workflow_runner.py`, `test_session_service.py`,
  `test_api.py`.
- DB: `test_db_persistence.py`.
- Frontend: `apps/desktop/src/components/*.test.tsx`,
  `apps/desktop/src/state/sessionStore.test.ts`.

Total backend tests: 184 (`uv run pytest`).
Total frontend tests: 19 (`npm run test`).
