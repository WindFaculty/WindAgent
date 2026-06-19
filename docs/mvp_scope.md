# MVP Scope — Local Desktop AI Computer-Use Agent

Tài liệu này là nguồn tham chiếu duy nhất định nghĩa MVP. Mọi phase sau
phải bám theo scope đã chốt ở đây. Nếu cần mở rộng, phải cập nhật file này
trước rồi mới triển khai.

## 1. MVP là gì

MVP chỉ cần chứng minh được **vòng lặp cốt lõi** end-to-end trên máy
Windows local-first:

```
User gõ lệnh tự nhiên
  → Qwen3 4B (qua Ollama) lập workflow đơn giản
  → Backend validate workflow
  → Executor chạy từng bước trên Windows bằng PyAutoGUI
  → UI stream tiến trình realtime qua WebSocket
  → User có thể Stop / Pause / Resume giữa chừng
  → Mọi sự kiện được lưu vào SQLite + log file
```

Không có thành phần nào trong vòng lặp được phép chỉ là mock khi release.

## 2. Demo bắt buộc

### Demo 1 — Notepad

User gõ:
```
Mở Notepad và gõ Hello from local AI agent.
```

Planner phải tạo workflow 2 step:
1. `open_app` với `app=notepad`
2. `type_text` với `text="Hello from local AI agent."`

Executor phải:
- mở `notepad.exe` thật
- focus vào cửa sổ Notepad
- gõ đúng nội dung
- stream event `step_started` → `step_completed` cho từng step

### Demo 2 — Edge mở URL

User gõ:
```
Mở trang google.com trên Edge.
```

Planner phải tạo workflow 2 step:
1. `open_app` với `app=edge`
2. `open_url` với `url="https://google.com"`

Executor phải mở Microsoft Edge và navigate tới URL.

## 3. MVP KHÔNG làm gì

Các hạng mục dưới đây được **chính thức defer** sang post-MVP. Tuyệt đối
không đưa vào code trong các phase 0–10:

- GUI-Actor vision thật (Qwen2.5-VL)
- Playwright / browser automation nâng cao
- Model manager UI đầy đủ (chỉ cần pull Ollama bằng tay)
- Workflow drag/drop editor
- Plugin system / sandbox
- Multi-agent collaboration
- Auto-update
- Context 64k, vLLM, llama.cpp nâng cao
- Streaming text generation từ planner (chỉ cần final JSON)
- Voice I/O
- Cloud fallback mặc định

## 4. Acceptance criteria tổng thể

MVP được xem là đạt khi **đồng thời** pass tất cả tiêu chí:

### Core agent loop
- [ ] User nhập lệnh tự nhiên từ UI
- [ ] Planner Qwen3 4B local trả về workflow JSON hợp lệ
- [ ] Workflow được validate trước khi chạy
- [ ] Workflow chạy tuần tự, không song song
- [ ] Step status stream realtime qua WebSocket

### Desktop control
- [ ] Mở Notepad được
- [ ] Gõ text tiếng Việt có dấu được (qua clipboard fallback)
- [ ] Mở Edge với URL được
- [ ] Screenshot artifact được lưu vào `artifacts/runs/{session_id}/screenshots/`

### User control
- [ ] Stop hủy workflow trước step kế tiếp
- [ ] Pause dừng trước step tiếp theo (không kill app)
- [ ] Resume tiếp tục đúng vị trí pause
- [ ] Retry chạy lại step failed
- [ ] Lỗi không làm app crash

### Local-first
- [ ] Backend chạy local (FastAPI sidecar)
- [ ] SQLite lưu local
- [ ] Qwen chạy qua Ollama local
- [ ] Không gọi bất kỳ API cloud nào khi user không bật

### Safety
- [ ] Tool whitelist reject mọi tool ngoài danh sách
- [ ] Không có API chạy shell tự do
- [ ] Permission event hoạt động cho medium-risk tools
- [ ] Audit log lưu mọi tool call

### Persistence
- [ ] Session, message, workflow, step, tool call, event đều lưu DB
- [ ] Restart backend vẫn thấy lịch sử session cũ

### Dev experience
- [ ] `scripts/dev_backend.ps1` chạy được backend 1 lệnh
- [ ] `scripts/dev_desktop.ps1` chạy được desktop 1 lệnh
- [ ] `scripts/healthcheck.ps1` phát hiện thiếu dependency
- [ ] README root hướng dẫn chạy từ máy sạch

## 5. Rủi ro kỹ thuật đã biết

| Rủi ro | Tác động | Mitigation MVP |
|---|---|---|
| Ollama offline khi demo | Planner fail | Health check + fallback rule-based parser cho 2 demo |
| Qwen trả JSON sai | Workflow invalid | Validate schema + repair prompt 1 lần + reject rõ ràng |
| PyAutoGUI mất focus | `type_text` gõ sai chỗ | Active window check + retry 1 lần |
| Tiếng Việt có dấu | `pyautogui.write` lỗi unicode | Fallback `pyperclip.copy` + `Ctrl+V` |
| WebSocket disconnect | UI mất event | Auto-reconnect + replay event từ DB |
| SQLite lock khi concurrent | Workflow runner block | Single writer thread + WAL mode |
| Edge khởi động chậm | step `open_url` fail | `wait` tool + retry policy |
| Screen DPI scaling | `click_xy` lệch tọa độ | MVP chỉ demo app mở bằng tên, defer click_xy chính xác |
| User bấm Stop lúc tool đang chạy | Tool không clean up | Acknowledgement async, tool vẫn chạy nốt rồi mới nhận stop |

## 6. Nguyên tắc khi triển khai

1. **Vertical slice trước**: ưu tiên chạy được demo 1 Notepad hơn là build
   kiến trúc đẹp.
2. **Hardcode tạm được**: hardcoded parser cho 2 demo là chấp nhận được
   trong phase đầu, miễn là có interface rõ để thay sau.
3. **Không over-engineer**: không thêm plugin system, multi-agent, hay
   config phức tạp khi chưa cần.
4. **Event là hợp đồng**: mọi thay đổi giao tiếp frontend-backend phải cập
   nhật `docs/event_protocol.md` và `docs/api_contract.md`.
5. **Local-first tuyệt đối**: không có network call ngoài Ollama local.

## 7. Liên kết tài liệu liên quan

- `docs/event_protocol.md` — định nghĩa event WebSocket stream
- `docs/api_contract.md` — REST + WebSocket API
- `docs/safety_policy.md` — tool whitelist + risk level
- `ban_ke_hoach.md` — bản kế hoạch tổng (file gốc)