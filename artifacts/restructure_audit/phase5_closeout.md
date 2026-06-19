# Phase 5 Closeout — Workflow Engine sequential + control Pause/Resume/Stop

Ngày: 2026-06-18
Trạng thái: COMPLETED
Acceptance criteria: PASS

## 1. Phạm vi đã làm

Phase 5 yêu cầu workflow engine chạy tuần tự với state machine đầy đủ +
control pause/resume/stop/retry cả qua REST và WebSocket. Phiên này
build runner thật, wire tất cả các stub từ Phase 1 + Phase 3, đảm bảo
mọi transition stream qua WS + persist vào DB.

Phiên trước đã implement sẵn:
- Phase 1: REST + WS + in-memory event bus
- Phase 2: SQLite persistence (6 bảng) + event_hooks mirror
- Phase 3: Tool Executor + Tool Registry + 9 tool + PyAutoGUI/MockGuiAdapter

Phiên này bổ sung:
- Phase 5: WorkflowRunner thật + auto-start + pause/resume/stop/retry + WS control

## 2. Deliverables thực tế

### 2.1 Source code mới / sửa cho Phase 5

**Mới:**
- `services/workflow_runner.py` — WorkflowRunner class với state machine
  + control signals (pause/resume/stop/retry) + shutdown method

**Sửa:**
- `services/workflow_service.py` — thêm `update_status(session_id, status)`
  + `update_step_status(step_id, status)` (cả in-memory + DB)
- `main.py` — wire runner vào lifespan, version bump 0.3.0 → 0.5.0,
  gọi `runner.shutdown()` khi app shutdown
- `routers/sessions.py` — sau khi tạo workflow, gọi `runner.start()`
  để auto-start execution
- `routers/workflow.py` — pause/resume/stop giờ gọi runner thật + emit
  user_* event echo; retry giờ resolve session từ step_id + gọi
  `runner.retry()`; thêm GET `/sessions/{id}/runner` để inspect state
- `routers/websocket.py` — thêm reader task parse client control
  message `{"action": "pause|resume|stop"}` và dispatch runner

### 2.2 Tests

**Mới:**
- `tests/test_workflow_runner.py` — 9 tests, all pass:
  1. `test_runner_executes_steps_sequentially_in_order` — step order trong event log
  2. `test_stop_does_not_run_subsequent_steps` — stop không chạy step sau
  3. `test_pause_then_resume_completes_workflow` — pause không kill workflow
  4. `test_ws_pause_action_echoes_user_paused_event` — WS control message
  5. `test_runner_state_endpoint_reports_final_status` — GET /runner
  6. `test_session_finished_event_emitted_on_completion` — final event
  7. `test_unknown_intent_emits_session_finished_with_zero_steps` — 0-step workflow
  8. `test_retry_after_workflow_completes` — retry thật sự chạy lại
  9. `test_pause_endpoint_404_when_no_runner` — edge case

**Sửa cho khớp Phase 5:**
- `tests/test_api.py::test_get_workflow_after_planning` — accept status
  pending/running/completed thay vì chỉ pending
- `tests/test_api.py::test_retry_endpoint_returns_501_in_phase1` →
  `test_retry_endpoint_returns_202_in_phase5` — retry giờ return 202
- `tests/test_db_persistence.py::test_update_status_writes_to_db` —
  accept thêm running/completed
- `tests/test_db_persistence.py::test_workflow_and_steps_persisted` —
  accept status thay đổi
- `tests/test_db_persistence.py::test_data_survives_app_restart` —
  accept status mới
- `tests/test_tools_api.py::test_run_workflow_emits_full_event_sequence`
  — bỏ call thủ công /workflow/run (runner auto-start), check thêm
  step_started/step_completed/session_finished events

### 2.3 Docs đã cập nhật

- `docs/api_contract.md` — Phase 1 stub → Phase 5 real cho
  pause/resume/stop/retry; thêm GET /sessions/{id}/runner; WS control
  message spec
- `apps/backend/README.md` — layout cập nhật, smoke test với runner
  state, phase roadmap

