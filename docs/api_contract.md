# Hợp đồng REST API & Giao tiếp Sidecar (REST API Contract)

Tài liệu này đặc tả toàn bộ các API HTTP REST và kết nối WebSocket được cung cấp bởi **FastAPI Sidecar Backend** để tương tác với **Tauri/React Frontend**.

---

## 1. Nguyên tắc thiết kế chung

*   **Base URL**: Mặc định chạy cục bộ ở địa chỉ `http://127.0.0.1:8765`.
*   **Định dạng dữ liệu**: Mọi Request và Response đều sử dụng định dạng JSON (`application/json`).
*   **Kiểu dữ liệu đặc biệt**:
    *   Các trường ID sử dụng định dạng chuỗi UUID v4 chuẩn (RFC 4122).
    *   Thời gian (Timestamp) sử dụng định dạng chuỗi ISO 8601 (múi giờ UTC, kết thúc bằng chữ `Z`).
*   **Định dạng lỗi**: Khi gặp lỗi hệ thống, API phản hồi mã trạng thái HTTP (400, 404, 422, 500, v.v.) đi kèm body JSON dạng:
    ```json
    { "detail": "Thông tin chi tiết về lỗi phát sinh" }
    ```

---

## 2. Đặc tả các Endpoint HTTP REST

### Liveness Probe (Kiểm tra trạng thái hệ thống)
*   **Phương thức**: `GET`
*   **Đường dẫn**: `/health`
*   **Mô tả**: Kiểm tra nhanh xem sidecar backend có đang chạy và phản hồi hay không.
*   **Response (200 OK)**:
    ```json
    {
      "status": "ok",
      "service": "windagent-backend",
      "agent_s3": {
        "mode": "disabled",
        "enabled": false,
        "package_available": true,
        "external_repo_available": false,
        "config_missing_count": 0
      }
    }
    ```

### Agent-S3 Health (Trạng thái chi tiết phân hệ Agent-S3)
*   **Phương thức**: `GET`
*   **Đường dẫn**: `/agent-s3/health`
*   **Mô tả**: Lấy trạng thái cấu hình và tích hợp của Agent-S3. Đi kèm cơ chế **Secret Scrubbing** bảo vệ API Key.
*   **Response (200 OK)**:
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

### Models Health (Trạng thái mô hình Ollama)
*   **Phương thức**: `GET`
*   **Đường dẫn**: `/models/health`
*   **Mô tả**: Kiểm tra kết nối tới dịch vụ Ollama cục bộ.
*   **Response (200 OK)**:
    ```json
    {
      "provider": "ollama",
      "online": true,
      "model": "qwen3:4b-q4",
      "latency_ms": 250,
      "error": null
    }
    ```

### Quản lý danh sách mô hình (Model Registry)
*   **Lấy danh sách các Model**: `GET /models`
    *   *Mô tả*: Trả về danh sách tất cả các mô hình được đăng ký (cục bộ hoặc API) kèm theo trạng thái runtime và cấu hình quota.
    *   *Response (200 OK)*:
        ```json
        [
          {
            "id": "google_gemini_2.5_flash",
            "name": "Gemini 2.5 Flash",
            "provider": "Google AI Studio",
            "providerId": "google_ai_studio",
            "apiSource": "google",
            "modelId": "gemini-2.5-flash",
            "baseUrl": "https://generativelanguage.googleapis.com",
            "type": "API",
            "billingMode": "RPM_RPD",
            "context": "1048K",
            "status": "Ready",
            "hasKey": true,
            "roles": "GUI Agent, Planner",
            "rt": "320ms",
            "sr": "100%",
            "sparkPoints": "0,15 15,18 30,12 45,16 60,6 68,10",
            "description": "Google's fast multimodal model...",
            "deployment": "Cloud API",
            "quantization": null,
            "vram": "—",
            "vramVal": "—",
            "vramMax": "—",
            "vramPct": 0,
            "ramVal": "—",
            "ramMax": "—",
            "ramPct": 0,
            "contextVal": "0",
            "contextMax": "1048K",
            "contextPct": 0,
            "tokensPerSec": "72.5",
            "uptime": "30d",
            "assignedRoles": [{"name": "GUI Agent", "type": "Candidate"}],
            "tags": ["Fast", "Multimodal", "Free Tier"],
            "capabilities": ["chat", "vision", "tool_use", "long_context"],
            "quota": {
              "mode": "RPM_RPD",
              "rpmLimit": 15,
              "rpdLimit": 1500,
              "tpmLimit": 1000000,
              "remainingRequestsToday": 1490,
              "remainingTokensToday": 980000,
              "remainingCredit": null,
              "resetAt": "2026-07-03T14:00:00Z",
              "source": "provider_api"
            }
          }
        ]
        ```

