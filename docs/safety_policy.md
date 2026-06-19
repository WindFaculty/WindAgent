# Safety Policy — Local Desktop AI Agent

Hợp đồng an toàn cho phép MVP. Phase 7 implement lớp permission gate
tối thiểu. Phase 10 hardening sẽ bổ sung.

Trạng thái triển khai:
- **Phase 7 (current)**: tool whitelist runtime + permission gate
  (config + REST + WS resolve). Tool whitelist + risk level đã có từ
  Phase 3 (`services/tool_registry.py`).
- **Phase 10**: auth cho REST/WS, rate limiting, audit log UI.

## Risk level (đã chốt Phase 3, cập nhật Phase 11)

| Risk level | Tool MVP | Yêu cầu MVP |
|---|---|---|
| safe | `screenshot`, `wait` | Không confirm |
| medium | `open_app`, `open_url`, `type_text`, `hotkey`, `press_key`, `scroll` | Configurable qua PermissionConfig |
| high | `click_xy`, `click_target` | Permission gate luôn bật; `click_xy` qua `confirm_before_click` |

> **Phase 11 update:** `scroll` đã được nâng từ `safe` lên `medium`
> trong `services/tool_registry.py` để khớp runtime behaviour (scroll
> kích hoạt mouse wheel events trên desktop user). Cập nhật `click_xy`
> + `click_target` đều là `high` (click_target thêm ở Phase 8). Tool
> whitelist giờ có **10 tool MVP**.

## Quy tắc cứng

1. **Tool whitelist cứng** — mọi tool ngoài 10 tool MVP bị reject ngay tại
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

| Tool | `requires_confirmation` | `needs_confirmation()` default | Override |
|---|---|---|---|
| `screenshot`, `wait`, `scroll`, `open_app`, `open_url`, `hotkey`, `press_key` | False | never | — |
| `type_text` | True | confirm nếu `len(text) > 20` HOẶC chứa sensitive keyword | tắt bằng `confirm_before_type=False` |
| `click_xy` | True | always confirm (khi `safe_mode=True` hoặc `confirm_before_click=True`) | tắt bằng `confirm_before_click=False` |
| `click_target` | True | always confirm (khi `safe_mode=True`) | — |

> **Phase 11 note:** runtime behaviour không đổi — `scroll` vẫn `never`
> confirm vì `requires_confirmation=False`. Việc nâng `scroll` lên
> `risk_level=medium` chỉ là metadata mô tả mức độ tác động lên desktop,
> không kích hoạt permission gate.

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

## Agent-S3 safety contract (Phase 11)

Khi `WINDAGENT_AGENT_S3_ENABLED=1`, Agent-S3 là planner phụ (additive).
Các safety guarantee bắt buộc:

1. **Raw action code KHÔNG được exec trực tiếp.** Adapter chỉ trả raw
   Python strings từ upstream LLM; runtime KHÔNG gọi `exec()` / `eval()`
   / `compile()` lên các strings đó. `agent_s3_action_translator.py`
   chỉ dùng `ast.parse(line, mode="exec")` cho shape inspection, parsed
   tree bị discard ngay.
2. **Mọi raw action phải qua translator trước khi map sang tool.**
   Translator là whitelist-based: chỉ nhận patterns đã biết (click / type /
   hotkey / press / scroll / sleep / screenshot), reject mọi thứ khác
   (import / open / subprocess / os.system / requests / urllib / socket /
   multi-line statements). Test `tests/test_agent_s3_action_translator.py`
   pin 31+ case bao gồm 11 malicious patterns.
3. **Translated action phải map vào tool whitelist** (`open_app`,
   `open_url`, `type_text`, `hotkey`, `press_key`, `click_xy`, `click_target`,
   `scroll`, `screenshot`, `wait`) rồi đi qua `ToolExecutor.execute()`.
4. **Mọi gated tool call vẫn phải qua permission gate/audit.** Translator
   output rơi vào `ToolExecutor`, nơi `PermissionService.request_permission()`
   chạy trước khi thực thi. `permission_request` / `permission_granted`
   / `permission_denied` events được mirror vào audit log (DB + JSONL).
5. **`/agent-s3/health` KHÔNG trả secret.** Scrub layer trong
   `services/agent_s3_health.py::scrub_secrets()` thay mọi key-shaped
   (`api_key` / `secret` / `token` / `password` / `bearer` /
   `authorization`) bằng boolean `*_configured`. Test
   `tests/test_agent_s3_secret_scrubbing.py` pin contract này (29 case
   bao gồm cả user-spec values `sk-tes...3456` / `ground-secret-abcdef`).
6. **`WINDAGENT_AGENT_S3_ENABLE_LOCAL_ENV` luôn bị force về 0.** Agent-S3
   local coding sandbox (exec arbitrary Python + bash) bị cấm ở config
   layer bất kể env. Nếu user set 1, config layer set False + ghi note
   vào `status.extra.notes` để debug dễ.
7. **WorkflowRunner chưa gọi `propose()`.** Agent-S3 hiện tại là **safe
   optional scaffold** — code + tests + config + health endpoint ready,
   nhưng runner không invoke adapter. Việc wire vào runner là Phase 12
   follow-up (finding `INT-001`) và phải giữ nguyên 7 guarantee trên.

Xem `docs/agent_s3_integration.md` để biết chi tiết cài đặt, env vars,
và troubleshooting.

## Liên kết

- Tool whitelist chi tiết: `docs/event_protocol.md` §6
- API endpoint chi tiết: `docs/api_contract.md`
- Event shape: `docs/event_protocol.md`