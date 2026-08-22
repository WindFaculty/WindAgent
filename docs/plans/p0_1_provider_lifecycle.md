# P0.1 — PROVIDER MANAGEMENT (completed)

**Gate:** `P0_1_PROVIDER_LIFECYCLE_LIVE` ✅ **ACHIEVED**

**Ngày:** 2026-08-22 · Baseline input: `docs/plans/p0_feature_truth_baseline.md`

---

## 1. P0.1.1 — Provider lifecycle hoàn chỉnh

Trước P0.1 chỉ có Create/Read/Test-connection. Đã bổ sung đầy đủ 8 operations của plan:

| Operation | Endpoint | Trạng thái |
| --- | --- | --- |
| Create | `POST /api/v3/providers` | có sẵn (Phase 10) |
| Read | `GET /providers`, `/providers/{id}` | có sẵn |
| **Edit** | `PATCH /api/v3/providers/{id}` | **MỚI** — name, base_url, protocol_mode, supports_* |
| **Enable / Disable** | `PATCH /api/v3/providers/{id}` `{enabled: bool}` | **MỚI** — disabled → status `offline` |
| **Credential rotate** | `PUT /api/v3/providers/{id}/credential` | **MỚI** — re-encrypt, bump `secret_version`, attach endpoint chưa có cred |
| **Credential remove** | `DELETE /api/v3/providers/{id}/credential` | **MỚI** — detach endpoints + xóa row, fail-closed về `configured: false` |
| Test connection | `POST /{id}/test-connection` | có sẵn (real probe) |
| **Delete** | `DELETE /api/v3/providers/{id}?allow_disabling_rules=` | **MỚI** — dependency check + explicit opt-in |

### Delete semantics (đúng yêu cầu plan)

```text
DELETE /providers/{id}
  ├─ còn ENABLED routing rule tham chiếu canonical model mà provider bind
  │    → HTTP 409 + blocking_rules[] (role/name/model ids) + hướng xử lý
  │      Provider KHÔNG bị xóa. Không cascade ngầm.
  └─ allow_disabling_rules=true (quyết định rõ ràng của user)
       → các rule xung đột bị DISABLE (không xóa, reversible, có audit)
       → vendor + endpoints + credentials + bindings + runtime state +
         health samples + discovery snapshots + rate windows + attempts
         bị xóa theo đúng thứ tự FK; canonical models GIỮ NGUYÊN
         (shared identity, không phải tài sản của provider)
```

Audit events mới: `provider.update`, `provider.delete` (kèm removed-row counts), `rule.disable`, `credential.rotate` (chỉ label/version — không bao giờ secret), `credential.remove`.

## 2. P0.1.2 — Credential security (giữ nguyên invariant, verify thêm)

- AES-GCM encrypted-at-rest (`enc:v1:`), key env `WINDAGENT_ENCRYPTION_KEY`, fail-closed khi thiếu key — rotate/remove đi qua cùng đường encrypt, raw key **không bao giờ** xuất hiện trong response, audit metadata, reason hay bất kỳ field nào.
- UI chỉ biết: `configured`, `credential_reference (cred:<id>)`, `label`, `secret_version`, `updated_at`.
- Test xác minh: rotate rồi probe thật qua `httpx.MockTransport` → authorization header dùng key MỚI (`Bearer new-key…`); quét toàn bộ response text + audit rows → 0 leak.

## 3. P0.1.3 — Endpoint configuration

`base_url` / `protocol_mode` (`openai|anthropic|gemini|ollama`) / credential / enabled state đều editable qua PATCH. MVP targets (OpenRouter, Google AI Studio, Groq, Ollama, custom OpenAI-compatible) đi qua protocol modes hiện có — không tạo adapter riêng.

Catalog-only (demo) providers fail-closed 404 cho mọi mutation — chỉ durable SQL authority được sửa/xóa.

## 4. Code map