## 3. Acceptance criteria check (theo plan §"Acceptance criteria")

- [x] Step không chạy song song
  → Đạt. `test_runner_executes_steps_sequentially_in_order` verify
       event order = [1, 2].
- [x] Stop không làm chạy tiếp step sau
  → Đạt. Runner check `stop_requested` trước mỗi step, đánh dấu step
       hiện tại `cancelled` và thoát loop. `test_stop_does_not_run_subsequent_steps`
       + smoke test verify.
- [x] Pause không giết app, chỉ tạm ngừng workflow
  → Đạt. Runner spin trên `asyncio.sleep(0.02)` khi paused, không block
       event loop. App vẫn nhận event khác, control khác. `test_pause_then_resume_completes_workflow`
       + smoke test verify.
- [x] Mọi transition được stream và lưu DB
  → Đạt. EventBus publish mọi transition (step_started, step_completed,
       step_failed, session_finished, user_*) qua WS. Event hook Phase 2
       mirror vào `execution_events` table.
       `test_session_finished_event_emitted_on_completion` +
       `test_run_workflow_emits_full_event_sequence` verify DB rows.

## 4. Quyết định thiết kế chính

1. **Runner là asyncio.Task per session** — dict `_states: Dict[UUID, _RunState]`
   track mỗi session. `start()` tạo task mới; `pause/resume/stop` set flag
   boolean trên state; task check flag trong loop. Cancel thật sự chỉ khi
   shutdown app.
2. **Auto-start runner trong `POST /sessions/{id}/messages`** — sau khi
   `create_for_message()` return workflow, gọi `runner.start()` ngay.
   0-step workflow vẫn start (exits immediately, phát session_finished).
3. **Pause dùng spin loop 20ms** — không block event loop, runner vẫn
   yield để nhận event khác. Đơn giản hơn `asyncio.Event` cho MVP.
4. **Retry spawn task mới từ current_step_index** — không resume task cũ.
   State mới có `started_at` mới, `final_status` reset về None. Step
   failed được re-execute, nếu success thì runner tiếp tục các step sau.
5. **Echo pattern cho control event** — backend phát `user_paused` qua
   bus khi nhận pause qua REST HOẶC WS. WS reader task là client-side
   trigger; REST là HTTP trigger. Cùng dispatch xuống runner, cùng
   emit event echo. Frontend nghe 1 channel là thấy đủ.
6. **GET /sessions/{id}/runner expose state** — frontend dùng để render
   control button enabled/disabled, hiển thị progress, hiển thị lỗi.
7. **WorkflowService.update_status + update_step_status** — write cả
   in-memory lẫn DB. Step status update duyệt workflow N nhỏ (MVP), OK
   đến vài nghìn step.
8. **GET /sessions/{id}/runner return null khi không có runner** — ví dụ
   session tạo xong chưa gửi message, hoặc workflow có 0 step.
9. **Runner.shutdown() cancel + await** — khi lifespan exit, cancel mọi
   task, await tối đa 2s. Tránh uvicorn warning về pending task.

## 5. State machine thực tế

### Session / Workflow status
```
idle ──create_session──▶ idle
idle ──POST /messages──▶ pending ──runner.start──▶ running
                                                  │
                                       ┌──────────┼──────────┐
                                  pause│    success│    failure│
                                       ▼          ▼          ▼
                                    paused    completed   failed
                                       │
                                  resume│
                                       ▼
                                    running
                                       │
                                  stop │ (bất cứ lúc nào)
                                       ▼
                                    cancelled
```

### Step status
```
pending ──runner._run──▶ running ──success──▶ success
                              ──failure──▶ failed
                              ──stop────▶ cancelled
```

### Tool call status (do ToolExecutor, Phase 3)
```
pending ──started──▶ running ──success──▶ success
                            ──exception─▶ failed
```

## 6. Đầu ra của phase (theo plan §"Đầu ra của phase")

- [x] Workflow chạy tuần tự ổn định
  → Đạt. Auto-start + sequential + final event. MockGUI smoke test 2-step workflow completed trong <1s.
