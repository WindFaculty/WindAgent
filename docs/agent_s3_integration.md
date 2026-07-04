# Hướng dẫn Tích hợp & Cấu hình Agent-S3 (Agent-S3 Integration Guide)

Phân hệ **Agent-S3** là một bộ lập kế hoạch bổ sung (optional planner) dựa trên thư viện [Agent-S](https://github.com/simular-ai/Agent-S) của Simular AI, giúp WindAgent v1.2.0 có khả năng tự động hóa giao diện trực quan thông qua phân tích ảnh chụp màn hình desktop (screen-grounded planning).

---

## 1. Trạng thái tích hợp hiện tại (Phase 12)

*   **Bộ nạp cấu hình (Config Loader)**: Đọc các cài đặt cấu hình từ biến môi trường và kiểm tra tính hợp lệ trước khi khởi chạy hệ thống.
*   **Adapter liên kết**: Hỗ trợ nạp động (lazy import) thư viện SDK chính thức của Simular AI, giúp tránh lỗi import khi người dùng không kích hoạt phân hệ này.
*   **Bộ dịch hành động (Action Translator)**: Lọc và dịch các hành động sinh ra bởi Agent-S thành công cụ của WindAgent, đảm bảo không thực thi các câu lệnh nguy hiểm (chặn `exec`/`eval`/`import`/`subprocess`).
*   **Wired into WorkflowRunner**: Công cụ `agent_s3_step` đã được tích hợp đầy đủ vào runner. Mỗi bước `agent_s3_step` sẽ thực hiện quy trình: Chụp màn hình -> Gửi lên Agent-S3 đề xuất -> Dịch hành động -> Xin xác nhận quyền người dùng -> Thực thi hành động an toàn trên màn hình Windows.

---

## 2. Hướng dẫn cài đặt (Installation Modes)

Phân hệ này mặc định bị **vô hiệu hóa** (`WINDAGENT_AGENT_S3_ENABLED=0`). Để kích hoạt, trước tiên bạn cần cài đặt dependency theo một trong hai chế độ:

### Chế độ A: Cài đặt dạng thư viện (Package Mode - Khuyến nghị)
Cài đặt trực tiếp gói `gui-agents` phiên bản `0.3.2` từ PyPI vào môi trường ảo của dự án:
```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\setup_agent_s3.ps1 -Mode package
```

### Chế độ B: Cài đặt dạng mã nguồn ngoài (External Mode)
Tải mã nguồn dự án Agent-S trực tiếp từ GitHub vào thư mục `external/Agent-S/` và liên kết đường dẫn hệ thống:
```powershell
cd D:\antigaravity_code\WindAgent
powershell -ExecutionPolicy Bypass -File scripts\setup_agent_s3.ps1 -Mode external
```

---

## 3. Cấu hình biến môi trường (Environment Variables)

Thiết lập các biến môi trường sau để kích hoạt và cấu hình Agent-S3:

| Tên biến | Bắt buộc | Giá trị ví dụ | Ý nghĩa |
|---|---|---|---|
| `WINDAGENT_AGENT_S3_ENABLED` | Có | `1` | Kích hoạt phân hệ Agent-S3 (`1` để bật, `0` để tắt). |
| `WINDAGENT_AGENT_S3_SOURCE` | Không | `package` | Nguồn nạp: `package` hoặc `external`. |
| `WINDAGENT_AGENT_S3_EXTERNAL_PATH` | Chỉ khi chọn external | `external/Agent-S` | Đường dẫn thư mục mã nguồn Agent-S. |
| `WINDAGENT_AGENT_S3_PROVIDER` | Có | `openai` | Nhà cung cấp AI chính (ví dụ: `openai`, `anthropic`, v.v.). |
| `WINDAGENT_AGENT_S3_MODEL` | Có | `gpt-5-2025-08-07` | Tên mô hình AI chính dùng cho Agent-S3. |
| `WINDAGENT_AGENT_S3_MODEL_API_KEY` | Có | `sk-proj-...` | API Key cho mô hình chính (sẽ được tự động lọc bỏ khỏi response). |
| `WINDAGENT_AGENT_S3_GROUND_PROVIDER`| Có | `huggingface` | Nhà cung cấp mô hình định vị trực quan (Grounding LLM). |
| `WINDAGENT_AGENT_S3_GROUND_MODEL` | Có | `ui-tars-1.5-7b` | Tên mô hình định vị trực quan. |
| `WINDAGENT_AGENT_S3_GROUND_API_KEY` | Có | `hf_...` | API Key cho mô hình định vị trực quan. |

---

## 4. Công cụ `agent_s3_step` (Tool Specification)

Đây là công cụ cấp độ **High-Risk**, luôn yêu cầu quyền xác nhận của người dùng.

### Định dạng tham số đầu vào (JSON Schema)
```json
{
  "instruction": "Click vào nút Đăng nhập trên màn hình",
  "screenshot": true,
  "dry_run": false,
  "max_retries": 0,
  "require_permission": true,
  "timeout_ms": 30000
}
```

### Quy trình thực thi tuần tự
1.  **Chụp quan sát (Observation)**: Chụp màn hình nền nếu `screenshot=true`.
2.  **Đề xuất hành động (Propose)**: Gửi chỉ thị `instruction` cùng ảnh chụp màn hình tới SDK Agent-S3 để lấy câu lệnh hành động thô (ví dụ: `pyautogui.click(100, 200)`).
3.  **Dịch cú pháp (Translate)**: Chạy qua bộ dịch tĩnh AST để loại bỏ các đoạn mã độc hại và trích xuất tham số.
4.  **Kiểm tra an toàn bổ sung**: Đối chiếu công cụ dịch ra với danh sách cho phép của Agent-S3 (`click_xy`, `type_text`, `hotkey`, `press_key`, `scroll`, `wait`, `screenshot`).
5.  **Xin quyền hạn (Permission)**: Gửi yêu cầu phê duyệt thông qua Cổng phân quyền. Nếu được cho phép, chuyển hành động xuống tầng `ToolExecutor` của WindAgent để tương tác trực tiếp lên màn hình.

---

## 5. Bảng mã lỗi xử lý (Error Codes)

Khi bước chạy `agent_s3_step` thất bại, hệ thống sẽ trả về một trong các mã lỗi chuẩn sau:

| Mã lỗi | Nguyên nhân |
|---|---|
| `AGENT_S3_DISABLED` | Phân hệ Agent-S3 chưa được bật hoặc chưa liên kết thành công. |
| `AGENT_S3_ADAPTER_NOT_READY` | Khởi tạo SDK Agent-S3 thất bại do lỗi thư viện hoặc kết nối mạng. |
| `AGENT_S3_UNAVAILABLE` | Cấu hình bị thiếu hoặc môi trường chạy thiếu thư viện liên quan. |
| `AGENT_S3_PROPOSE_FAILED` | Gọi mô hình chính của Agent-S3 bị lỗi hoặc timeout. |
| `AGENT_S3_UNSAFE_ACTION` | Hành động sinh ra chứa mã độc (như câu lệnh `import`, `subprocess`, `os.system`). |
| `AGENT_S3_UNSUPPORTED_ACTION` | Hành động sinh ra không được hỗ trợ dịch ngược về whitelist. |
| `MAPPED_TOOL_NOT_WHITELISTED` | Công cụ sau khi dịch nằm ngoài danh sách công cụ cho phép. |
| `MAPPED_TOOL_INVALID_PARAMS` | Tham số công cụ sau khi dịch sai kiểu dữ liệu hoặc không vượt qua bộ kiểm tra Pydantic. |
| `MAPPED_TOOL_EXECUTION_FAILED` | Lỗi phát sinh trong quá trình điều khiển thiết bị thực tế (ví dụ: chuột bị kẹt tọa độ). |

---

## 6. Liên kết

- [docs/safety_policy.md](file:///d:/antigaravity_code/WindAgent/docs/safety_policy.md) — Quy tắc an toàn và kiểm tra AST chi tiết.
- [docs/api_contract.md](file:///d:/antigaravity_code/WindAgent/docs/api_contract.md) — Hợp đồng API sức khỏe `/agent-s3/health`.