# Danh sách Kiểm thử tích hợp E2E (E2E Manual Test Checklist)

Đây là tài liệu kiểm thử thủ công chính thức trước mỗi đợt phát hành phiên bản WindAgent v1.2.0. Người kiểm thử cần chạy tuần tự các bước dưới đây trên máy Windows để đảm bảo tính ổn định của hệ thống.

---

## 1. Kiểm tra môi trường & Khởi chạy hệ thống

### 1.1. Healthcheck Môi trường
- [ ] Chạy lệnh kiểm tra môi trường:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\healthcheck.ps1
  ```
- [ ] Xác nhận kết quả: Toàn bộ mục đánh dấu `[CRIT]` phải trả về trạng thái **PASS**.

### 1.2. Khởi chạy Sidecar Backend (Mock Mode)
- [ ] Chạy khởi động backend:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1
  ```
- [ ] Đọc log tại `artifacts/logs/backend.log` và xác nhận xuất hiện dòng:
  *   `using MockModelClient`
  *   `backend ready — db=...`
- [ ] Gửi request tới `http://127.0.0.1:8765/health` và nhận về JSON status: `"ok"`.

### 1.3. Khởi chạy Giao diện Frontend (Vite)
- [ ] Mở terminal mới và chạy:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\dev_desktop.ps1
  ```
- [ ] Mở trình duyệt tại địa chỉ `http://localhost:5173`. Xác nhận giao diện hiển thị biểu tượng **WindAgent** và các chỉ số CPU/RAM/GPU bắt đầu nhảy số ở Header.

---

## 2. Kiểm thử Tương tác Giao diện (10 Phân hệ)

### 2.1. Phân hệ Dashboard (Bảng điều khiển)
- [ ] Xác nhận các biểu đồ nhỏ ở Header (CPU, RAM, GPU, VRAM) cập nhật liên tục mỗi 2 giây.
- [ ] Kiểm tra phần **System Health**: Các chỉ số CPU, RAM, GPU, VRAM, Disk, Network hiển thị dấu tích xanh lá.
- [ ] Kiểm tra danh sách **Active Agents**: Renders đầy đủ trạng thái các Agent (Planner, GUI Agent, Coder, Researcher).
- [ ] Kiểm tra **Timeline Logs** và **Task Queue** hiển thị đúng dữ liệu giả lập/thực tế.

### 2.2. Phân hệ Agent Workspace (Không gian làm việc)
- [ ] Vào phân hệ **Agent Workspace**. Nhập câu lệnh `"Mở Notepad và gõ Hello"` vào khung chat và ấn **Gửi**.
- [ ] Xác nhận luồng chạy bắt đầu:
  *   Danh sách checklist tin nhắn Agent tự động nhảy trạng thái `pending -> running -> success`.
  *   Khung log **Terminal** in ra các dòng lệnh git clone, npm install, pytest giả lập.
  *   Cột bên phải hiển thị mục tiêu hiện tại (Current Goal) và tiến độ nhảy lên `72%` rồi `100%`.
  *   Thống kê công cụ đang dùng (Tools in Use) hiển thị chấm xanh lá nhấp nháy cho `File System`, `Terminal`, `Code Analyzer`.

### 2.3. Phân hệ Router (Điều phối mô hình)
- [ ] Vào phân hệ **Router**. Chọn dòng `Planner → Local Chat` trong bảng luật định tuyến.
- [ ] Xác nhận cột bên phải hiển thị đầy đủ thông số của luật định tuyến đó (Route ID, Tags, Usage Rate, Latency).
- [ ] Xác nhận biểu đồ đường tròn **Traffic Distribution** và sơ đồ **Routing Graph** vẽ các kết nối overlay nối từ Agent qua Router Core tới các Model đích.
- [ ] Trình mô phỏng **Route Simulation** hiển thị đúng quy trình từ User Request -> Planner -> Router -> Primary Model.