*   **Thêm cấu hình Model**: `POST /models`
    *   *Request Body*:
        ```json
        {
          "name": "Gemini 2.5 Flash",
          "provider_id": "google_ai_studio",
          "model_id": "gemini-2.5-flash",
          "type": "API",
          "capabilities": ["chat", "vision"],
          "tags": ["Cloud"],
          "roles": ["Planner"]
        }
        ```
    *   *Response (200 OK)*:
        ```json
        { "id": "google_ai_studio_gemini-2.5-flash", "display_name": "Gemini 2.5 Flash" }
        ```

*   **Nhập/Tải Model local**: `POST /models/import`
    *   *Request Body*:
        ```json
        { "source": "ollama", "model_name": "qwen3.5:4b-q4" }
        ```
    *   *Response (200 OK)*:
        ```json
        { "status": "queued", "model_name": "qwen3.5:4b-q4", "message": "Import job has been queued successfully." }
        ```

*   **Điều khiển model**: `POST /models/{model_id}/start` | `POST /models/{model_id}/stop` | `POST /models/{model_id}/restart`
    *   *Response (200 OK)*:
        ```json
        { "status": "started", "model_id": "google_gemini_2.5_flash" }
        ```

*   **Lấy quy tắc định tuyến**: `GET /models/routing`
    *   *Response (200 OK)*:
        ```json
        {
          "Planner": { "primary": "google_gemini_2.5_flash", "fallback": "openrouter_free" },
          "Coder": { "primary": "mistral_codestral", "fallback": "qwen_coder_free" }
        }
        ```

*   **Cập nhật quy tắc định tuyến**: `PATCH /models/routing`
    *   *Request Body*:
        ```json
        {
          "Planner": { "primary": "google_gemini_2.5_flash_lite", "fallback": "openrouter_free" }
        }
        ```
    *   *Response (200 OK)*:
        ```json
        { "status": "success", "message": "Routing rules updated successfully." }
        ```

*   **Lấy log hoạt động model**: `GET /models/{model_id}/logs`
    *   *Response (200 OK)*:
        ```json
        [
          { "time": "10:21 AM", "message": "Probe complete: health=Healthy, latency=320ms" }
        ]
        ```

*   **Xem so sánh hiệu năng (Benchmarks)**: `GET /models/benchmarks`
*   **Chạy Benchmark**: `POST /models/benchmarks/run`
    *   *Request Body*:
        ```json
        { "model_ids": ["google_gemini_2.5_flash"], "test_name": "smoke", "prompt": "Say OK in one sentence.", "max_tokens": 16 }
        ```
    *   *Response (200 OK)*:
        ```json
        { "results": [{ "model_id": "google_gemini_2.5_flash", "success": true, "latency_ms": 320 }] }
        ```

*   **Lấy danh sách hoạt động gần đây**: `GET /models/activity`
*   **Danh sách cấu hình Provider**: `GET /models/providers`
*   **Đồng bộ hóa model của Provider**: `POST /models/providers/{provider_id}/sync`
*   **Lấy thông tin Quota của Provider**: `GET /models/providers/{provider_id}/quota`
*   **Chạy kiểm tra liên kết (Probe Model)**: `POST /models/{model_id}/probe`

### Cấu hình Cổng phân quyền (Permission Settings)
*   **Đọc cấu hình**: `GET /permissions/config`
    *   **Response (200 OK)**:
        ```json
        {
          "safe_mode": false,
          "confirm_before_type": true,
          "confirm_before_click": true,
          "type_text_length_threshold": 20,
          "request_timeout_s": 60.0
        }
        ```
*   **Cập nhật cấu hình**: `PATCH /permissions/config`
    *   **Request Body** (tất cả các trường là tùy chọn):
        ```json
        {
          "safe_mode": true,
          "confirm_before_click": false
        }
        ```
    *   **Response (200 OK)**: Trả về đối tượng cấu hình đầy đủ sau khi đã cập nhật thành công.

### Phản hồi yêu cầu phê duyệt (Permission Decision)
*   **Phương thức**: `POST`
*   **Đường dẫn**: `/permissions/{request_id}/decide`
*   **Mô tả**: Frontend gửi quyết định phê duyệt hoặc từ chối thực thi một công cụ bị treo bởi Permission Gate.
*   **Request Body**:
    ```json
    { "decision": "granted" }
    ```
    *(Các giá trị được chấp nhận: `"granted"`, `"denied"`)*
*   **Response (202 Accepted)**:
    ```json
    {
      "request_id": "uuid-request-id",
      "decision": "granted",
      "status": "resolved"
    }
    ```

