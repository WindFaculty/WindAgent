# Kế hoạch triển khai từng phase để đạt MVP ứng dụng Desktop AI Computer-Use Agent local-first

## 0. Định nghĩa MVP cần đạt

MVP không phải là bản đầy đủ của toàn bộ kiến trúc. MVP chỉ cần chứng minh được vòng lặp cốt lõi:

**Người dùng nhập lệnh tự nhiên → Qwen3 4B lập workflow đơn giản → app thực thi từng bước trên máy Windows → UI stream tiến trình → người dùng có thể Stop/Pause/Resume → hệ thống lưu log và lịch sử.**

Kịch bản demo bắt buộc:

> Người dùng gõ: “Mở Notepad và gõ Hello from local AI agent.”
> Agent tạo workflow:
>
> 1. Mở Notepad
> 2. Gõ nội dung
> 3. Báo hoàn thành
>    Executor thực thi bằng PyAutoGUI. UI hiển thị từng bước đang chạy, thành công hoặc lỗi.

Kịch bản demo phụ:

> Người dùng gõ: “Mở trang google.com trên Edge.”
> Agent tạo workflow:
>
> 1. Mở Edge
> 2. Điều hướng tới URL
> 3. Báo hoàn thành

MVP chưa cần làm:

* Chưa cần GUI-Actor vision thật.
* Chưa cần Playwright.
* Chưa cần model manager UI đầy đủ.
* Chưa cần workflow drag/drop.
* Chưa cần plugin sandbox.
* Chưa cần multi-agent.
* Chưa cần auto-update.
* Chưa cần context 64k/vLLM/llama.cpp nâng cao.

---

# Phase 0 — Chốt scope, repo skeleton và chuẩn giao tiếp nội bộ

## Mục tiêu

Tạo nền móng dự án rõ ràng, tránh over-engineering. Sau phase này phải có cấu trúc thư mục, chuẩn API nội bộ, chuẩn event streaming và dữ liệu mẫu để các phase sau phát triển không bị lệch hướng.

## Việc cần làm

### 0.1. Tạo cấu trúc repository

Cấu trúc đề xuất:

```txt
desktop-ai-agent/
├── apps/
│   ├── desktop/                 # Tauri + React + TypeScript
│   └── backend/                 # Python FastAPI sidecar
├── docs/
│   ├── mvp_scope.md
│   ├── event_protocol.md
│   ├── api_contract.md
│   └── safety_policy.md
├── models/
│   └── README.md
├── scripts/
│   ├── dev_backend.ps1
│   ├── dev_desktop.ps1
│   └── healthcheck.ps1
├── artifacts/
│   └── runs/
└── README.md
```

### 0.2. Viết tài liệu MVP scope

File: `docs/mvp_scope.md`

Nội dung cần có:

* MVP làm gì.
* MVP không làm gì.
* Demo bắt buộc.
* Demo phụ.
* Acceptance criteria.
* Các rủi ro kỹ thuật đã biết.

### 0.3. Định nghĩa event protocol

File: `docs/event_protocol.md`

Các event tối thiểu:

```json
{
  "event": "step_started",
  "timestamp": "2026-06-18T00:00:00+07:00",
  "data": {
    "session_id": "string",
    "step_id": "string",
    "step_name": "string"
  }
}
```

Event MVP cần có:

* `session_created`
* `message_received`
* `planning_started`
* `planning_finished`
* `workflow_created`
* `step_started`
* `step_completed`
* `step_failed`
* `tool_call_started`
* `tool_call_finished`
* `permission_request`
* `permission_granted`
* `permission_denied`
* `user_paused`
* `user_resumed`
* `user_stopped`
* `error`
* `session_finished`

### 0.4. Định nghĩa workflow schema tối thiểu

Workflow MVP chỉ cần dạng tuần tự:

```json
{
  "workflow_id": "uuid",
  "session_id": "uuid",
  "steps": [
    {
      "id": "uuid",
      "order": 1,
      "name": "Open Notepad",
      "tool_name": "open_app",
      "params": {
        "app": "notepad"
      },
      "status": "pending"
    }
  ]
}
```

## Đầu ra của phase

* Repo chạy được skeleton.
* Có thư mục `apps/desktop`.
* Có thư mục `apps/backend`.
* Có tài liệu MVP scope.
* Có tài liệu event protocol.
* Có schema workflow mẫu.

## Acceptance criteria

