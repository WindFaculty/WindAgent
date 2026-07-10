# Kế hoạch tích hợp Hermes vào Agent Workspace của WindAgent

## 1. Kết luận kiến trúc

Nên tích hợp theo mô hình **hai sidecar độc lập**, không import trực tiếp mã nguồn Hermes vào FastAPI của WindAgent:

```text
React / Tauri Workspace
        │
        │ REST + WebSocket
        ▼
WindAgent FastAPI :8765
  ├─ Session facade
  ├─ Event bridge
  ├─ Permission gateway
  ├─ Model Router
  ├─ SQLite audit
  └─ Browser / Terminal bridge
        │
        │ HTTP + SSE, Bearer auth
        ▼
Hermes Gateway :8642
  ├─ Agent loop
  ├─ Todo planning
  ├─ Terminal / Files / Web / Memory / Skills
  ├─ Subagents
  └─ Persistent Hermes sessions
        │
        │ OpenAI-compatible API
        ▼
WindAgent Router :8765/v1
        │
        ▼
NVIDIA / Gemini / OpenRouter / Ollama / provider khác
```

Vai trò được tách rõ:

* **Hermes** là agent runtime: suy luận, gọi tool, todo planning, memory, skills, subagent.
* **WindAgent** là control plane: giao diện, session facade, quyền, audit, browser preview, model router, quota và trạng thái.
* Frontend chỉ kết nối với WindAgent. Không để React gọi thẳng Hermes vì Hermes API có quyền sử dụng terminal và yêu cầu API key cho mọi deployment.

Hermes đã có API server phù hợp cho kiến trúc này: session API, chat streaming, Runs API, SSE event stream, stop, approval, health, capabilities, skills và toolsets.

---

## 2. Việc cần xử lý trước khi tích hợp

GitHub hiện tại chưa hoàn toàn trùng với bản local bạn vừa probe.

Trên branch `feat/router-phase6-memory-a2a`:

* `apps/desktop/src/api/client.ts` vẫn là mock client, trả session, workflow, health và WebSocket giả.
* `App.tsx` vẫn chạy luồng mô phỏng bằng state, timer, task và terminal hardcoded.
* Thanh trạng thái bên phải cũng đang dùng dữ liệu mô phỏng cho Tools, Memory và Recent Actions.
* Backend trong GitHub vẫn mount router ở root, chưa thấy prefix `/api/v1`.

Do đó, bước đầu tiên phải là đẩy phiên bản local đã probe lên một branch cố định, sau đó mới tích hợp Hermes trên branch đó. Nếu không, Codex hoặc Hermes có thể vô tình thay đổi lại client mock.

### Chuẩn hóa route

Đề xuất chọn chuẩn chính thức:

```text
REST:      /api/v1/*
WebSocket: /ws/{session_id}
Compatibility:
  /health
  /models/health
```

Backend mount toàn bộ session, permissions và runtime API dưới `/api/v1`. Hai route `/health` và `/models/health` được giữ làm alias để không phá script healthcheck cũ.

---

## 3. Chiến lược sử dụng Hermes

### 3.1 Chạy Hermes như dịch vụ local

Tạo một Hermes profile riêng cho WindAgent:

```text
Profile: windagent
Host:    127.0.0.1
Port:    8642
```

Biến môi trường phía WindAgent:

```env
WINDAGENT_HERMES_ENABLED=true
WINDAGENT_HERMES_MODE=external
WINDAGENT_HERMES_URL=http://127.0.0.1:8642
WINDAGENT_HERMES_API_KEY=***
WINDAGENT_HERMES_PROFILE=windagent
WINDAGENT_HERMES_TIMEOUT_SECONDS=120
```

Hermes được cấu hình:

```env
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=***
```

Hermes native Windows hỗ trợ CLI, gateway và tools; shell mặc định có thể sử dụng Git Bash được cài kèm.

Không tự động tải hoặc cài Hermes từ backend. `HermesProcessManager` chỉ:

1. Probe gateway.
2. Báo trạng thái chưa cài/chưa chạy.
3. Tùy chọn khởi động `hermes -p windagent gateway` khi người dùng bật chế độ managed.

