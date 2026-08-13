# Event Protocol (Architecture V2)

Tài liệu này định nghĩa envelope và danh mục sự kiện (event catalog) của
WindAgent Architecture V2. Nguồn chuẩn duy nhất là code:

- Envelope: `core/windagent_core/events/envelope.py` (`EventEnvelope`, Pydantic v2)
- Catalog: `core/windagent_core/events/catalog.py` và các module mở rộng
  (`studio.py`, `video_production.py`, `video_production_ir.py`, `script_asset_events.py`)
- Giao vận: `apps/api/windagent_api/routers/v2_events.py`

## 1. EventEnvelope (shape bắt buộc)

Mọi sự kiện phát ra trong hệ thống đều là `EventEnvelope` với các trường:

| Field | Kiểu | Ghi chú |
|---|---|---|
| `event_id` | `EventId` (UUID) | Sinh khi publish |
| `event_type` | `str` | Taxonomy dạng dotted: `task.created`, `studio.screenplay.locked` |
| `schema_version` | `int` | Mặc định `1`; bump khi thay đổi schema phá vỡ tương thích |
| `stream_id` | `str \| None` | Stream/session để sắp xếp tuần tự |
| `aggregate_id` | `str \| None` | Aggregate nguồn phát sinh sự kiện |
| `aggregate_type` | `str \| None` | Loại aggregate |
| `sequence` | `int` | Tăng đơn điệu theo stream; dùng cho dedupe và replay |
| `occurred_at` | `datetime` | Thời điểm xảy ra (UTC) |
| `recorded_at` | `datetime \| None` | Thời điểm persist (nếu có) |
| `session_id` | `SessionId \| None` | Session liên quan |
| `correlation_id` | `str \| None` | Chuỗi correlation xuyên suốt request |
| `causation_id` | `EventId \| None` | Event gây ra event này |
| `trace_id` | `str \| None` | Trace context |
| `payload` | `dict` | Nội dung nghiệp vụ riêng của event |
| `metadata` | `dict` | Metadata bổ sung |

Envelope có `to_dict()` / `from_dict()` để persist và truyền qua wire.
`event_type` và `sequence` được validate khi khởi tạo (`field_validator`).

## 2. Giao vận (transports)

| Transport | Đường dẫn | Ghi chú |
|---|---|---|
| WebSocket | `WS /api/v2/events/ws` | Streaming realtime; dùng `EventEnvelope` |
| SSE | `GET /api/v2/events/stream` | Server-sent events |
| JSON | `GET /api/v2/events` | Liệt kê lịch sử event |

`seq` (trong envelope là `sequence`) tăng đơn điệu theo stream; client có thể
replay sau reconnect bằng cách đọc lại từ `sequence` cuối đã nhận và dedupe
theo `event_id`.

Router legacy `GET /api/v2/video-production/events` (`v2_events_legacy_router`)
vẫn tồn tại cho tương thích với production events; không dùng cho event mới.

## 3. Danh mục sự kiện (catalog)

Tên sự kiện dùng taxonomy dotted, không dùng tên flat kiểu `step_started`.
Các nhóm chính trong `catalog.py`:

### Session & Conversation
`session.created`, `session.started`, `session.finished`, `session.paused`,
`session.resumed`, `session.stopped`, `session.message_received`,
`session.assistant_started`, `session.assistant_delta`, `session.assistant_completed`

### Task, Workflow, Step
`task.created`, `task.started`, `task.completed`, `task.failed`, `task.cancelled`
`workflow.created`, `workflow.started`, `workflow.updated`, `workflow.completed`,
`workflow.failed`, `workflow.cancelled`
`step.started`, `step.completed`, `step.failed`, `step.cancelled`

### Planning
`planning.started`, `planning.finished`, `planning.replan`, `planning.clarification_request`

### Tool & Model
`tool.proposed`, `tool.started`, `tool.progress`, `tool.finished`, `tool.error`
`model.request_started`, `model.response_delta`, `model.response_completed`,
`model.reasoning_delta`

### Provider
`provider.error`, `provider.status_changed`

### Browser
`browser.session_started`, `browser.action_started`, `browser.action_completed`,
`browser.nav_started`, `browser.nav_completed`, `browser.screenshot_updated`,
`browser.console`, `browser.error`

### Permission
`permission.request`, `permission.granted`, `permission.denied`

### Recovery & Verification
`recovery.started`, `recovery.completed`
`verification.started`, `verification.completed`, `verification.failed`

### Worktree
`worktree.created`, `worktree.changed`, `worktree.committed`, `worktree.merged`,
`worktree.conflict`, `worktree.removed`

### System
`system.error`, `system.heartbeat`, `system.terminal_output`, `artifact.created`

### Studio (`events/studio.py`)
`studio.series.created`, `studio.episode.created`, `studio.episode.ready_for_production`,
`studio.idea.candidates_generated`, `studio.idea.selected`,
`studio.story.review_completed`, `studio.story.revision_requested`,
`studio.screenplay.locked`, `studio.revision.derived`,
`studio.artifact.created`, `studio.approval.requested`, `studio.approval.recorded`,
`studio.task.submitted`, `studio.task.completed`,
`studio.run.started`, `studio.run.completed`, `studio.run.failed`, `studio.run.cancelled`

### Video production (`events/video_production.py`, `video_production_ir.py`)
Event riêng của production pipeline (director, shots, engine jobs, asset,
audio, postproduction) — xem module tương ứng; đây là nguồn chuẩn, không
duplicate danh sách ở đây.

## 4. Quy ước phát hành event

- Persist trước khi broadcast (durable sequence) khi có storage gắn với stream.
- Không phát event có tên nằm ngoài catalog.
- Payload không chứa secret; dùng `core/windagent_core/security/redaction.py`
  trước khi ghi log/persist.

## Liên kết

- [docs/api_contract.md](api_contract.md) — HTTP REST, SSE, WebSocket endpoints