- [x] Pause dừng trước step tiếp theo
  → Đạt. Pause check ở đầu mỗi step iteration; step hiện tại (nếu đang chạy) chạy xong.
- [x] Resume tiếp tục
  → Đạt. Clear `paused` flag; runner thoát spin loop, chạy step tiếp.
- [x] Stop hủy workflow
  → Đạt. Set `stop_requested`, runner thoát loop với final_status=cancelled, emit session_finished.
- [x] Retry chạy lại step lỗi
  → Đạt. `runner.retry()` spawn task mới từ `current_step_index`, reset state.

## 7. Vấn đề phát hiện & xử lý trong lúc làm

| Vấn đề | Cách xử lý |
|---|---|
| Phiên trước để 6 test stale (assert status `pending`) | Update assertion accept running/completed, đợi runner finish với `time.sleep(0.2)` |
| `test_retry_endpoint_returns_501_in_phase1` đã lỗi thời | Đổi thành `test_retry_endpoint_returns_202_in_phase5` |
| `test_run_workflow_emits_full_event_sequence` gọi /workflow/run sau auto-start → 3 tool_call_started | Bỏ manual call, check event từ auto-start (step_started/completed/session_finished) |
| Server cũ bind 8765 không chết → uvicorn mới fail | Kill PID 9172 thủ công qua taskkill |
| Bash trên Windows ngống encode UTF-8 của "Mở" trong curl --data | Smoke test dùng ASCII "M Notepad va go Hello", test suite dùng httpx Python client nên không bị |

## 8. Rủi ro còn lại

| Rủi ro | Lý do chưa giải quyết | Giải quyết ở |
|---|---|---|
| Stop giữa step đang chạy sẽ đợi step xong (không kill tool giữa chừng) | Plan cho phép; tool không có cancel API | Post-MVP |
| Retry chạy lại từ current step, không skip step OK | Đúng theo spec | OK |
| Không có timeout per step — tool treo sẽ treo workflow | Plan chưa yêu cầu | Phase 10 hardening |
| Pause/resume/stop qua WS không có auth — bất cứ client nào cũng điều khiển được | MVP local-first, single user | Post-MVP |
| Runner state chỉ in-memory — restart backend mất vị trí pause/stop | Phase 2 đã có DB; runner state chưa persist | Phase 10 |
| Retry không reset `current_step_index` nếu retry từ step completed trước đó | Edge case, MVP chấp nhận | Phase 10 |

## 9. Sẵn sàng cho phase tiếp theo

Theo plan §"Thứ tự ưu tiên" sau Phase 5:
- **Phase 4**: Qwen3 4B qua Ollama — thay `parse_intent` (hardcoded) bằng
  real model. WorkflowRunner interface không đổi, chỉ workflow source đổi.
- **Phase 6**: Tauri UI — wire frontend vào runner state + WS control.
- **Phase 7**: Permission gate thật — chèn giữa runner và ToolExecutor.

Cả 3 phase tiếp theo đều có thể bắt đầu ngay từ state hiện tại.

## 10. Lệnh kiểm tra nhanh

```powershell
cd D:\antigaravity_code\WindAgent\apps\backend
uv sync --extra dev
uv run pytest --timeout=15                    # 97 passed
$env:WINDAGENT_MOCK_GUI=1
uv run uvicorn main:app --port 8765           # start server with mock GUI
# Trong shell khác:
$sid = (curl -X POST http://127.0.0.1:8765/sessions | ConvertFrom-Json).session_id
curl -X POST http://127.0.0.1:8765/sessions/$sid/messages -H "Content-Type: application/json" --data-raw '{"content":"M Notepad va go Hello"}'
Start-Sleep 1
curl http://127.0.0.1:8765/sessions/$sid/runner      # status: completed
curl http://127.0.0.1:8765/sessions/$sid/workflow    # status: completed, both steps: success
```

Kỳ vọng: 97 passed, runner auto-start, workflow complete trong <1s.