### 3.2 Hermes gọi model qua WindAgent Router

Hermes nên gọi LLM thông qua OpenAI-compatible gateway hiện có của WindAgent:

```text
Hermes provider base URL:
http://127.0.0.1:8765/v1

Hermes model:
auto/Coder
```

Gateway WindAgent đã hiểu các định danh `role:*` và `auto/*`, sau đó resolve sang role của router.

Luồng hoàn chỉnh:

```text
Hermes agent loop
  → POST WindAgent /v1/chat/completions model=auto/Coder
  → Router chọn model
  → ProviderGateway gọi provider
  → fallback khi lỗi/quota
  → trả kết quả cho Hermes
```

Nhờ vậy Hermes không tự cạnh tranh với Router của WindAgent.

### 3.3 Khoảng trống phải sửa trong Router

Streaming hiện tại của WindAgent chưa phải streaming thực. Backend đợi nội dung hoàn chỉnh rồi cắt chuỗi thành các đoạn 5 ký tự và phát SSE. Token usage cũng đang được ước lượng bằng số từ.

Trước khi đánh dấu tích hợp production-ready cần:

* Stream trực tiếp từng delta từ provider.
* Truyền nguyên `usage` do provider trả về.
* Truyền model/provider thực tế được chọn.
* Phát sự kiện fallback.
* Hỗ trợ cancellation khi Hermes dừng run.
* Không tạo stream giả từ kết quả hoàn chỉnh.

---

## 4. Backend Hermes Bridge

Tạo package mới:

```text
apps/backend/services/hermes/
  client.py
  process_manager.py
  session_bridge.py
  run_bridge.py
  event_mapper.py
  event_reconciler.py
  tool_catalog.py
  browser_bridge.py
  terminal_bridge.py
  schemas.py
```

### `HermesClient`

Đóng gói các API:

```text
GET  /health
GET  /health/detailed
GET  /v1/capabilities
GET  /v1/models
GET  /v1/toolsets
GET  /v1/skills

POST /api/sessions
GET  /api/sessions/{id}
GET  /api/sessions/{id}/messages
POST /api/sessions/{id}/chat/stream

POST /v1/runs
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/stop
POST /v1/runs/{run_id}/approval
```

Hermes session stream đã định nghĩa các sự kiện như `assistant.delta`, `tool.started`, `tool.completed`, `run.completed`.

### `HermesRunBridge`

Mỗi lần người dùng gửi prompt:

1. Kiểm tra WindAgent session.
2. Resolve hoặc tạo Hermes session.
3. Gửi `POST /v1/runs`.
4. Lưu `run_id`.
5. Mở SSE `/v1/runs/{run_id}/events`.
6. Chuyển Hermes events thành WindAgent events.
7. Ghi raw event và normalized event vào SQLite.
8. Broadcast qua `/ws/{windagent_session_id}`.

Runs API được thiết kế chính xác cho dashboard có thể attach/detach, poll lại trạng thái và theo dõi tiến trình dài.

### Đồng bộ session

Tạo bảng:

```text
SessionRuntimeLinkORM
  id
  windagent_session_id
  runtime_type              # hermes
  hermes_session_id
  hermes_run_id
  agent_role                # Coder, Researcher...
  workspace_root
  status
  last_event_sequence
  created_at
  updated_at
```

Không lưu Hermes API key trong database.

---

## 5. Giao thức sự kiện thống nhất

Giữ envelope hiện tại:

```json
{
  "event": "assistant_delta",
  "timestamp": "2026-07-11T00:00:00Z",
  "sequence": 143,
  "data": {}
}
```

Thêm `sequence` để reconnect không bị trùng hoặc mất event.

### Mapping đề xuất

