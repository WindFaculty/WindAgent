# Safety Policy — Local Desktop AI Agent

Hợp đồng an toàn cho phép MVP. Phase 7 implement lớp permission gate
tối thiểu. Phase 10 hardening sẽ bổ sung.

Trạng thái triển khai:
- **Phase 7 (current)**: tool whitelist runtime + permission gate
  (config + REST + WS resolve). Tool whitelist + risk level đã có từ
  Phase 3 (`services/tool_registry.py`).
- **Phase 10**: auth cho REST/WS, rate limiting, audit log UI.

## Risk level (đã chốt Phase 3)

| Risk level | Tool MVP | Yêu cầu MVP |
|---|---|---|
| safe | `screenshot`, `wait`, `scroll` | Không confirm |
| medium | `open_app`, `open_url`, `type_text`, `hotkey`, `press_key`, `click_xy` | Configurable qua PermissionConfig |
| high | `delete_file`, `shell_command`, `send_email`, `payment` | **Chưa implement ở MVP** — whitelist cứng từ chối |

## Quy tắc cứng

1. **Tool whitelist cứng** — mọi tool ngoài 9 tool MVP bị reject ngay tại
   PlannerService (`_validate` check `tool_name in _TOOL_WHITELIST`) và
   PermissionService (`get_tool()` raises `KeyError` cho unknown name).
2. **Không shell tự do** — `open_app` chỉ nhận alias thuộc
   `{"notepad", "calc", "mspaint", "edge", "explorer"}` (Pydantic
   `Literal` enforce trong `OpenAppParams`). Không có cách nào truyền
   command tự do.
3. **Mọi tool call phải ghi audit log** — Phase 2 hook mirror event
   `tool_call_started` / `tool_call_finished` vào bảng `tool_calls`.

## PermissionConfig (Phase 7 default)

```python
PermissionConfig(
    safe_mode=False,
    confirm_before_type=True,
    confirm_before_click=True,
    type_text_length_threshold=20,
    sensitive_keywords=("password", "token", "secret", "api_key", ...),
    request_timeout_s=60.0,
)
```

### Quy tắc `needs_confirmation()`

| Tool | Default (config) | Override |
|---|---|---|
| `screenshot`, `wait`, `scroll` | never | — |
| `open_app`, `open_url`, `hotkey`, `press_key` | never | — |
| `type_text` | confirm nếu `len(text) > 20` HOẶC chứa sensitive keyword | tắt bằng `confirm_before_type=False` |
| `click_xy` | always confirm | tắt bằng `confirm_before_click=False` |
| Bất kỳ tool có `requires_confirmation=True` | always confirm khi `safe_mode=True` | — |

## Permission flow (Phase 7)

```
WorkflowRunner._gate_permission(step)
   ↓
   PermissionService.needs_confirmation(tool_info, params)?
   ↓ no
   executor.execute()  (chạy tool, audit, emit events)
   ↓ yes
   PermissionService.request_permission(...)
   ↓
   emit permission_request event qua EventBus
   ↓
   block cho tới khi:
     - user bấm Confirm → REST /permissions/{id}/decide {"decision":"granted"}
                          HOẶC WS {"action":"permission_granted","request_id":"..."}
     - user bấm Cancel → tương tự với "denied"
     - timeout (60s) → auto-deny
   ↓
   if granted → executor.execute() (tiếp)
   if denied → mark step "cancelled", runner tiếp step sau (không fail workflow)
```

### API surface

- `POST /permissions/{request_id}/decide` body `{"decision": "granted"|"denied"}`
  → 202 + `permission_granted|denied` event echo
- `GET /permissions/config` → current `PermissionConfig` dict
- `PATCH /permissions/config` body `{safe_mode?, confirm_before_type?, confirm_before_click?, type_text_length_threshold?}`
  → updated config
- WebSocket `{"action": "permission_granted"|"permission_denied", "request_id": "<uuid>"}`
  → cùng effect như REST

### Audit

Mỗi decision emit event qua bus → Phase 2 hook mirror vào
`execution_events` table. Cột `event_type` sẽ là
`permission_request` / `permission_granted` / `permission_denied`,
cột `data_json` chứa full payload.

## Quy tắc bảo mật khác (post-MVP)

- Auth: hiện tại không có. MVP local-first, single user.
- Rate limit: chưa có. Phase 10.
- Audit log rotation/retention: chưa có. Phase 10.
- Encrypted secret storage: chưa cần. Phase 10.

## Liên kết

- Tool whitelist chi tiết: `docs/event_protocol.md` §6
- API endpoint chi tiết: `docs/api_contract.md`
- Event shape: `docs/event_protocol.md`