* Developer mới mở repo có thể hiểu MVP cần làm gì trong 10 phút.
* Không có module thừa như plugin system, Playwright, multi-agent trong phase này.
* Tất cả phase sau phải bám theo `docs/mvp_scope.md`.

---

# Phase 1 — Backend FastAPI sidecar tối thiểu

## Mục tiêu

Tạo backend local chạy được độc lập, có API tạo session, nhận message, tạo workflow giả lập, stream event qua WebSocket.

## Việc cần làm

### 1.1. Khởi tạo FastAPI app

Thư mục:

```txt
apps/backend/
├── main.py
├── routers/
│   ├── sessions.py
│   ├── workflow.py
│   └── websocket.py
├── services/
│   ├── session_service.py
│   ├── workflow_service.py
│   └── event_bus.py
├── schemas/
│   ├── session.py
│   ├── workflow.py
│   └── event.py
└── tests/
```

### 1.2. API tối thiểu

Cần có:

```txt
POST /sessions
GET  /sessions/{session_id}
POST /sessions/{session_id}/messages
GET  /sessions/{session_id}/workflow
WS   /ws/{session_id}
GET  /health
```

### 1.3. Event bus nội bộ

Implement `EventBus` để backend có thể phát event:

```python
await event_bus.publish(session_id, {
    "event": "planning_started",
    "data": {...}
})
```

Ban đầu có thể dùng in-memory pub/sub. Chưa cần Redis.

### 1.4. Workflow giả lập

Khi user gửi message:

```txt
Mở Notepad và gõ Hello
```

Backend chưa cần gọi model thật. Có thể hardcode parser tạm:

```json
[
  {
    "name": "Open Notepad",
    "tool_name": "open_app",
    "params": {"app": "notepad"}
  },
  {
    "name": "Type text",
    "tool_name": "type_text",
    "params": {"text": "Hello"}
  }
]
```

## Đầu ra của phase

* Backend chạy bằng lệnh PowerShell.
* Gọi API tạo session được.
* Gửi message tạo workflow giả lập được.
* WebSocket nhận event được.

## Acceptance criteria

* `GET /health` trả về OK.
* `POST /sessions` tạo session ID.
* `POST /sessions/{id}/messages` phát event `planning_started`, `planning_finished`, `workflow_created`.
* Có unit test cho session service, workflow service, event bus.

---

# Phase 2 — SQLite persistence và audit log

## Mục tiêu

MVP phải local-first, vì vậy cần lưu session, message, workflow, step, tool call và event vào SQLite. Sau phase này, đóng/mở lại backend vẫn thấy lịch sử cơ bản.

## Việc cần làm

### 2.1. Thêm SQLAlchemy hoặc SQLModel

Cấu trúc:

```txt
apps/backend/db/
├── database.py
├── models.py
└── migrations/
```

### 2.2. Bảng tối thiểu

MVP cần 6 bảng:

```txt
chat_sessions
messages
workflows
workflow_steps
tool_calls
execution_events
```

### 2.3. Schema tối thiểu

`chat_sessions`:

```txt
id
created_at
updated_at
status
```

`messages`:

```txt
id
session_id
sender
content
created_at
```

`workflows`:

```txt
id
session_id
status
created_at
updated_at
```

`workflow_steps`:

```txt
id
workflow_id
order_index
name
tool_name
params_json
status
created_at
updated_at
```

`tool_calls`:

```txt
id
session_id
step_id
tool_name
input_json
output_json
status
created_at
```

`execution_events`:

```txt
id
session_id
event_type
data_json
created_at
```

### 2.4. Lưu tất cả event vào DB

Mỗi khi `event_bus.publish()` được gọi, event cũng phải được ghi vào bảng `execution_events`.

## Đầu ra của phase

* SQLite DB tự tạo khi backend khởi động.
* Session/message/workflow/event được lưu.
* Có thể xem lại workflow của session cũ.

## Acceptance criteria

* Tạo session → DB có row.
* Gửi message → DB có message.
* Workflow được tạo → DB có workflow + steps.
* Event được stream và cũng được lưu vào DB.
* Có test xác nhận event không bị mất khi workflow chạy.

---

# Phase 3 — Tool Executor desktop cơ bản bằng PyAutoGUI

## Mục tiêu

Biến workflow từ dữ liệu tĩnh thành hành động thật trên Windows.

## Tool MVP cần có

