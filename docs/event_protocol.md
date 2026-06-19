# Event Protocol — Local Desktop AI Agent

Tài liệu này định nghĩa **hợp đồng event** giữa backend FastAPI và frontend
Tauri/React. Bất kỳ thay đổi nào về shape, tên field hay ý nghĩa event đều
phải cập nhật file này trước khi sửa code.

## 1. Định dạng chung

Mọi event stream qua WebSocket đều là JSON object có 3 trường bắt buộc:

```json
{
  "event": "step_started",
  "timestamp": "2026-06-18T00:00:00+07:00",
  "data": { ... }
}
```

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `event` | string | có | Tên event, snake_case, xem bảng §3 |
| `timestamp` | string | có | ISO 8601 với timezone, ví dụ `2026-06-18T14:32:11+07:00` |
| `data` | object | có | Payload riêng của từng event, xem §4 |

`session_id` luôn nằm trong `data` trừ khi event là `session_created`
(trong trường hợp đó session_id vừa được tạo và sẽ có trong data).

## 2. Kênh truyền

- WebSocket endpoint: `ws://localhost:<port>/ws/{session_id}`
- Backend đẩy event realtime, không queue client-side
- Frontend có trách nhiệm reconnect + replay event từ DB nếu mất kết nối
- Backend cũng ghi mọi event vào bảng `execution_events` để persistence

## 3. Danh sách event MVP

17 event bắt buộc, chia theo nhóm:

### Nhóm session lifecycle
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `session_created` | User tạo session mới | Backend |
| `session_finished` | Workflow kết thúc (success/failed/cancelled) | Backend |

### Nhóm message & planning
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `message_received` | Backend nhận message từ user | Backend |
| `planning_started` | Bắt đầu gọi planner | Backend |
| `planning_finished` | Planner trả về JSON hợp lệ | Backend |
| `workflow_created` | Workflow đã được validate và lưu DB | Backend |

### Nhóm step execution
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `step_started` | Workflow runner bắt đầu chạy 1 step | Backend |
| `step_completed` | Step chạy xong, success | Backend |
| `step_failed` | Step chạy lỗi, có `error` field | Backend |

### Nhóm tool call
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `tool_call_started` | Bắt đầu gọi tool cụ thể | Backend |
| `tool_call_finished` | Tool trả kết quả (kèm success/failed) | Backend |

### Nhóm permission
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `permission_request` | Cần user confirm trước khi chạy tool medium-risk | Backend |
| `permission_granted` | User đã bấm Confirm | Frontend → Backend → phát lại |
| `permission_denied` | User đã bấm Cancel | Frontend → Backend → phát lại |

### Nhóm user control
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `user_paused` | User bấm Pause | Frontend → Backend → phát lại |
| `user_resumed` | User bấm Resume | Frontend → Backend → phát lại |
| `user_stopped` | User bấm Stop | Frontend → Backend → phát lại |

### Nhóm error
| Event | Khi nào phát | Ai phát |
|---|---|---|
| `error` | Bất kỳ lỗi nào không thuộc event trên | Backend |

## 4. Chi tiết `data` cho từng event

### session_created
```json
{
  "session_id": "uuid",
  "created_at": "2026-06-18T14:32:11+07:00"
}
```

### message_received
```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "content": "Mở Notepad và gõ Hello"
}
```

### planning_started
```json
{
  "session_id": "uuid",
  "message_id": "uuid"
}
```

### planning_finished
```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "model": "qwen3:4b-q4",
  "latency_ms": 1234,
  "used_fallback": false
}
```

### workflow_created
```json
{
  "session_id": "uuid",
  "workflow_id": "uuid",
  "step_count": 2
}
```

### step_started
```json
{
  "session_id": "uuid",
  "workflow_id": "uuid",
  "step_id": "uuid",
  "step_name": "Open Notepad",
  "tool_name": "open_app",
  "order": 1
}
```

### step_completed
```json
{
  "session_id": "uuid",
  "workflow_id": "uuid",
  "step_id": "uuid",
  "duration_ms": 845
}
```