### Quản lý phiên làm việc (Chat Sessions)
*   **Tạo Session mới**: `POST /sessions`
    *   **Response (201 Created)**:
        ```json
        {
          "session_id": "uuid-session-id",
          "created_at": "2026-07-03T12:00:00Z",
          "status": "idle"
        }
        ```
*   **Lấy chi tiết Session**: `GET /sessions/{session_id}`
    *   **Response (200 OK)**: Trả về thông tin thời gian khởi tạo, cập nhật, và trạng thái hiện tại (`idle`, `running`, `paused`, `completed`, `failed`, `cancelled`).

### Gửi tin nhắn & Lập kế hoạch (Send Message)
*   **Phương thức**: `POST`
*   **Đường dẫn**: `/sessions/{session_id}/messages`
*   **Mô tả**: User gửi tin nhắn yêu cầu tự động hóa. Backend sẽ tạo luồng planning và sinh ra workflow.
*   **Request Body**:
    ```json
    { "content": "Mở ứng dụng Calculator trên màn hình" }
    ```
*   **Response (202 Accepted)**:
    ```json
    {
      "message_id": "uuid-message-id",
      "workflow_id": "uuid-workflow-id",
      "step_count": 1
    }
    ```

### Đọc thông tin Workflow
*   **Phương thức**: `GET`
*   **Đường dẫn**: `/sessions/{session_id}/workflow`
*   **Response (200 OK)**:
    ```json
    {
      "workflow_id": "uuid-workflow-id",
      "session_id": "uuid-session-id",
      "created_at": "2026-07-03T12:00:05Z",
      "status": "pending",
      "steps": [
        {
          "id": "uuid-step-id",
          "order": 1,
          "name": "Open Calculator",
          "tool_name": "open_app",
          "params": { "app": "calc" },
          "status": "pending"
        }
      ]
    }
    ```

### Điều khiển Workflow Runner (Pause / Resume / Stop / Retry)
*   **Pause (Tạm dừng)**: `POST /sessions/{session_id}/pause`
    *   *Trả về*: `{"status": "paused_requested", "workflow_id": "uuid"}` (Mã 202)
*   **Resume (Tiếp tục)**: `POST /sessions/{session_id}/resume`
    *   *Trả về*: `{"status": "resumed_requested", "workflow_id": "uuid"}` (Mã 202)
*   **Stop (Dừng lại)**: `POST /sessions/{session_id}/stop`
    *   *Trả về*: `{"status": "stopped_requested", "workflow_id": "uuid"}` (Mã 202)
*   **Retry (Chạy lại từ bước lỗi)**: `POST /workflow/{step_id}/retry`
    *   *Trả về*: `{"status": "retry_requested", "workflow_id": "uuid", "step_id": "uuid"}` (Mã 202)

### Kiểm tra trạng thái máy chạy (Runner State)
*   **Phương thức**: `GET`
*   **Đường dẫn**: `/sessions/{session_id}/runner`
*   **Mô tả**: Xem thông số hoạt động in-memory của WorkflowRunner để cập nhật trạng thái các nút bấm điều khiển trên UI.
*   **Response (200 OK)**:
    ```json
    {
      "session_id": "uuid-session-id",
      "runner": {
        "session_id": "uuid-session-id",
        "workflow_id": "uuid-workflow-id",
        "paused": false,
        "stop_requested": false,
        "current_step_index": 0,
        "last_failed_step_id": null,
        "task_done": false,
        "final_status": "running"
      }
    }
    ```

---

## 3. Giao tiếp Thời gian thực qua WebSocket

Hệ thống cung cấp kênh WebSocket để stream toàn bộ các trạng thái chạy và cho phép gửi lệnh phản hồi nhanh.

*   **Endpoint**: `ws://localhost:8765/ws/{session_id}`
*   **Luồng gửi tin nhắn từ Client -> Server**:
    Client có thể gửi các JSON text frame để thực hiện hành động nhanh thay vì gọi API REST:
    *   Tạm dừng: `{"action": "pause"}`
    *   Tiếp tục: `{"action": "resume"}`
    *   Dừng hẳn: `{"action": "stop"}`
    *   Cho phép cấp quyền: `{"action": "permission_granted", "request_id": "<uuid>"}`
    *   Từ chối cấp quyền: `{"action": "permission_denied", "request_id": "<uuid>"}`

---

## 4. Liên kết

- [docs/event_protocol.md](file:///d:/antigaravity_code/WindAgent/docs/event_protocol.md) — Tài liệu chi tiết về đặc tả cấu trúc JSON của từng loại WebSocket Event.
- [docs/safety_policy.md](file:///d:/antigaravity_code/WindAgent/docs/safety_policy.md) — Chính sách bảo mật và Cổng phân quyền.