```txt
open_app
open_url
type_text
hotkey
press_key
click_xy
scroll
screenshot
wait
```

## Việc cần làm

### 3.1. Tạo Tool Registry

File:

```txt
apps/backend/services/tool_registry.py
apps/backend/services/tool_executor.py
```

Mỗi tool có metadata:

```python
{
    "name": "open_app",
    "description": "Open a Windows application",
    "risk_level": "medium",
    "requires_confirmation": False
}
```

### 3.2. Implement tool `open_app`

Ban đầu hỗ trợ:

```txt
notepad
calc
mspaint
edge
explorer
```

Ví dụ:

```python
subprocess.Popen(["notepad.exe"])
```

### 3.3. Implement tool `type_text`

Dùng PyAutoGUI:

```python
pyautogui.write(text, interval=0.01)
```

Với tiếng Việt có dấu, fallback sang clipboard paste:

```python
pyperclip.copy(text)
pyautogui.hotkey("ctrl", "v")
```

### 3.4. Implement tool `open_url`

Cách MVP đơn giản:

```python
subprocess.Popen(["cmd", "/c", "start", "msedge", url])
```

### 3.5. Implement screenshot artifact

`screenshot()` lưu ảnh vào:

```txt
artifacts/runs/{session_id}/screenshots/{timestamp}.png
```

Return:

```json
{
  "path": "...",
  "width": 1920,
  "height": 1080
}
```

### 3.6. Ghi tool call log

Mỗi tool call phải ghi:

* tool name
* input
* output
* status
* error nếu có

## Đầu ra của phase

* Backend có thể mở Notepad thật.
* Backend có thể gõ text thật.
* Backend có thể mở Edge với URL thật.
* Tool call được stream về UI/console.
* Tool call được lưu DB.

## Acceptance criteria

* Chạy workflow `open_app notepad → type_text Hello` thành công.
* Nếu tool lỗi, step chuyển sang `failed`.
* Nếu user stop, tool executor không chạy step tiếp theo.
* Screenshot được lưu thành artifact.

---

# Phase 4 — Planner Qwen3 4B Q4 qua Ollama

## Mục tiêu

Thay hardcoded parser bằng model planner local. Qwen3 4B Q4 sẽ nhận lệnh người dùng và trả về workflow JSON hợp lệ.

## Việc cần làm

### 4.1. Tạo Model Client

File:

```txt
apps/backend/services/model_client.py
apps/backend/services/planner_service.py
```

Interface:

```python
class ModelClient:
    async def chat(self, messages, stream=False) -> str:
        ...
```

Provider MVP:

```txt
ollama_openai_compatible
```

Endpoint mặc định:

```txt
http://localhost:11434/v1/chat/completions
```

### 4.2. Health check Ollama

Endpoint:

```txt
GET /models/health
```

Trả về:

```json
{
  "provider": "ollama",
  "online": true,
  "model": "qwen3:4b-q4",
  "latency_ms": 1234
}
```

### 4.3. Prompt planner MVP

Planner phải trả JSON, không trả văn xuôi.

System prompt cần ép schema:

```txt
You are a local desktop workflow planner.
Convert the user's instruction into a sequential workflow.
Only use these tools:
- open_app
- open_url
- type_text
- hotkey
- press_key
- click_xy
- scroll
- screenshot
- wait

Return valid JSON only.

Schema:
{
  "steps": [
    {
      "name": "string",
      "tool_name": "string",
      "params": {}
    }
  ]
}
```

### 4.4. JSON validation

Không tin output model trực tiếp.

Cần có:

* JSON parse.
* Validate tool_name thuộc whitelist.
* Validate params đúng schema.
* Nếu invalid, gọi repair prompt một lần.
* Nếu vẫn invalid, trả lỗi rõ ràng về UI.

### 4.5. Fallback parser

Để MVP ổn định, giữ fallback rule-based cho 2 demo:

* Mở Notepad và gõ X.
* Mở URL X trên Edge.

Nếu Qwen lỗi, fallback vẫn giúp demo chạy được.

## Đầu ra của phase

* User nhập lệnh tự nhiên.
* Qwen tạo workflow.
* Backend validate workflow.
* Workflow chạy sequential.

## Acceptance criteria

* Lệnh “Mở Notepad và gõ Hello” tạo đúng 2 step.
* Lệnh “Mở google.com trên Edge” tạo đúng step mở URL.
* Nếu Qwen trả JSON lỗi, backend không crash.
* Nếu Ollama offline, UI nhận lỗi `model_offline`.

