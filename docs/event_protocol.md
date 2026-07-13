# Giao thức WebSocket & Chuỗi sự kiện (WebSocket Event Protocol)

Tài liệu này định nghĩa cấu trúc dữ liệu của các sự kiện (Events) được truyền tải thời gian thực qua kết nối WebSocket `ws://localhost:8765/ws/{session_id}` giữa FastAPI Sidecar Backend và Tauri/React Frontend.

---

## 1. Cấu trúc bao đóng sự kiện (Envelope Shape)

Tất cả các tin nhắn gửi qua WebSocket đều là đối tượng JSON chứa 3 trường bắt buộc:

```json
{
  "event": "step_started",
  "timestamp": "2026-07-03T12:00:10.123Z",
  "data": { ... }
}
```

*   `event` (string): Tên định danh của sự kiện (dạng `snake_case`).
*   `timestamp` (string): Thời gian phát sinh sự kiện theo định dạng ISO 8601 UTC.
*   `data` (object): Nội dung payload riêng của từng sự kiện cụ thể.
*   `seq` (int, Giai đoạn 7): Số thứ tự tăng đơn điệu theo session, gán khi publish (persist-before-broadcast). Client lưu `seq` cuối, reconnect bằng `/ws/{session_id}?after_seq=N` hoặc `GET /api/v1/events/{session_id}?after_seq=N` để replay event bị mất; dedupe theo `seq`.

---

## 2. Danh sách các Sự kiện hệ thống

Hệ thống hỗ trợ 18 sự kiện phân nhóm theo các pha hoạt động:

### Nhóm A: Vòng đời Phiên (Session Lifecycle)
*   `session_created`: Phát khi phiên làm việc mới được khởi tạo thành công.
*   `session_finished`: Phát khi workflow chạy kết thúc (thành công, thất bại hoặc bị hủy).

### Nhóm B: Lập kế hoạch (Planning Phase)
*   `message_received`: Ghi nhận backend đã nhận yêu cầu từ người dùng.
*   `planning_started`: Bắt đầu quá trình gọi mô hình LLM để phân tích cú pháp và lập lịch.
*   `planning_finished`: Mô hình LLM trả về danh sách các bước workflow hợp lệ.
*   `workflow_created`: Workflow đã được phân tích, xác thực và lưu vào cơ sở dữ liệu.
*   `workflow_updated`: Hermes cập nhật lại toàn bộ kế hoạch todo (thay thế danh sách cũ).

### Nhóm C: Chạy Workflow (Execution Phase)
*   `step_started`: Bắt đầu thực thi một bước trong workflow.
*   `step_completed`: Bước chạy thành công.
*   `step_failed`: Bước chạy thất bại (chứa chi tiết mã lỗi).
*   `step_cancelled`: Bước bị hủy (agent bỏ qua hoặc người dùng dừng).

### Nhóm D: Gọi công cụ tương tác (Tool Call Phase)
*   `tool_call_started`: Bắt đầu gọi một công cụ cụ thể (như gõ chữ, click chuột, chụp màn hình).
*   `tool_call_finished`: Công cụ trả kết quả thực thi và thời gian chạy.

### Nhóm E: Phân quyền (Permission Gating)
*   `permission_request`: Treo luồng và gửi yêu cầu xin quyền người dùng trên UI.
*   `permission_granted`: Người dùng đã ấn nút "Cho phép".
*   `permission_denied`: Người dùng đã ấn nút "Từ chối" hoặc tự động từ chối do hết giờ.

### Nhóm F: Điều khiển luồng (User Controls)
*   `user_paused`: Người dùng yêu cầu tạm dừng chạy.
*   `user_resumed`: Người dùng yêu cầu tiếp tục chạy.
*   `user_stopped`: Người dùng yêu cầu dừng hẳn workflow.

### Nhóm G: Tích hợp Agent-S3 (Agent-S3 Events)
*   `agent_s3_action_proposed`: Phát ra khi phân hệ Agent-S3 gửi đề xuất hành động trực quan và WindAgent hoàn tất dịch cú pháp qua AST.

### Nhóm H: Lỗi chung (Global Errors)
*   `error`: Báo lỗi hệ thống chung không thuộc các nhóm trên.

### Nhóm I: Worktree (Giai đoạn 6)
*   `worktree_created`: Tạo worktree cô lập cho coding agent thành công.
*   `worktree_changed`: Agent thay đổi nội dung worktree (optional diff).
*   `worktree_committed`: Agent tạo local commit trong worktree.
*   `worktree_merged`: Integration agent merge/cherry-pick nhánh vào main thành công.
*   `worktree_conflict`: Merge conflict — cần can thiệp người dùng.
*   `worktree_removed`: Worktree bị gỡ (quarantine hoặc xoá).