### 2.4. Phân hệ Agents (Thư mục Agent)
- [ ] Vào phân hệ **Agents**. Xác nhận danh sách hiển thị đầy đủ 6 Agent chuyên biệt.
- [ ] Click thử vào nút cấu hình cấu hình hoặc xem chi tiết của một Agent bất kỳ để xem mô tả.

### 2.5. Phân hệ Workflows (Quy trình)
- [ ] Vào phân hệ **Workflows**.
- [ ] Xác nhận danh sách hiển thị lịch sử chạy của các workflow trước đó từ SQLite.
- [ ] Click vào một dòng workflow để mở rộng danh sách các bước con và xem trạng thái của từng bước.

### 2.6. Phân hệ Browser & Files & Memory
- [ ] Mở phân hệ **Browser**: Trình address bar hiển thị URL và khung web hiển thị mockup giao diện.
- [ ] Mở phân hệ **Files**: Hiển thị danh sách cây thư mục cục bộ của dự án.
- [ ] Mở phân hệ **Memory**: Thử gõ câu hỏi vào ô tìm kiếm ngữ cảnh dài hạn và xác nhận sơ đồ nút mạng Vector hiển thị.

### 2.7. Phân hệ Models (Quản lý mô hình)
- [ ] Vào phân hệ **Models**. Xác nhận trạng thái online/offline của Ollama được cập nhật.
- [ ] Click thử nút "Pull" hoặc đổi nhà cung cấp AI để xem giao diện phản hồi.

### 2.8. Phân hệ Settings (Cài đặt)
- [ ] Vào phân hệ **Settings**. Bật/Tắt nút gạt **Safe Mode**.
- [ ] Thêm một từ khóa nhạy cảm mới vào danh sách cảnh báo, ấn Save và xác nhận cấu hình được cập nhật thành công (bằng cách kiểm tra cấu hình trả về qua API `/permissions/config`).

---

## 3. Kiểm thử Cổng phân quyền & Các lệnh dừng (Pause/Resume/Stop)

### 3.1. Phê duyệt phân quyền (Permission Gate)
- [ ] Bật cấu hình `WINDAGENT_PERMISSION_CONFIRM_BEFORE_TYPE=1` trong file env hoặc bật Safe Mode trên UI.
- [ ] Gửi lệnh gõ văn bản dài hơn 20 ký tự qua Workspace.
- [ ] Xác nhận xuất hiện **Permission Dialog** xin phép chạy `type_text`.
- [ ] Thử chọn **Cancel** (Từ chối): Xác nhận bước chạy đó bị hủy (`cancelled`), luồng workflow không bị lỗi mà bỏ qua bước này để chạy tiếp.
- [ ] Thử chọn **Allow** (Cho phép): Xác nhận công cụ thực thi bình thường.

### 3.2. Lệnh tạm dừng & Dừng hẳn (Pause/Resume/Stop)
- [ ] Gửi một câu lệnh dài (nhiều bước hoặc có bước chờ lâu như `wait seconds=5`).
- [ ] Trong lúc workflow đang chạy, ấn nút **Pause** trên giao diện: Xác nhận workflow tạm ngừng ngay khi bước hiện tại chạy xong.
- [ ] Ấn nút **Resume**: Xác nhận workflow tiếp tục chạy từ bước đang tạm dừng.
- [ ] Ấn nút **Stop**: Toàn bộ các bước còn lại trong danh sách bị chuyển thành `cancelled`, phiên làm việc chuyển trạng thái thành `cancelled`.

---

## 4. Kiểm thử Khôi phục & Tắt hệ thống

- [ ] **Kiểm tra tắt nóng**: Ấn `Ctrl+C` tại terminal chạy Backend sidecar. Xác nhận toàn bộ tiến trình uvicorn dừng ngay lập tức, không bị treo luồng ngầm.
- [ ] **Kiểm tra khôi phục**: Khởi động lại backend sidecar. Tải lại trang frontend `http://localhost:5173` và xác nhận toàn bộ lịch sử trò chuyện cùng các phiên cũ hiển thị đầy đủ (được nạp lại thành công từ file SQLite `windagent.db`).
