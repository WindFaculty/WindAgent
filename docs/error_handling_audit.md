# Rà soát & Kiểm tra Xử lý Lỗi (Error Handling Audit)

Tài liệu này hệ thống hóa các kịch bản lỗi có thể phát sinh trong hệ thống WindAgent v1.2.0, nơi phát hiện lỗi, cách xử lý của backend, và cách hiển thị tương ứng trên giao diện người dùng.

---

## 1. Lỗi kết nối Mạng (Network & Connectivity)

| Tình huống lỗi | Nơi bắt lỗi | Cách xử lý và hiển thị trên UI |
|---|---|---|
| Backend sidecar chưa khởi động khi tải UI | `api/client.ts` bắt lỗi `fetch` bị từ chối. | Hiển thị biểu ngữ màu đỏ báo lỗi kết nối trên thanh trạng thái StatusBar. Khung chat vẫn mở nhưng không gửi được lệnh. |
| Kết nối WebSocket bị đứt giữa chừng | `api/client.ts` bắt sự kiện ngắt kết nối. | Tự động thử kết nối lại (Auto-reconnect) với cơ chế giãn cách thời gian lũy thừa (từ 1 giây đến tối đa 15 giây). |
| Kết nối lại WebSocket tới phiên làm việc (Session) không tồn tại | Server trả mã đóng kết nối `4404`. | Client đóng kết nối hoàn toàn và ghi log lỗi vào console. Người dùng cần tạo phiên làm việc mới. |
| API REST /health trả lỗi 5xx | Thư viện HTTP client của frontend nhận HTTP code. | Hiển thị thông báo `API 5xx: error` trên StatusBar đỏ. |

---

## 2. Lỗi Mô hình & Lập kế hoạch (AI Models & Planner)

| Tình huống lỗi | Nơi bắt lỗi | Cách xử lý và hiển thị trên UI |
|---|---|---|
| Ollama cục bộ chưa khởi động | `model_client.py` ném lỗi `ModelOfflineError`. | `PlannerService` kích hoạt cơ chế dịch cú pháp dự phòng dựa trên tập luật (Rule-based Fallback Parser). Nếu khớp 2 câu demo (Notepad, Edge), workflow vẫn được sinh ra và chạy bình thường. |
| Mô hình trả chuỗi văn bản thay vì JSON hợp lệ | `PlannerService` kiểm tra cú pháp JSON thất bại. | Kích hoạt cơ chế sửa JSON tự động (Repair Prompt) gửi lại Ollama 1 lần. Nếu vẫn hỏng, kích hoạt bộ dịch dự phòng. |
| Mô hình đề xuất công cụ không nằm trong whitelist | `PlannerService` kiểm tra tên công cụ. | Hủy bỏ workflow, gửi sự kiện `error` với mã lỗi `MODEL_UNKNOWN_TOOL` về frontend. UI báo lỗi workflow không hợp lệ. |
| Không tìm thấy mô hình chỉ định (ví dụ chưa pull `qwen3:4b-q4`) | `/models/health` trả về kết quả `online: true` nhưng đi kèm thông báo lỗi của Ollama. | Badge mô hình trên Header hiển thị màu đỏ báo lỗi cấu hình mô hình. |

---

## 3. Lỗi Thực thi Công cụ (Tool Execution)

| Tình huống lỗi | Nơi bắt lỗi | Cách xử lý và hiển thị trên UI |
|---|---|---|
| Sai tham số công cụ (ví dụ: mở app không nằm trong whitelist) | Pydantic validation trong `ToolExecutor` kiểm tra schema. | Hủy bước thực thi, trả lỗi `INVALID_PARAMS` kèm mô tả chi tiết tham số sai. Bước chạy trên UI chuyển thành màu đỏ (`failed`). |
| PyAutoGUI thiếu quyền kiểm soát hệ thống (Windows UAC chặn click) | `gui_adapter.py` ném ngoại lệ khi gọi hệ thống. | Ghi nhận lỗi vào audit log, trả lỗi `TOOL_EXECUTION_FAILED` về Client. Bước chạy chuyển sang `failed`. |
| Gọi công cụ định vị trực quan `click_target` khi chưa cấu hình vision | `ToolExecutor` phát hiện dịch vụ grounding ở chế độ mock stub. | Trả lỗi `VISION_STUB_MODE` hướng dẫn người dùng sử dụng click tọa độ thô `click_xy` cho phiên bản hiện tại. |
| Đường dẫn lưu ảnh chụp màn hình screenshot không ghi được | `ToolExecutor` bắt lỗi file system (Quyền hạn ổ đĩa đầy/chặn ghi). | Ghi nhận sự cố, đánh dấu bước screenshot là `failed` nhưng không làm sập tiến trình chạy của sidecar. |

---

## 4. Lỗi Cơ sở dữ liệu (Database & Persistence)

| Tình huống lỗi | Nơi bắt lỗi | Cách xử lý và hiển thị trên UI |
|---|---|---|
| File database SQLite bị khóa (database is locked) | `database.py` bắt lỗi tranh chấp ghi từ `aiosqlite`. | Ghi log cảnh báo mức ERROR. Luồng WebSocket thời gian thực vẫn chạy, dữ liệu log phiên được ghi đệm để lưu lại sau khi mở khóa. |
| Không tìm thấy Session ID lưu trong SQLite khi reload trang | API `/sessions/{id}` trả về mã HTTP 404. | Giao diện hiển thị thông báo phiên làm việc không tồn tại hoặc đã bị xóa. |
| Ổ đĩa đầy không ghi được file JSONL | `event_hooks.py` bắt lỗi ghi tệp tin. | Ghi nhận cảnh báo trong log backend. Hệ thống tiếp tục chạy bằng SQLite in-memory tạm thời. |

---

## 5. Liên kết

- [docs/e2e_test_checklist.md](file:///d:/antigaravity_code/WindAgent/docs/e2e_test_checklist.md) — Danh sách kiểm thử tích hợp E2E.
- [docs/safety_policy.md](file:///d:/antigaravity_code/WindAgent/docs/safety_policy.md) — Chính sách bảo mật và Cổng phân quyền.