---

# Phase 5 — Workflow Engine sequential + control Pause/Resume/Stop

## Mục tiêu

Có engine chạy workflow thật, từng step một, có trạng thái rõ ràng, có thể dừng/tạm dừng/tiếp tục.

## State machine MVP

Step status:

```txt
pending
running
success
failed
skipped
cancelled
```

Session/workflow status:

```txt
idle
planning
running
paused
completed
failed
cancelled
```

## Việc cần làm

### 5.1. Workflow runner

File:

```txt
apps/backend/services/workflow_runner.py
```

Logic:

```txt
for step in steps:
    if stop_requested:
        mark cancelled
        break

    while paused:
        wait

    mark step running
    execute tool
    mark success/failed
```

### 5.2. Control API

```txt
POST /sessions/{session_id}/pause
POST /sessions/{session_id}/resume
POST /sessions/{session_id}/stop
POST /workflow/{step_id}/retry
```

### 5.3. WebSocket control message

Frontend có thể gửi:

```json
{"action": "pause"}
{"action": "resume"}
{"action": "stop"}
```

### 5.4. Error policy

MVP xử lý lỗi đơn giản:

* Tool lỗi → step failed.
* Workflow dừng.
* UI hiện lỗi.
* User có thể retry step hoặc stop.

Chưa cần auto-recovery phức tạp.

## Đầu ra của phase

* Workflow chạy tuần tự ổn định.
* Pause dừng trước step tiếp theo.
* Resume tiếp tục.
* Stop hủy workflow.
* Retry chạy lại step lỗi.

## Acceptance criteria

* Step không chạy song song.
* Stop không làm chạy tiếp step sau.
* Pause không giết app, chỉ tạm ngừng workflow.
* Mọi transition được stream và lưu DB.

---

# Phase 6 — Frontend Tauri + React MVP UI

## Mục tiêu

Tạo giao diện desktop tối thiểu nhưng đủ dùng: chat, workflow progress, log event, nút control.

## Layout MVP

```txt
┌───────────────────────────────────────────────┐
│ Header: Local Desktop AI Agent                │
├───────────────────────────────┬───────────────┤
│ Chat Panel                    │ Workflow Panel │
│                               │               │
│ User messages                 │ Step 1 ✅      │
│ Assistant/status messages     │ Step 2 ⏳      │
│ Tool events                   │ Step 3 ❌      │
│                               │               │
├───────────────────────────────┴───────────────┤
│ Input box + Send + Stop + Pause + Resume       │
└───────────────────────────────────────────────┘
```

## Việc cần làm

### 6.1. Tauri shell

Tạo app desktop:

```txt
apps/desktop/
├── src-tauri/
└── src/
```

Trong MVP, Tauri chỉ cần mở React app và gọi backend local.

### 6.2. Backend launcher

Có 2 lựa chọn:

Cách A cho dev MVP:

* User chạy backend bằng script riêng.
* Tauri frontend connect tới `localhost`.

Cách B cho MVP đóng gói:

* Tauri start Python sidecar.

Khuyến nghị MVP nội bộ: làm Cách A trước, sau đó mới Cách B ở Phase 9.

### 6.3. Chat UI

Component:

```txt
ChatPanel.tsx
MessageList.tsx
ChatInput.tsx
```

Chức năng:

* Nhập lệnh.
* Gửi message tới backend.
* Hiển thị message user.
* Hiển thị assistant status.
* Hiển thị lỗi.

### 6.4. Workflow panel

Component:

```txt
WorkflowPanel.tsx
WorkflowStepItem.tsx
```

Hiển thị:

* Step order.
* Step name.
* Tool name.
* Status.
* Error nếu có.

Chưa cần drag/drop.

### 6.5. Event stream client

Hook:

```txt
useSessionEvents.ts
```

Nhận event WebSocket và update UI realtime.

### 6.6. Control buttons

Nút:

```txt
Stop
Pause
Resume
Retry failed step
```

## Đầu ra của phase

* Mở app desktop thấy UI.
* Gửi lệnh từ UI được.
* UI nhận event realtime.
* UI hiển thị workflow progress.
* UI điều khiển Stop/Pause/Resume được.

## Acceptance criteria