---

## 3. Đặc tả Chi tiết Payload cho từng Sự kiện

### session_created
```json
{
  "session_id": "uuid-session-id",
  "created_at": "2026-07-03T12:00:00Z"
}
```

### message_received
```json
{
  "session_id": "uuid-session-id",
  "message_id": "uuid-message-id",
  "content": "Mở Notepad và gõ Hello"
}
```

### planning_started
```json
{
  "session_id": "uuid-session-id",
  "message_id": "uuid-message-id"
}
```

### planning_finished
```json
{
  "session_id": "uuid-session-id",
  "message_id": "uuid-message-id",
  "model": "qwen3:4b-q4",
  "latency_ms": 1200,
  "used_fallback": false
}
```

### workflow_created
```json
{
  "session_id": "uuid-session-id",
  "workflow_id": "uuid-workflow-id",
  "step_count": 2
}
```

### step_started
```json
{
  "session_id": "uuid-session-id",
  "workflow_id": "uuid-workflow-id",
  "step_id": "uuid-step-id",
  "step_name": "Open Notepad",
  "tool_name": "open_app",
  "order": 1
}
```

### step_completed
```json
{
  "session_id": "uuid-session-id",
  "workflow_id": "uuid-workflow-id",
  "step_id": "uuid-step-id",
  "duration_ms": 845
}
```

### step_failed
```json
{
  "session_id": "uuid-session-id",
  "workflow_id": "uuid-workflow-id",
  "step_id": "uuid-step-id",
  "error": {
    "type": "tool_error",
    "message": "Không tìm thấy phần mềm notepad.exe",
    "code": "APP_NOT_FOUND"
  }
}
```

### tool_call_started
```json
{
  "session_id": "uuid-session-id",
  "step_id": "uuid-step-id",
  "tool_name": "open_app",
  "input": { "app": "notepad" }
}
```

### tool_call_finished
```json
{
  "session_id": "uuid-session-id",
  "step_id": "uuid-step-id",
  "tool_name": "open_app",
  "status": "success",
  "output": { "pid": 4812 },
  "duration_ms": 150
}
```

### permission_request
```json
{
  "session_id": "uuid-session-id",
  "step_id": "uuid-step-id",
  "tool_name": "type_text",
  "risk_level": "medium",
  "summary": "Nhập văn bản vào cửa sổ đang kích hoạt",
  "params": { "text": "Hello World" }
}
```

### agent_s3_action_proposed
```json
{
  "session_id": "uuid-session-id",
  "step_id": "uuid-step-id",
  "instruction": "Click vào biểu tượng Chrome",
  "translated_tool": "click_xy",
  "translated_params": { "x": 450, "y": 820, "button": "left" },
  "safety_status": "accepted",
  "rejection_code": null,
  "rejected_count": 0,
  "dry_run": false,
  "screenshot_path": "artifacts/runs/uuid/screenshots/obs_1.png"
}
```
*(Nếu `safety_status` có giá trị là `"rejected"`, các trường `translated_tool` và `translated_params` sẽ mang giá trị null và `rejection_code` sẽ chứa mã định danh nguyên nhân từ chối).*

### session_finished
```json
{
  "session_id": "uuid-session-id",
  "workflow_id": "uuid-workflow-id",
  "final_status": "completed",
  "total_duration_ms": 6500
}
```

---

## 4. Đặc tả cấu trúc chi tiết Workflow JSON

Dưới đây là cấu trúc định dạng dữ liệu đầy đủ của một Workflow được tạo và lưu trữ:

```json
{
  "workflow_id": "uuid-workflow-id",
  "session_id": "uuid-session-id",
  "created_at": "2026-07-03T12:00:05Z",
  "status": "pending",
  "steps": [
    {
      "id": "uuid-step-1",
      "order": 1,
      "name": "Mở phần mềm Notepad",
      "tool_name": "open_app",
      "params": { "app": "notepad" },
      "status": "pending"
    },
    {
      "id": "uuid-step-2",
      "order": 2,
      "name": "Nhập chuỗi văn bản",
      "tool_name": "type_text",
      "params": { "text": "Hello WindAgent", "method": "paste" },
      "status": "pending"
    }
  ]
}
```

---

## 5. Liên kết

- [docs/api_contract.md](file:///d:/antigaravity_code/WindAgent/docs/api_contract.md) — Chi tiết các endpoint HTTP REST của Sidecar.
- [docs/safety_policy.md](file:///d:/antigaravity_code/WindAgent/docs/safety_policy.md) — Phân cấp bảo mật cho các công cụ trong Whitelist.