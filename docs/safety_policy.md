# Chính sách Bảo mật & Phân quyền (Security & Safety Policy)

Bảo mật là yếu tố quan trọng hàng đầu trong WindAgent. Do ứng dụng AI để điều khiển trực tiếp hệ điều hành desktop thực tế của người dùng, hệ thống triển khai một cơ chế bảo mật nhiều lớp (defense-in-depth) nhằm đảm bảo AI luôn hoạt động trong phạm vi cho phép và không thực thi các hành vi gây hại.

---

## 1. Phân cấp mức độ rủi ro công cụ (Risk Tiers)

Các công cụ được phân thành 3 cấp độ rủi ro trong `services/tool_registry.py`:

| Cấp độ | Công cụ | Quy định phê duyệt |
|---|---|---|
| **Safe (An toàn)** | `screenshot`, `wait` | Tự động chạy, không cần người dùng xác nhận. |
| **Medium (Trung bình)** | `open_app`, `open_url`, `type_text`, `hotkey`, `press_key`, `scroll` | Mặc định tự động chạy trừ khi bật **Safe Mode** hoặc các điều kiện đặc biệt. |
| **High (Nguy hiểm)** | `click_xy`, `click_target`, `agent_s3_step` | Luôn yêu cầu phê duyệt từ người dùng thông qua Cổng phân quyền (Permission Gate). |

*Lưu ý về `type_text`:* Công cụ này được coi là rủi ro trung bình, nhưng sẽ tự động kích hoạt yêu cầu phê duyệt nếu:
1. Độ dài đoạn văn bản vượt quá ngưỡng cấu hình (mặc định 20 ký tự).
2. Văn bản chứa các từ khóa nhạy cảm (ví dụ: `password`, `token`, `secret`, `api_key`, v.v.).

---

## 2. Quy tắc bảo mật cứng (Hard Rules)

1.  **Whitelist công cụ cố định**: Hệ thống chỉ nhận diện và chạy đúng 11 công cụ đã được khai báo sẵn. Mọi công cụ lạ do LLM sinh ra ngoài whitelist này đều bị PlannerService hoặc PermissionService từ chối ngay lập tức.
2.  **Không cho phép chạy Shell tự do**: Không cung cấp bất kỳ công cụ nào để thực thi câu lệnh Command Line tự do (như `bash`, `cmd`, `powershell`).
3.  **Giới hạn mở ứng dụng**: Công cụ `open_app` chỉ chấp nhận danh sách ứng dụng cụ thể: `{"notepad", "calc", "mspaint", "edge", "explorer"}`. Mọi tên phần mềm khác đều bị Pydantic validator chặn lại.
4.  **Bắt buộc ghi Audit Log**: Mọi cuộc gọi công cụ (tool call) đều phải ghi nhận trạng thái vào bảng `tool_calls` (SQLite) và lưu trữ dưới dạng file nhật ký phiên `artifacts/runs/{session_id}/events.jsonl`.
5.  **Bảo vệ thông tin bí mật (Secret Scrubbing)**: Hệ thống tự động lọc bỏ các giá trị API Key của OpenAI, Anthropic, hay HuggingFace ra khỏi các API phản hồi về Client để tránh rò rỉ dữ liệu qua màn hình UI hoặc logs.

---

## 3. Cổng phân quyền (Permission Gate Flow)

Khi một bước trong workflow cần được phê duyệt (dựa trên cấu hình `PermissionConfig`):

```
[WorkflowRunner] Chạy tới bước cần quyền hạn
       ↓
[PermissionService] Xác định công cụ cần xin quyền người dùng
       ↓
[EventBus] Phát sự kiện `permission_request` thời gian thực
       ↓
[FastAPI Backend] Treo luồng thực thi (Block) và lắng nghe phản hồi
       ↓
[User Interface] Hiển thị Dialog thông báo xin quyền (nút Cho phép / Từ chối)
       ↓
[User phản hồi]
  ├─> Chọn Grant (Cho phép) -> Gửi API/WS quyết định -> Tiếp tục thực thi tool
  ├─> Chọn Deny (Từ chối)   -> Hủy bước hiện tại, đánh dấu "cancelled" -> Chạy tiếp các bước sau
  └─> Hết giờ (Timeout 60s) -> Tự động từ chối (Auto-deny) nhằm bảo vệ hệ thống
```

Cấu hình phân quyền có thể thay đổi động qua API `PATCH /permissions/config` bao gồm:
*   `safe_mode`: Nếu bật `True`, toàn bộ công cụ Medium và High đều yêu cầu xác nhận.
*   `confirm_before_type`: Bật/Tắt chế độ xác nhận khi gõ văn bản.
*   `confirm_before_click`: Bật/Tắt chế độ xác nhận khi click chuột qua tọa độ.
*   `type_text_length_threshold`: Điều chỉnh ngưỡng độ dài ký tự tối đa trước khi xin quyền.

---

## 4. Rào cản bảo mật cho Agent-S3 (Agent-S3 Safety Guarantees)

Khi tích hợp tác vụ Agent-S3 để tự động hóa màn hình trực quan, hệ thống áp dụng các nguyên tắc phòng vệ nghiêm ngặt:

1.  **Không thực thi mã thô (No Raw Exec)**: Agent-S3 có thể sinh ra các đoạn mã Python để mô tả hành động. WindAgent **tuyệt đối không** sử dụng `eval()`, `exec()`, hay `compile()` để chạy các đoạn mã này.
2.  **Bộ biên dịch an toàn bằng AST (AST-based Translation)**: Sử dụng thư viện `ast` của Python để phân tích cú pháp tĩnh đoạn mã đề xuất. Nếu phát hiện các câu lệnh lạ (như `import`, `subprocess`, `os.system`, `requests`, v.v.), hành động đó sẽ bị đánh dấu `rejected` với mã lỗi `AGENT_S3_UNSAFE_ACTION` và bị hủy bỏ ngay lập tức.
3.  **Ánh xạ ngược về Whitelist**: Các câu lệnh PyAutoGUI hợp lệ (như `pyautogui.click`, `pyautogui.write`) sẽ được dịch ngược về các công cụ trong Whitelist của WindAgent (ví dụ: `click_xy`, `type_text`) để xử lý.
4.  **Bảo vệ chống vòng lặp vô hạn (Bounded Loop)**: Mỗi bước chạy `agent_s3_step` chỉ được phép đề xuất và chạy đúng 1 hành động đơn lẻ. Cơ chế vòng lặp tự trị đa bước (multi-step loops) bị giới hạn để tránh Agent tự ý click chuột vô hạn mà không có sự kiểm soát của con người.
5.  **Trạng thái đã nghỉ hưu**: Adapter Agent-S3 không còn nằm trong runtime Architecture V2; mọi lần tái giới thiệu phải đi qua canonical execution và permission contracts.

---

## 5. Liên kết

- [docs/mvp_scope.md](file:///d:/antigaravity_code/WindAgent/docs/mvp_scope.md) — Tổng quan kiến trúc hệ thống.
- [docs/agent_s3_integration.md](file:///d:/antigaravity_code/WindAgent/docs/agent_s3_integration.md) — Đặc tả tích hợp và cấu hình Agent-S3.
- [docs/api_contract.md](file:///d:/antigaravity_code/WindAgent/docs/api_contract.md) — Chi tiết các endpoint điều khiển phân quyền.