* Không cần mở Swagger/Postman để demo.
* Demo Notepad chạy hoàn toàn từ UI.
* Khi step chạy, status đổi `pending → running → success`.
* Khi lỗi, UI hiện lỗi rõ ràng.
* WebSocket reconnect nếu refresh UI.

---

# Phase 7 — Safe Mode và permission gate tối thiểu

## Mục tiêu

MVP có khả năng điều khiển máy tính nên bắt buộc phải có lớp an toàn tối thiểu. Không cần hệ thống permission quá phức tạp, nhưng phải chặn các hành động nguy hiểm.

## Tool risk level MVP

```txt
safe:
- screenshot
- wait
- scroll

medium:
- open_app
- open_url
- type_text
- hotkey
- press_key
- click_xy

high:
- delete_file
- shell_command
- send_email
- payment
```

Trong MVP chưa implement high-risk tools, nhưng policy phải có.

## Việc cần làm

### 7.1. Tool whitelist

Agent chỉ được gọi tool nằm trong whitelist.

Nếu model tạo tool lạ:

```json
{"tool_name": "delete_all_files"}
```

Backend reject ngay.

### 7.2. Confirmation cho medium risk tùy cấu hình

MVP nên có setting:

```json
{
  "safe_mode": true,
  "confirm_before_type": true,
  "confirm_before_click": true
}
```

Để demo mượt, có thể mặc định:

* `open_app`: không cần confirm.
* `open_url`: không cần confirm.
* `type_text`: confirm nếu text dài hoặc chứa dữ liệu nhạy cảm.
* `click_xy`: confirm nếu dùng tọa độ manual.

### 7.3. Permission request event

Backend gửi:

```json
{
  "event": "permission_request",
  "data": {
    "tool_name": "type_text",
    "summary": "Type text into active window",
    "params": {
      "text": "Hello"
    }
  }
}
```

Frontend hiện dialog:

```txt
Agent muốn gõ nội dung vào cửa sổ hiện tại.
[Confirm] [Cancel]
```

### 7.4. Không chạy shell tùy ý trong MVP

MVP không cho planner tạo shell command. `open_app` phải là danh sách app được hỗ trợ, không truyền command tự do.

## Đầu ra của phase

* Tool whitelist hoạt động.
* Permission dialog hoạt động.
* User cancel thì step bị `cancelled`.
* Audit log lưu quyết định confirm/cancel.

## Acceptance criteria

* Model không thể gọi tool ngoài whitelist.
* User có thể cancel hành động nhập text.
* Permission event được lưu DB.
* Không có API chạy shell tự do.

---

# Phase 8 — GUI grounding stub cho MVP

## Mục tiêu

Vì MVP chưa cần GUI-Actor vision thật, nhưng kiến trúc phải chuẩn bị sẵn interface để sau này cắm Qwen2.5-VL GUI Actor. Phase này tạo “stub” để không phá kiến trúc sau này.

## Việc cần làm

### 8.1. Tạo interface GUI grounding

File:

```txt
apps/backend/services/gui_grounding.py
```

Interface:

```python
class GuiGroundingService:
    async def locate(self, screenshot_path: str, target: str) -> GuiPoint:
        ...
```

Return:

```json
{
  "x": 100,
  "y": 200,
  "confidence": 0.8,
  "method": "manual_stub"
}
```

### 8.2. Manual coordinate mode

Trong MVP, nếu user yêu cầu click theo tên nút nhưng chưa có vision model:

* Backend chụp screenshot.
* UI hiển thị message: “MVP chưa hỗ trợ nhận diện nút bằng vision. Hãy nhập tọa độ hoặc dùng click_xy.”
* Cho phép user nhập x/y.

### 8.3. Chuẩn bị model role

Định nghĩa sẵn role:

```txt
planner
gui_grounding
verifier
fallback
```

Nhưng MVP chỉ dùng `planner`.

## Đầu ra của phase

* Có interface để sau này thay stub bằng Qwen2.5-VL.
* Không hardcode GUI actor vào workflow runner.
* MVP vẫn chạy được với click_xy/manual.

## Acceptance criteria

* Code không phụ thuộc trực tiếp vào implementation vision.
* Có test cho `GuiGroundingServiceStub`.
* Khi gặp step `click_target`, hệ thống báo rõ chưa hỗ trợ vision thật thay vì click bừa.

---

# Phase 9 — Packaging nội bộ và developer runbook

## Mục tiêu

MVP phải dễ chạy trên máy Windows của bạn. Chưa cần installer hoàn chỉnh, nhưng phải có script khởi động rõ ràng.