| Layer | File |
| --- | --- |
| Port contract | `core/windagent_core/contracts/providers/provider_management.py` (+10 methods lifecycle) |
| SQL repo | `storage/windagent_storage/repositories/provider_management_repository.py` (update/delete/upsert_credential/remove/list_bound_canonical_ids/get_credential_summary…) |
| Service | `providers/windagent_providers/management/service.py` (`update_provider`, `delete_provider`, `rotate_credential`, `remove_credential`; errors `ProviderVendorNotFoundError`, `ProviderInUseError`) |
| Router | `apps/api/windagent_api/routers/v3/providers.py` (4 endpoints mới + schemas) |
| FE contracts | `frontend/packages/api-contracts/src/providers.ts` |
| FE client | `frontend/packages/api-client/src/client.ts` (`ProvidersApi.update/remove/rotateCredential/removeCredential`) |
| FE hooks | `frontend/app/src/features/providers/hooks/useProviders.ts` (+4 mutations) |
| FE page | `frontend/app/src/features/providers/pages/ProvidersPage.tsx` (**viết lại hoàn toàn**, không còn alias RoutingPage) |

Không cần migration mới — cột `enabled` đã tồn tại trên `provider_vendors` và `provider_endpoints`.

## 5. Frontend ProvidersPage (Target UI đạt được)

- Danh sách provider card: tên, id, status chip màu real-time (health map server), models count, enabled/disabled
- Per-endpoint: base_url, trạng thái, latency, credential configured + label, nút **Test Connection** hiển thị receipt thật (reachable/auth/latency/models discovered/error_code)
- **Add Provider** form (id, name, type, base_url, protocol_mode incl. OpenAI-compatible cho OpenRouter/Groq/custom, API key password field)
- **Edit** inline (name/base_url/protocol), **Enable/Disable** toggle, **API key** panel (rotate/remove), **Delete** với conflict flow: 409 → liệt kê blocking rules → checkbox xác nhận "disable rules & delete"
- Tất cả dữ liệu từ server authority — zero mock. Nút Sync Models thuộc P0.2 nên chưa đặt.

## 6. Verification

| Suite | Kết quả |
| --- | --- |
| `tests/integration/test_p0_1_provider_lifecycle.py` (13 test mới: edit/enable/rotate/probe-dùng-key-mới/remove/delete-blocked/delete-fallback-ref/delete-opt-in/clean-delete/HTTP lifecycle/catalog-only 404/no-leak) | **13 passed** |
| `tests/unit/providers` + phase10 integration | **203 passed** tổng |
| Full `tests/contracts` (ignore phase7 demo-dependent, phase16, code_video-drift) | **539 passed, 31 skipped, 0 FAILED** — so baseline 515+1f: không regression, tăng ~24 test do route mới vào contract-compatibility parametrization |
| ruff (toàn bộ file đổi) | clean |
| Frontend workspaces vitest | all pass |
| Desktop `tsc -b --noEmit` + `vite build` | PASS |
| Web `tsc --noEmit` + `vite build` | PASS |

Ghi chú trung thực:
- Sửa thêm lỗi typecheck có SẴN trong file orphaned `ProviderConfigPanel.tsx` (so sánh `'error'` ngoài union) để workspace build xanh lại.
- `test_phase10_production.py` khi chạy standalone có thể fail flaky (retry/cancel/plan_pins) — **pre-existing**: chứng minh bằng cách stash toàn bộ thay đổi P0.1 rồi chạy lại → vẫn fail. Trong full-suite run thì pass (thứ tự/state-dependent). Thuộc hardening sau P0, không phải regression của P0.1.
- `test_phase7_projects_and_studio` vẫn giữ ignore như baseline (phụ thuộc demo seed).

## Gate

```text
P0_1_PROVIDER_LIFECYCLE_LIVE = ACHIEVED
```

Next: **P0.2 Model Discovery & Catalog** (tách Sync Models khỏi Test Connection, expose registry lên `/api/v3/models`, reconciliation ADDED/UPDATED/UNCHANGED/UNAVAILABLE, FREE/PAID/UNKNOWN, Test Model probe).
