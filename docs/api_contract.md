# API Contract — Local Desktop AI Agent

Hợp đồng REST + WebSocket giữa backend FastAPI và frontend Tauri/React.
Mọi thay đổi shape phải cập nhật file này + `docs/event_protocol.md`
trong cùng commit.

Trạng thái triển khai:
- **Phase 1 (current)**: tất cả endpoint dưới đây đã chạy và có test.
- **Phase 5**: pause/resume/stop hiện chỉ emit event echo, chưa có runner
  thật để xử lý.

## Base URL

Mặc định dev: `http://127.0.0.1:8765`. Phase 9 sẽ thêm cấu hình port
qua biến môi trường.

## Content type

Mọi request/response JSON dùng `application/json`. UUID trả về dưới dạng
string canonical (RFC 4122). Timestamp dùng ISO 8601 với timezone UTC.

## Error format

Mọi lỗi REST trả về:

```json
{ "detail": "human-readable message" }
```

Status code chuẩn:
- `400` validation error
- `404` session / workflow không tồn tại
- `422` Pydantic validation
- `501` chưa implement (Phase 5 retry)

## Endpoints

### GET /health

Liveness probe. Không phụ thuộc Ollama.

Response 200:
```json
{
  "status": "ok",
  "phase": 1,
  "service": "windagent-backend"
}
```

### GET /models/health  *(Phase 4)*

Probe model provider (Ollama hoặc Mock). Luôn trả 200 — frontend tự
kiểm tra `online`.

Response 200:
```json
{
  "provider": "ollama",
  "online": true,
  "model": "qwen3:4b-q4",
  "latency_ms": 1234,
  "error": null
}
```

Khi `online=false`:
```json
{
  "provider": "ollama",
  "online": false,
  "model": "qwen3:4b-q4",
  "latency_ms": null,
  "error": "connection refused"
}
```

Frontend dùng để hiển thị badge "Qwen ready" / "Qwen offline (fallback)".

### GET /permissions/config  *(Phase 7)*

Trả về `PermissionConfig` hiện tại.

Response 200:
```json
{
  "safe_mode": false,
  "confirm_before_type": true,
  "confirm_before_click": true,
  "type_text_length_threshold": 20,
  "request_timeout_s": 60.0
}
```

### PATCH /permissions/config  *(Phase 7)*

Cập nhật một hoặc nhiều field. Field nào không gửi thì giữ nguyên.

Body (tất cả optional):
```json
{
  "safe_mode": false,
  "confirm_before_type": true,
  "confirm_before_click": false,
  "type_text_length_threshold": 20
}
```

Response 200 = config sau update.

### POST /permissions/{request_id}/decide  *(Phase 7)*

Resolve một permission request đang chờ.

Body:
```json
{ "decision": "granted" | "denied" }
```

Response 202:
```json
{ "request_id": "uuid", "decision": "granted", "status": "resolved" }
```

Response 404 nếu request_id không tồn tại / đã resolved / đã timeout.
Response 422 nếu body sai schema.

Side effect: emit `permission_granted` hoặc `permission_denied` event
qua EventBus; runner unblock và tiếp tục (granted) hoặc skip step
(denied).

### POST /sessions

Tạo chat session mới.

Response 201:
```json
{
  "session_id": "uuid",
  "created_at": "2026-06-18T12:00:00Z",
  "status": "idle"
}
```

Side effect: phát event `session_created` qua WebSocket của session đó
nếu có client subscribe. Hiện tại service không tự emit event này; nếu
Phase 6 cần, sẽ bật lại (test cũ `test_create_session_emits_session_created`
đã cover shape).

### GET /sessions/{session_id}

Lấy thông tin session.

Response 200:
```json
{
  "id": "uuid",
  "created_at": "2026-06-18T12:00:00Z",
  "updated_at": "2026-06-18T12:00:00Z",
  "status": "idle"
}
```

Response 404 nếu session không tồn tại.

### POST /sessions/{session_id}/messages

Gửi message từ user. Backend lưu message, chạy hardcoded planner,
emit đầy đủ event planning sequence.

Body:
```json
{ "content": "Mở Notepad và gõ Hello" }
```
- `content`: string 1..4000 ký tự.

Response 202:
```json
{
  "message_id": "uuid",
  "workflow_id": "uuid",
  "step_count": 2
}
```

Response 404 nếu session không tồn tại.

Events phát theo thứ tự qua WebSocket:
1. `message_received`
2. `planning_started`
3. `planning_finished` (với `used_fallback=true`, model="fallback-rule-based")
4. `workflow_created`

### GET /sessions/{session_id}/workflow

Đọc workflow gắn với session.