## Việc cần làm

### 9.1. Script chạy backend

File:

```txt
scripts/dev_backend.ps1
```

Làm:

* Tạo venv nếu chưa có.
* Cài requirements.
* Chạy FastAPI.

### 9.2. Script chạy desktop

File:

```txt
scripts/dev_desktop.ps1
```

Làm:

* Cài npm package nếu thiếu.
* Chạy Tauri dev.

### 9.3. Script healthcheck

File:

```txt
scripts/healthcheck.ps1
```

Kiểm tra:

* Python version.
* Node version.
* Rust/Tauri CLI.
* Ollama running.
* Qwen model available.
* Backend health OK.
* SQLite writable.
* PyAutoGUI import OK.

### 9.4. README chạy MVP

README cần có:

```txt
1. Cài Ollama
2. Pull Qwen3 4B Q4
3. Chạy backend
4. Chạy desktop
5. Test lệnh demo
```

### 9.5. Build Tauri dev package

Tạo build local:

```txt
npm run tauri build
```

Nếu chưa bundle Python sidecar được, ghi rõ MVP hiện cần chạy backend bằng script riêng.

## Đầu ra của phase

* Có hướng dẫn chạy từ máy sạch.
* Có script kiểm tra lỗi môi trường.
* Có build desktop cơ bản.

## Acceptance criteria

* Clone repo → chạy healthcheck → biết thiếu gì.
* Chạy backend bằng 1 script.
* Chạy desktop bằng 1 script.
* Demo MVP không cần sửa code thủ công.

---

# Phase 10 — MVP hardening, test và release candidate

## Mục tiêu

Biến prototype thành MVP đủ ổn để dùng thử nhiều lần, không chỉ chạy demo một lần.

## Việc cần làm

### 10.1. Test suite tối thiểu

Backend tests:

```txt
test_session_api.py
test_workflow_creation.py
test_workflow_runner.py
test_tool_executor.py
test_permission_gate.py
test_model_planner_validation.py
test_event_stream.py
```

Frontend tests tối thiểu:

```txt
ChatPanel render
WorkflowPanel render
Event reducer update status
Control buttons call API
```

E2E manual test checklist:

```txt
[ ] Mở app
[ ] Tạo session
[ ] Gửi lệnh mở Notepad
[ ] Workflow xuất hiện
[ ] Notepad mở
[ ] Text được gõ
[ ] Event stream đúng thứ tự
[ ] Stop hoạt động
[ ] Pause/Resume hoạt động
[ ] Log được lưu
[ ] Restart backend vẫn thấy session cũ
```

### 10.2. Error handling

Các lỗi phải có thông báo rõ:

* Ollama chưa chạy.
* Model chưa tải.
* Backend offline.
* WebSocket mất kết nối.
* PyAutoGUI không có quyền điều khiển.
* Tool execution failed.
* Planner trả JSON sai.

### 10.3. Log file

Lưu log vào:

```txt
artifacts/logs/backend.log
artifacts/runs/{session_id}/events.jsonl
```

### 10.4. MVP release note

File:

```txt
docs/mvp_release_note.md
```

Nội dung:

* Tính năng đã có.
* Tính năng chưa có.
* Known issues.
* Cách chạy demo.
* Cách báo lỗi.

## Đầu ra của phase

* MVP release candidate.
* Test suite xanh.
* Demo ổn định.
* Có release note.

## Acceptance criteria cuối cùng cho MVP

MVP được xem là đạt khi toàn bộ tiêu chí sau pass:

### Core agent loop

* User nhập lệnh tự nhiên từ UI.
* Planner local Qwen3 4B tạo workflow JSON.
* Workflow được validate.
* Workflow chạy sequential.
* Step status stream realtime.

### Desktop control

* Mở Notepad được.
* Gõ text được.
* Mở Edge với URL được.
* Screenshot artifact tạo được.

### User control

* Stop hoạt động.
* Pause hoạt động.
* Resume hoạt động.
* Lỗi không làm app crash.

### Local-first

* Backend chạy local.
* SQLite lưu local.
* Qwen chạy qua Ollama local.
* Không gọi API cloud mặc định.

### Safety

* Tool whitelist hoạt động.
* Không có shell command tự do.
* Permission event hoạt động.
* Audit log lưu tool call.

### Persistence

