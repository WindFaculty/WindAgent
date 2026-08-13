# Chính sách Bảo mật & Phân quyền (Security & Safety Policy)

WindAgent chạy agent có khả năng tương tác với desktop/browser và gọi model
ngoài. Chính sách này mô tả cơ chế bảo mật hiện tại (Architecture V2).
Nguồn chuẩn: `core/windagent_core/security/`, `apps/api/windagent_api/routers/v2_permissions.py`.

## 1. Security primitives (`core/windagent_core/security/`)

- `types.py`:
  - `RiskLevel` — phân cấp rủi ro (enum).
  - `ApprovalRequirement` — mức phê duyệt.
  - `Permission` — quyền (action + target); `ResourceScope`, `Principal`
    (`has_permission(action, target)`).
  - `RedactedValue` — wrapper che giá trị nhạy cảm khỏi repr/str; dùng trong
    model Pydantic để không lộ secret ra log/UI.
- `redaction.py` — `redact_text`, `redact_dict`, `redact_before_persist`:
  tự động lọc API key/secret khỏi text, dict và dữ liệu trước khi persist.
- `workspace.py` — giới hạn truy cập workspace root (path sandboxing).

## 2. Permission API (`/api/v2/permissions`)

| Endpoint | Chức năng |
|---|---|
| `GET /api/v2/permissions` | Liệt kê policy hiện tại (`PermissionPolicyResponse`) |
| `POST /api/v2/permissions/evaluate` | Đánh giá yêu cầu quyền (`EvaluatePermissionRequest` → `PermissionEvaluationResponse`) |

Không còn endpoint `PATCH /permissions/config` kiểu cũ; chính sách rủi ro
theo `RiskLevel`/`ApprovalRequirement` trong code, không phải whitelist tool
cứng 11 công cụ như kiến trúc cũ (PyAutoGUI-era đã bị loại bỏ).

## 3. Quy tắc cứng

1. **Secret Scrubbing bắt buộc**: mọi giá trị nhạy cảm (API key, token, secret)
   phải qua `redact_before_persist` trước khi ghi log/DB/phản hồi client.
   Không gửi credential qua query string (ví dụ Google auth dùng header
   `x-goog-api-key`).
2. **RedactedValue cho field nhạy cảm**: field chứa secret dùng wrapper
   `RedactedValue` để repr/str không lộ giá trị.
3. **Giới hạn workspace**: tool đọc/ghi file phải resolve path trong
   workspace root đã cấu hình (`WINDAGENT_WORKSPACE_ROOT`), không cho escape
   (xem `core/windagent_core/security/workspace.py`).
4. **Không chạy shell tự do từ prompt model**: tool shell/subprocess đi qua
   lớp sandbox và policy của `tools/windagent_tools`; không có tool "chạy
   lệnh tùy ý" phơi ra model không kiểm soát.
5. **Audit**: event `permission.request` / `permission.granted` /
   `permission.denied` được phát qua event bus (xem `docs/event_protocol.md`).

## 4. Chính sách chi tiết theo subsystem

Chi tiết theo từng lĩnh vực nằm trong `docs/video_production/security/`
(threat model, browser profile/secret policy, action confirmation, network/file
boundaries, privacy retention, audit & redaction) và `docs/video_production/browser_runtime/`.

## Liên kết

- [docs/event_protocol.md](event_protocol.md)
- [docs/api_contract.md](api_contract.md)