| Hermes event       | WindAgent event               | Panel sử dụng         |
| ------------------ | ----------------------------- | --------------------- |
| Run bắt đầu        | `agent_state_changed`         | Agent State           |
| `assistant.delta`  | `assistant_delta`             | Chat                  |
| Assistant hoàn tất | `assistant_message_completed` | Chat                  |
| `tool.started`     | `tool_call_started`           | Tools, Recent Actions |
| `tool.completed`   | `tool_call_finished`          | Tools, Terminal       |
| Todo write/read    | `workflow_updated`            | Current Task          |
| Approval pending   | `permission_request`          | Permissions           |
| Approval resolved  | `permission_granted/denied`   | Permissions           |
| Run completed      | `session_finished`            | Toàn trang            |
| Usage update       | `runtime_usage_updated`       | Model/Usage/Context   |
| Router fallback    | `model_route_changed`         | Model status          |
| Browser action     | `browser_state_updated`       | Browser Preview       |
| Terminal stdout    | `terminal_output_delta`       | Terminal              |
| Runtime error      | `error`                       | Chat, status          |

Frontend không nên tự diễn giải raw Hermes event. Việc chuẩn hóa phải được thực hiện tại backend để Hermes có thể nâng version mà không phá UI.

---

## 6. Giao diện chat streaming

Tách `AgentWorkspace` khỏi `App.tsx`. Trang này không tiếp tục nhận hàng loạt state mock qua props.

Cấu trúc đề xuất:

```text
pages/AgentWorkspace/
  AgentWorkspacePage.tsx
  components/
    ChatPanel.tsx
    TaskPanel.tsx
    TerminalPanel.tsx
    AgentBrowserPanel.tsx
    RuntimeSidebar.tsx
    PermissionDialog.tsx
  hooks/
    useAgentSession.ts
    useAgentEventStream.ts
    useWorkspaceSnapshot.ts
    useRunControls.ts
  store/
    agentWorkspaceStore.ts
  reducers/
    agentEventReducer.ts
```

### Luồng chat

Khi mount:

1. Đọc session gần nhất từ local storage hoặc URL.
2. Tạo session nếu chưa có.
3. Hydrate bằng `GET /api/v1/sessions/{id}/snapshot`.
4. Kết nối WebSocket.
5. Reconcile các event sau `last_sequence`.

Khi gửi:

1. Thêm user message theo optimistic update.
2. Gọi `POST /api/v1/sessions/{id}/messages`.
3. Tạo một assistant message rỗng.
4. Nối từng `assistant_delta` vào đúng `message_id`.
5. Khi hoàn tất, khóa nội dung và lưu usage.

Không dùng `setInterval`, timeout giả hoặc checklist hardcoded.

---

## 7. Current Task theo todo của Hermes

Hermes có tool `todo` riêng để agent phân rã nhiệm vụ. Mỗi task có:

```json
{
  "id": "1",
  "content": "Đọc cấu trúc repository",
  "status": "in_progress"
}
```

Các status hợp lệ:

```text
pending
in_progress
completed
cancelled
```

Todo có thứ tự ưu tiên, và hướng dẫn của Hermes quy định chỉ một item ở trạng thái `in_progress` tại một thời điểm. Mỗi lần gọi tool đều trả toàn bộ danh sách hiện tại.

### Mapping vào WindAgent Workflow

Lần đầu Hermes gọi `todo`:

```text
workflow_created
```

Những lần sau:

```text
workflow_updated
step_started
step_completed
step_cancelled
```

Backend upsert theo:

```text
windagent_session_id + hermes_todo_id
```

Task panel hiển thị:

* Objective.
* Danh sách task theo đúng thứ tự Hermes.
* Pending, In progress, Completed, Cancelled.
* Thời gian bắt đầu và thời lượng.
* Tool đang được task hiện tại sử dụng.
* Lỗi gần nhất.
* Nút xem input/output của từng bước.

Không để frontend tự suy đoán task từ văn bản chat.

---

## 8. Terminal / PowerShell / Logs

Cần phân biệt hai chế độ:

### Agent Logs

Đây là chế độ mặc định và an toàn hơn:

```text
> pytest tests -q
[stdout] 387 passed
[exit] 0
[duration] 42.5s
```

Dữ liệu lấy từ `tool.started` và `tool.completed`:

* Command.
* Working directory.
* Tool name.
* Stdout/stderr.
* Exit code.
* Duration.
* Trạng thái approval.
* Agent/subagent đã gọi.

### Interactive Terminal

Đây là terminal riêng do người dùng điều khiển, không phải agent log:

* PowerShell qua Windows ConPTY.
* Tabs.
* Resize.
* Kill process.
* Read-only mode khi agent đang chạy.

MVP nên hoàn thành Agent Logs trước. Chỉ xây interactive PTY sau khi event bridge ổn định.

Hermes API cần được probe để xác định có phát stdout theo chunk hay chỉ trả output cuối. Nếu chỉ có output cuối, MVP hiển thị command ngay khi bắt đầu và output khi kết thúc. Muốn stdout thực sự live thì bổ sung một Hermes plugin hoặc custom MCP terminal tool gọi `WindAgentTerminalService`.

### Bảo mật terminal

* Che API key, bearer token và biến môi trường nhạy cảm.
* Không trả toàn bộ environment.
* Giới hạn workspace root.
* Lệnh nguy hiểm phải yêu cầu approval.
* Output có giới hạn kích thước và hỗ trợ tải artifact riêng.

---

## 9. Browser / App Preview

Iframe thông thường không đủ tin cậy vì nhiều trang chặn iframe và không cho frontend quan sát hành động agent.

Đề xuất `BrowserBridge`:

```text
Hermes
  → custom MCP/browser tool
  → WindAgent BrowserService
  → Playwright hoặc Chrome DevTools Protocol
  → screenshot + URL + title + action events
  → WebSocket
  → AgentBrowserPanel
```

Panel hiển thị:

* Screenshot hiện tại.
* URL.
* Title.
* Loading state.
* Vị trí click gần nhất.
* Tool đang thao tác.
* Back, Forward, Reload.
* Open externally.
* Take control / Return control.

Các event:

```text
browser_session_started
browser_navigation_started
browser_navigation_completed
browser_screenshot_updated
browser_action_started
browser_action_completed
browser_console
browser_error
```

Ảnh chỉ lưu đường dẫn artifact trong database; không lưu base64 lớn vào SQLite.

MVP có thể phát screenshot sau mỗi browser action. Sau đó mới tăng lên stream định kỳ khoảng 1–2 FPS.

---

## 10. Thanh trạng thái bên phải

### Agent State

Nguồn dữ liệu:

```text
Hermes run status + WindAgent connection status
```

Các trạng thái:

```text
Disconnected
Ready
Planning
Thinking
Executing tool
Waiting approval
Paused
Stopping
Completed
Failed
```

### Model

Hiển thị:

```text
Agent runtime: Hermes
Role: Coder
Provider: NVIDIA / Gemini / OpenRouter / Ollama
Model: model thực tế được router chọn
Route tier: Primary / Fallback / Final fallback
Latency
```

Không dùng trường `model` mà frontend gửi tới Hermes làm nguồn sự thật. Hermes ghi rõ model request có thể chỉ mang tính hiển thị, còn model thật được cấu hình phía server.

Nguồn chính xác phải là Router execution result của WindAgent.

### Usage Token

Nên tách:

```text
Current turn
  Input
  Output
  Total

Session cumulative
  Input
  Output
  Total
```

### Context Window

Hiển thị:

```text
Latest prompt tokens / selected model context window
```

Ví dụ:

```text
62,380 / 131,072
47.6%
```

Không lấy tổng token toàn session chia context window vì đó là hai khái niệm khác nhau.

`context_window` lấy từ Model Catalog của WindAgent. `latest prompt tokens` lấy từ provider usage của lần gọi gần nhất.

### Tools in Use

Tách thành hai nhóm:

```text
Active now
  Terminal — Running
  File System — Reading

Available integrations
  Terminal
  Files
  Browser
  Web Search
  Memory
  Skills
  Todo
  Delegation
  MCP
```

Hermes có endpoint `/v1/toolsets` và `/v1/skills` để frontend/control plane khám phá tool một cách xác định thay vì hỏi model.

### Recent Actions

Không hardcode. Lấy 20–50 normalized events gần nhất:

```text
00:12:31  Read apps/backend/main.py
00:12:34  Updated task 2 → completed
00:12:35  Ran pytest tests/router
00:12:48  24 tests passed
00:12:49  Switched to task 3
```

Mỗi action có thể click để mở:

* Tool input.
* Output.
* Artifact.
* Task liên quan.
* Model execution.
* Error stack đã scrub secret.

---

## 11. API WindAgent đề xuất

### Session API giữ tương thích

```http
POST /api/v1/sessions
```

Request mới:

```json
{
  "runtime": "hermes",
  "agent_role": "Coder",
  "workspace_path": "D:\\code\\WindAgent",
  "model_policy": "auto/Coder"
}
```

```http
POST /api/v1/sessions/{id}/messages
GET  /api/v1/sessions/{id}
GET  /api/v1/sessions/{id}/workflow
GET  /api/v1/sessions/{id}/runner
POST /api/v1/sessions/{id}/pause
POST /api/v1/sessions/{id}/resume
POST /api/v1/sessions/{id}/stop
```

### API bổ sung

```http
GET /api/v1/runtimes/hermes/health
GET /api/v1/runtimes/hermes/capabilities
GET /api/v1/runtimes/hermes/tools

GET /api/v1/sessions/{id}/snapshot
GET /api/v1/sessions/{id}/events?after_sequence=123
GET /api/v1/sessions/{id}/usage
GET /api/v1/sessions/{id}/actions
GET /api/v1/sessions/{id}/terminal
GET /api/v1/sessions/{id}/browser
```

`snapshot` là endpoint quan trọng nhất khi refresh hoặc WebSocket reconnect:

```json
{
  "session": {},
  "run": {},
  "messages": [],
  "workflow": {},
  "terminal": [],
  "browser": {},
  "tools": {},
  "usage": {},
  "model": {},
  "recent_actions": [],
  "pending_permission": null,
  "last_sequence": 143
}
```

### Permission

Giữ API hiện tại:

```http
POST /api/v1/permissions/{request_id}/decide
```

Backend chuyển tiếp sang:

```text
POST Hermes /v1/runs/{run_id}/approval
```

---

## 12. Điều khiển Pause / Resume / Stop

Hermes Runs API hỗ trợ stop nhưng không nên giả định hỗ trợ pause/resume hoàn chỉnh như WorkflowRunner hiện tại.

Chính sách:

* **Stop:** chuyển thẳng tới Hermes `/stop`.
* **Pause:** dừng nhận task mới và chờ tool hiện tại đạt safe point.
* **Resume:** nếu Hermes run còn sống thì tiếp tục; nếu đã bị cancel thì tạo run mới với cùng Hermes session và todo/history cũ.
* **New message while running:** giai đoạn đầu disable send và yêu cầu Stop; giai đoạn sau hỗ trợ interrupt-and-redirect.

Hermes agent loop có cancellation và interruptible API calls, đồng thời hỗ trợ callback cho stream delta, tool progress và status.

---

## 13. Các giai đoạn triển khai

### Giai đoạn 0 — Đóng băng baseline

* Push code local vừa probe.
* Xác nhận branch và commit.
* Loại bỏ client mock.
* Chuẩn hóa `/api/v1`.
* Thêm contract test cho toàn bộ route.
* Không thay đổi UI trong giai đoạn này.

**Gate:** curl và frontend đều dùng cùng contract; không còn 404 health/models.

### Giai đoạn 1 — Hermes connectivity

* `HermesClient`.
* Health, detailed health, capabilities.
* Tools và skills discovery.
* Config/env validation.
* Secret scrubbing.
* UI hiển thị Hermes Connected/Disconnected.

**Gate:** WindAgent nhận diện đúng Hermes version và capabilities; API key không xuất hiện trong log.

### Giai đoạn 2 — Session và streaming chat

* Mapping WindAgent session ↔ Hermes session.
* Tạo run.
* SSE consumer.
* WebSocket event bridge.
* Assistant token streaming.
* Stop.
* Reconnect và snapshot hydration.

**Gate:** refresh trang giữa lúc run không làm mất session hoặc nhân đôi message.

### Giai đoạn 3 — Task và Recent Actions

* Parse Hermes `todo`.
* Upsert workflow/steps.
* Task panel dùng dữ liệu thật.
* Tool lifecycle.
* Recent action timeline.
* Permission mapping.

