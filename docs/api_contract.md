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

## 4. Đặc tả API Router v1.2 & OpenAI Compatible Gateway (OmniRoute Integrated)

### 4.1. Quy tắc định tuyến nâng cao (Advanced Routing Rules)

*   **Lấy danh sách quy tắc**: `GET /models/routing/rules`
    *   *Mô tả*: Trả về danh sách toàn bộ quy tắc định tuyến kèm theo các chỉ số thống kê hiệu suất thực tế trong 24h qua (tỷ lệ thành công, độ trễ, phân bổ cuộc gọi, timeline hoạt động, trạng thái health của provider).
    *   *Response (200 OK)*: Trả về danh sách đối tượng RuleDTO khớp với định dạng giao diện hiển thị.

*   **Tạo quy tắc mới**: `POST /models/routing/rules`
    *   *Request Body*: `RoutingRuleCreate` (chứa `role`, `name`, `description`, `primary_model_id`, `fallback_model_id`, `final_fallback_model_id`, `status`, `tags`, `policy`).

*   **Cập nhật quy tắc**: `PATCH /models/routing/rules/{role}`
    *   *Request Body*: `RoutingRulePatch` (cập nhật từng phần của quy tắc định tuyến).

*   **Xóa quy tắc**: `DELETE /models/routing/rules/{role}`

*   **Nhập khẩu hàng loạt**: `POST /models/routing/import`
    *   *Request Body*: `{"rules": [...]}`. Hỗ trợ bỏ qua các quy tắc lỗi, trả về thống kê số lượng thành công/thất bại kèm danh sách lỗi chi tiết.

### 4.2. Thống kê & Phân tích (Stats, Traffic & Graph)

*   **Lấy chỉ số tổng hợp**: `GET /models/routing/stats`
    *   *Mô tả*: Trả về dữ liệu cho các metric card (Total Routes, Active Rules, Fallback Chains, Avg Latency, Success Rate, Traffic Balance).

*   **Phân bổ lưu lượng**: `GET /models/routing/traffic`
    *   *Mô tả*: Lấy danh sách phân bổ phần trăm cuộc gọi tới các model LLM trong vòng 24h qua (Donut chart).

*   **Bản đồ định tuyến**: `GET /models/routing/graph`
    *   *Mô tả*: Trả về danh sách các nút và liên kết định tuyến để vẽ biểu đồ SVG kết nối giữa Agent Roles và Models.

### 4.3. Mô phỏng & Kiểm thử (Simulation & Live Test)

*   **Mô phỏng đường đi**: `POST /models/routing/simulate`
    *   *Request Body*: `{"role": "Coder", "prompt": "..."}`
    *   *Mô tả*: Chạy thử thuật toán định tuyến in-memory dựa trên chất lượng provider, quota còn lại, độ trễ và độ tương thích nghiệp vụ để đưa ra quyết định mà không gọi LLM thật.

*   **Kiểm thử thực tế**: `POST /models/routing/rules/{role}/test`
    *   *Mô tả*: Chạy thử thực tế model active của rule được chỉ định (gọi API thật), đo độ trễ và ghi log thực thi vào `router_execution_logs`.

### 4.4. Cổng kết nối chuẩn OpenAI (OpenAI Compatible Gateway)

*   **Danh sách model**: `GET /v1/models`
*   **Thực thi chat completion**: `POST /v1/chat/completions`
    *   *Mô tả*: Cổng chuyển tiếp chuẩn OpenAI. Hỗ trợ resolve trực tiếp model qua router khi truyền tham số `model` dạng `role:Planner` hoặc `auto/Planner`.

---

## 5. Tài liệu Tham chiếu (Upstream References)

Dự án này tích hợp và port các pattern lõi từ dự án upstream:
*   **Upstream Repository**: `https://github.com/diegosouzapw/OmniRoute.git`
*   **Commit SHA**: `1bda6c15dc885b645243f6cc198688ba6bb7480c`
*   **Các Pattern đã port**:
    *   OpenAI-compatible gateway routing structure.
    *   Multi-tier Fallback chain resolution logic (Primary -> Fallback -> Final Fallback).
    *   Composite suitability scoring (0.25*health + 0.20*quota + 0.20*task_fit + 0.15*cost_inverse + 0.10*latency_inverse + 0.10*context_fit).
    *   Execution logging and 24h stats/traffic/graph aggregations.
    *   In-memory routing simulation engine.
    *   Graceful partial failures handling during bulk rules imports.

---

## 6. Liên kết

- [docs/event_protocol.md](file:///d:/antigaravity_code/WindAgent/docs/event_protocol.md) — Tài liệu chi tiết về đặc tả cấu trúc JSON của từng loại WebSocket Event.
- [docs/safety_policy.md](file:///d:/antigaravity_code/WindAgent/docs/safety_policy.md) — Chính sách bảo mật và Cổng phân quyền.