* Session được lưu.
* Message được lưu.
* Workflow step được lưu.
* Tool call được lưu.
* Event được lưu.

### Packaging/dev experience

* Có script chạy backend.
* Có script chạy desktop.
* Có healthcheck.
* Có README MVP.

---

# Thứ tự ưu tiên thực hiện

## Nhóm bắt buộc làm trước

1. Phase 0 — Scope + protocol.
2. Phase 1 — Backend skeleton + WebSocket.
3. Phase 2 — SQLite persistence.
4. Phase 3 — PyAutoGUI Tool Executor.
5. Phase 5 — Workflow Runner sequential.

Lý do: đây là lõi runtime. Nếu chưa có các phần này, frontend đẹp hay model mạnh cũng chưa tạo ra sản phẩm.

## Nhóm làm tiếp để thành agent thật

6. Phase 4 — Qwen planner qua Ollama.
7. Phase 6 — Tauri React UI.
8. Phase 7 — Safe mode.

Lý do: khi runtime đã chắc, Qwen và UI mới có đất để chạy ổn định.

## Nhóm hoàn thiện MVP

9. Phase 8 — GUI grounding stub.
10. Phase 9 — Script/dev packaging.
11. Phase 10 — Hardening/test/release candidate.

---

# Worktree/task breakdown đề xuất

## Backend

```txt
apps/backend/main.py
apps/backend/routers/sessions.py
apps/backend/routers/workflow.py
apps/backend/routers/websocket.py
apps/backend/routers/models.py
apps/backend/services/event_bus.py
apps/backend/services/session_service.py
apps/backend/services/workflow_service.py
apps/backend/services/workflow_runner.py
apps/backend/services/tool_registry.py
apps/backend/services/tool_executor.py
apps/backend/services/model_client.py
apps/backend/services/planner_service.py
apps/backend/services/permission_service.py
apps/backend/services/gui_grounding.py
apps/backend/db/database.py
apps/backend/db/models.py
apps/backend/schemas/*.py
```

## Frontend

```txt
apps/desktop/src/components/chat/ChatPanel.tsx
apps/desktop/src/components/chat/MessageList.tsx
apps/desktop/src/components/chat/ChatInput.tsx
apps/desktop/src/components/workflow/WorkflowPanel.tsx
apps/desktop/src/components/workflow/WorkflowStepItem.tsx
apps/desktop/src/components/controls/RunControls.tsx
apps/desktop/src/hooks/useSessionEvents.ts
apps/desktop/src/api/client.ts
apps/desktop/src/state/sessionStore.ts
```

## Docs/scripts

```txt
docs/mvp_scope.md
docs/event_protocol.md
docs/api_contract.md
docs/safety_policy.md
docs/mvp_release_note.md
scripts/dev_backend.ps1
scripts/dev_desktop.ps1
scripts/healthcheck.ps1
```

---

# Backlog sau MVP

Sau khi MVP pass, mới mở các phase nâng cấp:

## Post-MVP P1 — Workflow editor đầy đủ

* Reorder step bằng drag/drop.
* Toggle step.
* Edit params.
* Save template.
* Load template.

## Post-MVP P2 — Model manager UI

* Add local model.
* Add API model.
* Assign role.
* Test latency.
* Fallback model.

## Post-MVP P3 — GUI Actor thật

* Qwen2.5-VL GUI Actor.
* Screenshot → element target → coordinate.
* Highlight trước khi click.
* Confirm nếu confidence thấp.

## Post-MVP P4 — Playwright browser automation

* Open Edge controlled context.
* DOM-based click.
* Form filling.
* Download file.
* Scrape table.

## Post-MVP P5 — Plugin/tool system

* Custom Python tool.
* Tool permission manifest.
* Sandbox.
* Import/export workflow.

---

# Kết luận

Để đạt MVP nhanh và chắc, không nên triển khai ngay toàn bộ kiến trúc lớn. Trọng tâm phải là một “vertical slice” hoàn chỉnh:

**Tauri UI → FastAPI backend → Qwen planner → workflow runner → PyAutoGUI executor → streaming events → SQLite log → safe control.**

Khi vertical slice này chạy ổn với demo Notepad và Edge, sản phẩm đã chứng minh được năng lực cốt lõi của desktop AI computer-use agent local-first. Các phần như GUI-Actor vision, Playwright, model manager UI, template workflow và plugin system nên được đưa vào sau MVP để tránh làm chậm bản đầu tiên.