Response 200: shape khớp `docs/event_protocol.md` §6
```json
{
  "workflow_id": "uuid",
  "session_id": "uuid",
  "created_at": "2026-06-18T12:00:00Z",
  "status": "pending",
  "steps": [
    {
      "id": "uuid",
      "order": 1,
      "name": "Open Notepad",
      "tool_name": "open_app",
      "params": { "app": "notepad" },
      "status": "pending"
    }
  ]
}
```

Response 404 nếu session hoặc workflow không tồn tại.

### POST /sessions/{session_id}/pause  *(Phase 5)*

Yêu cầu runner pause workflow. Workflow phải đang chạy (status ≠ finished).
Nếu workflow đã xong, trả 409.

Response 202:
```json
{ "status": "paused_requested", "workflow_id": "uuid" }
```

Response 404 nếu session không có runner.
Response 409 nếu workflow đã finished.

Event phát: `user_paused`.

### POST /sessions/{session_id}/resume  *(Phase 5)*

Resume workflow đang pause. Workflow phải đang pause.

Response 202:
```json
{ "status": "resumed_requested", "workflow_id": "uuid" }
```

Response 404/409 tương tự pause.

Event phát: `user_resumed`.

### POST /sessions/{session_id}/stop  *(Phase 5)*

Stop workflow. Workflow dừng ngay trước step tiếp theo, step hiện tại
(nếu đang chạy) vẫn chạy xong rồi mới thoát loop.

Response 202:
```json
{ "status": "stopped_requested", "workflow_id": "uuid" }
```

Event phát: `user_stopped`.

### POST /workflow/{step_id}/retry  *(Phase 5)*

Re-run workflow từ step có id này. Workflow phải đang finished.

Response 202:
```json
{
  "status": "retry_requested",
  "workflow_id": "uuid",
  "step_id": "uuid"
}
```

Response 404 nếu step_id không tồn tại hoặc session không có runner.
Response 409 nếu runner từ chối retry.

### GET /sessions/{session_id}/runner  *(Phase 5)*

Inspect in-memory state của WorkflowRunner cho session. Dùng cho frontend
để biết trạng thái control buttons.

Response 200:
```json
{
  "session_id": "uuid",
  "runner": {
    "session_id": "uuid",
    "workflow_id": "uuid",
    "paused": false,
    "stop_requested": false,
    "current_step_index": 1,
    "last_failed_step_id": null,
    "task_done": true,
    "final_status": "completed"
  }
}
```

`runner` là `null` nếu session chưa từng gửi message nào có workflow
chạy được.

## WebSocket

### WS /ws/{session_id}

Server → Client: stream event JSON xem `docs/event_protocol.md`.

Frame shape:
```json
{
  "event": "step_started",
  "timestamp": "2026-06-18T12:00:00Z",
  "data": { ... }
}
```

Quy tắc:
- Backend gửi text "ping" mỗi 20-30s nếu không có event (keepalive).
  Frontend nên bỏ qua frame này.
- Nếu session không tồn tại, server đóng socket với code `4404`.
- **Phase 5**: Client có thể gửi control message text frame:

  ```json
  {"action": "pause"}
  {"action": "resume"}
  {"action": "stop"}
  ```

  Server echo `user_paused` / `user_resumed` / `user_stopped` qua bus
  cho mọi subscriber. Nếu runner đã finished hoặc không tồn tại, server
  im lặng (không echo, không crash).
- **Phase 7**: Client cũng gửi permission decision:

  ```json
  {"action": "permission_granted", "request_id": "<uuid>"}
  {"action": "permission_denied",  "request_id": "<uuid>"}
  ```

  Server echo `permission_granted` / `permission_denied` qua bus cho
  mọi subscriber. Nếu request_id không pending thì server im lặng
  (không crash, không echo).

## Phase roadmap

| Endpoint | Phase 1 | Phase 4 |
|---|---|---|
| `GET /health` | ✓ real | unchanged |
| `GET /models/health` | — | ✓ real — Ollama / mock probe |
| `POST /sessions` | ✓ real | + reopen session cũ (Phase 2) |
| `GET /sessions/{id}` | ✓ real | |
| `POST /sessions/{id}/messages` | ✓ real + fallback parser | + Qwen3 4B qua Ollama |
| `GET /sessions/{id}/workflow` | ✓ real | |
| `POST /sessions/{id}/pause` | echo event only (Phase 1 stub) | ✓ real — runner pause |
| `POST /sessions/{id}/resume` | echo event only (Phase 1 stub) | ✓ real — runner resume |
| `POST /sessions/{id}/stop` | echo event only (Phase 1 stub) | ✓ real — runner stop |
| `POST /workflow/{step_id}/retry` | 501 (Phase 1 stub) | ✓ real — retry step |
| `GET /sessions/{id}/runner` | — | ✓ real — runner state |
| `WS /ws/{session_id}` | server→client | + client→server control |