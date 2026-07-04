# Tài liệu phát hành WindAgent v1.2.0 (Release Notes)

*   **Phiên bản**: v1.2.0
*   **Ngày phát hành**: 03/07/2026
*   **Trạng thái**: Bản phát hành chính thức (Stable Release) — Tích hợp thành công Agent-S3 và Hệ thống Giao diện Phân hệ Mới.

---

## 1. Các Tính năng mới nổi bật

### 1.1. Tích hợp phân hệ Agent-S3 (Phase 12)
*   **Wired Agent-S3**: Hỗ trợ tích hợp SDK chính thức của Simular AI làm bộ lập kế hoạch trực quan phụ trợ.
*   **Công cụ `agent_s3_step`**: Bổ sung công cụ High-Risk cho phép Agent tự chụp ảnh màn hình và đề xuất các click/type/scroll trực quan.
*   **AST Safety Boundary**: Hệ biên dịch tĩnh AST lọc các câu lệnh Python độc hại thô trước khi dịch thành công cụ trong Whitelist.
*   **Secret Scrubbing**: Tự động ẩn các API Key của nhà cung cấp mô hình AI trong mọi API phản hồi về giao diện.

### 1.2. Hệ thống Giao diện Phân hệ Mới (Tauri + React + Vite)
Giao diện đã được nâng cấp lên v1.2.0 với thiết kế hiện đại, mượt mà và trực quan hóa dữ liệu phong phú:
*   **Dashboard**: Theo dõi lịch sử sử dụng phần cứng, quản lý hàng đợi tác vụ, biểu đồ phân bổ mô hình và dòng nhật ký timeline thời gian thực.
*   **Router Console**: Cấu hình phân bổ lưu lượng cuộc gọi AI, thiết lập chuỗi dự phòng Fallback khi mô hình lỗi, sơ đồ định tuyến Routing Graph trực quan, và trình giả lập chạy thử Route Simulation.
*   **Agent Workspace**: Không gian làm việc đa nhiệm tích hợp luồng Chat, log Terminal chạy lệnh chi tiết, trình duyệt web mô phỏng Browser, chỉ số công cụ đang dùng và mức tiêu thụ token bộ nhớ.
*   **Memory Manager**: Quản lý bộ nhớ ngữ cảnh dài hạn dạng Vector DB, vẽ sơ đồ nút mạng liên kết bộ nhớ.
*   **Models Config**: Trình quản lý kết nối Ollama/Cloud models, hỗ trợ tải trực tiếp model bằng nút bấm trên giao diện.
*   **Settings**: Bật tắt safe mode, điều khiển cổng phân quyền, quản lý từ khóa nhạy cảm.

### 1.3. Lớp Dữ liệu Bền vững & Điều khiển chạy
*   Lưu trữ bền vững SQLite toàn bộ dữ liệu phiên, tin nhắn, workflow, các bước chạy và lịch sử cuộc gọi công cụ.
*   Log sự kiện kép: Đồng thời ghi vào SQLite và xuất tệp tin `events.jsonl` độc lập cho mỗi session chạy.
*   Nâng cấp Workflow Runner hỗ trợ đầy đủ các lệnh dừng nóng `Pause`, tiếp tục `Resume`, dừng hẳn `Stop`, và chạy lại từ bước lỗi `Retry`.

---

## 2. Kết quả Kiểm thử & Độ bao phủ (Test Coverage)

Bản build v1.2.0 đã vượt qua toàn bộ các bài kiểm thử tự động của hệ thống:

*   **338 bài kiểm thử Backend FastAPI** (`pytest`) vượt qua thành công:
    - Kiểm thử REST API endpoints và kết nối thời gian thực WebSocket.
    - Kiểm thử lưu trữ SQLite bền vững và ghi log phiên JSONL.
    - Kiểm thử thuật toán phân tích cú pháp AST của Translator Agent-S3.
    - Kiểm thử máy trạng thái WorkflowRunner điều khiển dừng luồng.
    - Kiểm thử Cổng phân quyền Permission Gating.
*   **19 bài kiểm thử Frontend React** (`vitest`) vượt qua thành công.
*   `tsc --noEmit` kiểm tra kiểu dữ liệu TypeScript sạch lỗi.

---

## 3. Các Lỗi đã biết (Known Issues) & Cách khắc phục

1.  **Lỗi build Tauri không có Rust**: Lệnh `tauri build` yêu cầu cài đặt Rust toolchain. Nếu máy của bạn không cài Rust, vui lòng sử dụng `npm run dev` để chạy giao diện trực tiếp trên trình duyệt ở địa chỉ `http://localhost:5173`.
2.  **PyAutoGUI yêu cầu phiên màn hình desktop thực tế**: Nếu chạy backend dưới dạng service chạy ngầm của Windows (Windows Service), các công cụ tương tác chuột click/type sẽ lỗi do không có giao diện hiển thị. Vui lòng chạy backend bằng cửa sổ PowerShell thông thường.
3.  **Hao phí ổ đĩa cho log sự kiện**: Thư mục `artifacts/runs/` lưu trữ các file `events.jsonl` và ảnh chụp màn hình screenshot. Các tệp tin này chưa có cơ chế tự động dọn dẹp theo thời gian, người quản trị cần dọn dẹp thủ công nếu ổ đĩa bị đầy.

---

## 4. Lộ trình phát triển tiếp theo (Phase 13+)

*   **Multi-step Autonomous Agent-S3 Loop**: Cho phép Agent-S3 tự động đề xuất nhiều hành động liên tiếp trong một vòng lặp kín có giới hạn số lần tối đa, thay vì chỉ chạy 1 hành động duy nhất mỗi bước như hiện tại.
*   **Visual Proposed Timeline**: Tích hợp hiển thị ảnh đề xuất trực quan và sơ đồ khoanh vùng click chuột của Agent-S3 ngay trên giao diện Workspace Chat Timeline.
*   **Tích hợp định vị Vision nâng cao**: Tận dụng Agent-S3 để định vị chính xác tọa độ các nút bấm trên ứng dụng trước khi thực thi lệnh click.

---

## 5. Liên kết

- [docs/mvp_scope.md](file:///d:/antigaravity_code/WindAgent/docs/mvp_scope.md) — Tổng quan kiến trúc hệ thống.
- [docs/api_contract.md](file:///d:/antigaravity_code/WindAgent/docs/api_contract.md) — Tài liệu đặc tả API REST.
- [docs/event_protocol.md](file:///d:/antigaravity_code/WindAgent/docs/event_protocol.md) — Tài liệu đặc tả giao thức WebSocket.