### step_failed
```json
{
  "session_id": "uuid",
  "workflow_id": "uuid",
  "step_id": "uuid",
  "error": {
    "type": "tool_error",
    "message": "App notepad không tìm thấy",
    "code": "APP_NOT_FOUND"
  }
}
```

### error  *(Phase 4)*

Phát khi Ollama / planner fail và fallback cũng không có. Backend KHÔNG
crash — chỉ phát event để UI biết.

```json
{
  "session_id": "uuid",
  "context": "planner",
  "error": {
    "type": "model_offline",
    "message": "Ollama không chạy ở localhost:11434",
    "code": "MODEL_OFFLINE"
  }
}
```

`context` có thể là `"planner"`, `"tool"`, `"runner"`, tuỳ nơi phát.

Các `code` chuẩn dùng trong event này:
- `MODEL_OFFLINE` — Ollama không reachable (Phase 4)
- `MODEL_INVALID_JSON` — model trả output không phải JSON hợp lệ
- `MODEL_UNKNOWN_TOOL` — model trả tool ngoài whitelist
- `MODEL_REPAIR_FAILED` — repair prompt cũng không sửa được
- `TOOL_NOT_FOUND` — tool name không tồn tại trong registry
- `INVALID_PARAMS` — params sai schema
- `TOOL_EXECUTION_FAILED` — tool chạy lỗi runtime

Trong MVP hiện tại, các lỗi `planner` được xử lý im lặng (fallback parser
chạy thay). Event `error` chỉ phát khi cả model lẫn fallback đều fail,
hiện tại chưa phát nhưng contract đã chốt để Phase 10 hardening.

### tool_call_started
```json
{
  "session_id": "uuid",
  "step_id": "uuid",
  "tool_name": "open_app",
  "input": { "app": "notepad" }
}
```

### tool_call_finished
```json
{
  "session_id": "uuid",
  "step_id": "uuid",
  "tool_name": "open_app",
  "status": "success",
  "output": { "pid": 1234 },
  "duration_ms": 230
}
```
`status` là `"success"` hoặc `"failed"`. Nếu `failed` thì có thêm field
`error` giống `step_failed`.

### permission_request
```json
{
  "session_id": "uuid",
  "step_id": "uuid",
  "tool_name": "type_text",
  "risk_level": "medium",
  "summary": "Type text into active window",
  "params": { "text": "Hello" }
}
```

### permission_granted
```json
{
  "session_id": "uuid",
  "step_id": "uuid",
  "tool_name": "type_text"
}
```

### permission_denied
```json
{
  "session_id": "uuid",
  "step_id": "uuid",
  "tool_name": "type_text",
  "reason": "user_cancelled"
}
```

### user_paused / user_resumed / user_stopped
```json
{
  "session_id": "uuid",
  "workflow_id": "uuid",
  "requested_at": "2026-06-18T14:35:00+07:00"
}
```

### error
```json
{
  "session_id": "uuid",
  "context": "planner",
  "error": {
    "type": "model_offline",
    "message": "Ollama không chạy ở localhost:11434",
    "code": "OLLAMA_UNREACHABLE"
  }
}
```

### session_finished
```json
{
  "session_id": "uuid",
  "workflow_id": "uuid",
  "final_status": "completed",
  "total_duration_ms": 5430
}
```
`final_status` là một trong: `completed`, `failed`, `cancelled`.

## 5. Quy tắc quan trọng

1. **Backend là nguồn phát event duy nhất**, trừ `permission_granted`,
   `permission_denied`, `user_paused`, `user_resumed`, `user_stopped` — các
   event này frontend gửi action qua WebSocket, backend echo lại cho mọi
   client đang nghe.
2. **Thứ tự event được đảm bảo trong cùng session** nhưng KHÔNG đảm bảo
   giữa các session khác nhau.
3. **Mọi event phải có `session_id`** trong `data`, kể cả event error để
   frontend biết session nào bị lỗi.