**Gate:** task thay đổi trên UI ngay sau mỗi todo update; đúng thứ tự và đúng trạng thái.

### Giai đoạn 4 — Terminal logs

* Hiển thị command.
* Output, exit code, duration.
* Filter stdout/stderr.
* Artifact cho output dài.
* Secret redaction.
* Optional terminal PTY để sau.

**Gate:** mọi command Hermes gọi đều xuất hiện trong audit và panel.

### Giai đoạn 5 — Router, model và usage

* Hermes dùng WindAgent `/v1`.
* Real streaming từ provider.
* Accurate usage passthrough.
* Selected model/provider/fallback events.
* Context calculation.
* Sidebar model/usage/context thật.

**Gate:** model hiển thị khớp RouterExecutionLog; token không còn tính bằng số từ.

### Giai đoạn 6 — Browser Bridge

* Playwright/CDP service.
* Custom Hermes MCP/browser tool.
* URL/title/screenshot events.
* Browser ownership controls.
* Artifact screenshots.

**Gate:** khi Hermes navigate/click, UI cập nhật preview và recent actions tương ứng.

### Giai đoạn 7 — UI hardening

* Tách AgentWorkspace khỏi `App.tsx`.
* Zustand hoặc reducer event-driven.
* Virtualized terminal/action list.
* Markdown/code rendering.
* Loading/error/empty states.
* Responsive layout.
* Không còn nội dung demo hardcoded.

**Gate:** disable Hermes vẫn mở trang được với trạng thái cấu hình rõ ràng, không crash.

### Giai đoạn 8 — Test và production hardening

* Unit test event mapper.
* Fake Hermes server cho integration tests.
* SSE reconnect/backpressure tests.
* Permission timeout tests.
* Hermes crash/restart reconciliation.
* WebSocket duplicate/out-of-order tests.
* Windows path và process tests.
* Frontend Playwright E2E.
* Full backend regression.

**Gate:** toàn bộ suite cũ pass; test mới chạy không cần provider thật.

---

## 14. Acceptance criteria cuối cùng

Tích hợp chỉ được xem là hoàn thành khi đạt đồng thời:

1. Người dùng gửi yêu cầu bằng ngôn ngữ tự nhiên và thấy câu trả lời stream dần.
2. Task panel phản ánh chính xác todo list của Hermes.
3. Chỉ một task `in_progress`, trừ trường hợp subagent được thể hiện riêng.
4. Terminal hiển thị command, output, exit code và duration thật.
5. Browser preview theo dõi browser do agent điều khiển.
6. Tools in Use phân biệt tool đang hoạt động và tool đã tích hợp.
7. Model, provider, route tier và fallback lấy từ Router thật.
8. Usage token lấy từ provider/Hermes, không ước lượng bằng word count.
9. Context hiển thị latest input tokens trên context window của model.
10. Stop và permission hoạt động end-to-end.
11. Refresh/reconnect không mất trạng thái.
12. Không có API key trong browser, log, WebSocket hoặc SQLite.
13. Hermes ngừng chạy không làm WindAgent backend crash.
14. Không còn dữ liệu hardcoded trên Agent Workspace.

---

## 15. Chiến lược branch và commit

Branch đề xuất:

```text
feat/hermes-agent-workspace-integration
```

Base:

```text
branch chứa bản local đã probe
```

Thứ tự commit:

```text
chore(api): normalize v1 routes and remove workspace mocks
feat(hermes): add runtime client and capability probing
feat(hermes): bridge sessions runs and SSE events
feat(workspace): stream chat from normalized agent events
feat(workspace): map Hermes todo state to task workflow
feat(workspace): add terminal tool activity and audit
feat(router): route Hermes model calls through provider gateway
feat(workspace): expose model usage and context metrics
feat(browser): add controlled agent browser bridge
test(hermes): add contract integration and reconnect coverage
docs(hermes): document architecture setup and operations
```

Ưu tiên triển khai ngay **Giai đoạn 0 → 3**. Sau bốn giai đoạn này, trang đã có chat streaming, agent thật, task thật, tool state và Recent Actions; terminal/browser/model telemetry có thể được hoàn thiện tuần tự mà không phải viết lại kiến trúc.