4. **Timestamp do backend sinh**, frontend không tự gắn.
5. **Không được emit event không có trong danh sách §3**. Nếu cần event
   mới, phải cập nhật file này trước.

## 6. Workflow schema (tối thiểu MVP)

Workflow MVP là tuần tự, không có branching/loop. Shape:

```json
{
  "workflow_id": "uuid",
  "session_id": "uuid",
  "created_at": "2026-06-18T14:32:11+07:00",
  "status": "pending",
  "steps": [
    {
      "id": "uuid",
      "order": 1,
      "name": "Open Notepad",
      "tool_name": "open_app",
      "params": { "app": "notepad" },
      "status": "pending"
    },
    {
      "id": "uuid",
      "order": 2,
      "name": "Type text",
      "tool_name": "type_text",
      "params": { "text": "Hello" },
      "status": "pending"
    }
  ]
}
```

### Field constraint

| Field | Type | Bắt buộc | Ghi chú |
|---|---|---|---|
| `workflow_id` | uuid v4 | có | Sinh 1 lần khi tạo workflow |
| `session_id` | uuid v4 | có | FK tới `chat_sessions.id` |
| `created_at` | ISO 8601 | có | |
| `status` | string | có | `pending`, `running`, `paused`, `completed`, `failed`, `cancelled` |
| `steps` | array | có | Tối thiểu 1 step, tối đa 20 (giới hạn MVP) |
| `steps[].id` | uuid v4 | có | |
| `steps[].order` | int >= 1 | có | Bắt đầu từ 1, tăng dần |
| `steps[].name` | string | có | Tên hiển thị cho user |
| `steps[].tool_name` | enum | có | Phải nằm trong whitelist (xem `safety_policy.md`) |
| `steps[].params` | object | có | Tùy `tool_name`, validate theo schema riêng |
| `steps[].status` | string | có | `pending`, `running`, `success`, `failed`, `skipped`, `cancelled` |

### Tool whitelist (MVP)

Chỉ những tool này được phép xuất hiện trong `tool_name`:

- `open_app` — mở app Windows theo tên
- `open_url` — mở URL trên browser
- `type_text` — gõ text vào cửa sổ active
- `hotkey` — bấm tổ hợp phím
- `press_key` — bấm 1 phím đơn
- `click_xy` — click tọa độ màn hình
- `scroll` — cuộn chuột
- `screenshot` — chụp màn hình lưu artifact
- `wait` — chờ N giây

Mọi `tool_name` ngoài danh sách phải bị backend reject ngay tại
validation, trước khi workflow được tạo.

### Param schema cho từng tool (MVP)

```json
{
  "open_app":   { "app": "string (notepad|calc|mspaint|edge|explorer)" },
  "open_url":   { "url": "string (http/https)" },
  "type_text":  { "text": "string", "method": "type|paste (default paste)" },
  "hotkey":     { "keys": ["string"] },
  "press_key":  { "key": "string" },
  "click_xy":   { "x": "int", "y": "int", "button": "left|right|middle (default left)" },
  "scroll":     { "clicks": "int", "direction": "up|down|left|right" },
  "screenshot": { "name": "string (optional)" },
  "wait":       { "seconds": "float > 0" }
}
```

## 7. Ví dụ end-to-end

User gõ "Mở Notepad và gõ Hello":

```
→ message_received
→ planning_started
→ planning_finished  (model: qwen3:4b-q4, latency_ms: 1200)
→ workflow_created    (workflow_id, step_count: 2)
→ step_started       (step 1, open_app)
  → tool_call_started
  → tool_call_finished (status: success)
→ step_completed     (step 1)
→ step_started       (step 2, type_text)
  → permission_request  (nếu bật confirm)
  → permission_granted
  → tool_call_started
  → tool_call_finished (status: success)
→ step_completed     (step 2)
→ session_finished   (final_status: completed)
```

## 8. Lịch sử thay đổi

| Ngày | Thay đổi | Ai |
|---|---|---|
| 2026-06-18 | Khởi tạo tài liệu Phase 0 | Initial |