# P0.2 — MODEL DISCOVERY & MODEL CATALOG (completed)

**Gate:** `P0_2_MODEL_CATALOG_LIVE` ✅ **ACHIEVED**

**Ngày:** 2026-08-22 · Input: `docs/plans/p0_feature_truth_baseline.md`, `docs/plans/p0_1_provider_lifecycle.md`

---

## 1. P0.2.1 — Tách Sync Models khỏi Test Connection

`ProviderProbeService` (`providers/windagent_providers/management/probe.py`) được tách thành **3 operation độc lập**, không còn pipeline ngầm:

| Operation | Làm gì | Không làm gì |
| --- | --- | --- |
| `POST /providers/{id}/test-connection` | 1 network handshake thật (connectivity/auth), persist endpoint status + health sample | **Không discover models, không đăng ký binding** (receipt `model_discovery` luôn `[]`) |
| `POST /providers/{id}/sync-models` | `adapter.list_models()` thật + reconcile durable | Không đòi hỏi test-connection chạy trước |
| `POST /providers/{id}/models/test` | 1 inference nhỏ THẬT qua adapter | Không trả quality metrics nào |

Verify bằng test: sau test-connection → `EndpointModelBindingORM.count() == 0`; chỉ có đúng 1 `/models` call (health handshake).

## 2. P0.2.2 — Durable discovered registry đầy đủ metadata

**Contract mở rộng** — `DiscoveredModel` thêm `display_name`, `pricing_prompt`, `pricing_completion` (raw string từ provider). Transport `list_models()` giờ parse `name`, `context_length/context_window`, và object `pricing` kiểu OpenRouter khi provider cung cấp.

**Schema mới trên `endpoint_model_bindings`** (migration `0016_binding_discovery_metadata`, additive + idempotent):

```text
availability       active | unavailable | deprecated   (mặc định active)
pricing_class      FREE  | PAID       | UNKNOWN        (mặc định UNKNOWN)
input_price        USD/token do provider quảng bá (NULL = không công bố)
output_price       USD/token do provider quảng bá (NULL = không công bố)
currency           ví dụ USD (chỉ set khi có giá)
last_discovered_at timestamp lần sync thành công gần nhất
```

Đã kiểm chứng migration: alembic head = `0016_binding_discovery_metadata`, đủ 6 cột.

## 3. P0.2.3 — Free / Paid controls (không suy đoán)

- `classify_pricing_class()` (core): cả hai giá được quảng bá & đều = 0 → **FREE**; có giá > 0 → **PAID**; thiếu/không parse được → **UNKNOWN**. Tuyệt đối không gán FREE/PAID khi provider không trả metadata.
- Filter server-side: `GET /api/v3/models?pricing=FREE|PAID|UNKNOWN` và `GET /providers/{id}/models?pricing=...` (422 nếu giá trị lạ).
- Model-level class tổng hợp truth-tul: PAID nếu có binding nào PAID, else FREE nếu có binding FREE, else UNKNOWN.
- UI: dropdown **All Pricing / Free / Paid / Unknown** trên Models page + badge FREE/PAID trên card và trong detail modal.

## 4. P0.2.4 — Discovery reconciliation

`reconcile_discovery_snapshot(endpoint_id, models)` phân loại mỗi lần sync:

```text
ADDED       : binding mới
UPDATED     : binding tồn tại nhưng availability/equivalence/pricing đổi,
            hoặc model trước đó unavailable xuất hiện lại → active
UNCHANGED   : giống hệt kỳ trước (vẫn cập nhật last_discovered_at)
UNAVAILABLE : binding active KHÔNG thấy trong lần sync này → availability=
            'unavailable', enabled=false — KHÔNG BAO GIỜ xóa
deprecated  : reserved cho merge/manual flow, sync không tự đặt
```

Sync fail giữa chừng (network/auth) → fail-closed, **không reconcile cục phần**, receipt `ok:false` + error_code, audit `provider.discovery` ghi reason fail.

## 5. P0.2.5 — Test Model probe

`probe_model(endpoint_id, canonical_id)`: resolve binding active → `adapter.generate(ProviderRequest(messages=[...], max_output_tokens=8, temperature=0))`. Receipt: `ok, latency_ms, finish_reason, provider_model_id, message`. Fail paths: `MODEL_NOT_BOUND`, `RateLimitFailure`, … đều fail-closed kèm error_code. Test khóa điều kiện "tiny": stub assert `max_output_tokens <= 16`.

## 6. `/api/v3/models` phục vụ registry thật

Trước P0.2 endpoint này chỉ đọc namespace demo (rỗng khi profile sạch). Nay merge:

```text
GET /api/v3/models  = durable registry (mọi vendor, availability=active)  ← authority
                    ∪ demo catalog (chỉ khi WINDAGENT_PROFILE=demo)
GET /models/{id}    : tra durable trước, rồi demo ns
```

Binding payload expose đầy đủ `availability/pricing_class/prices/currency/last_discovered_at`.

## 7. Code map

| Layer | File |
| --- | --- |
| Core contracts | `capabilities.py` (DiscoveredModel + classify_pricing_class); `routing_repository.py` port (+reconcile) |
| Adapter | `openai_compatible/transport.py::list_models` (parse pricing/name/context) |
| Binding repo | `v3_routing_repositories.py::reconcile_discovery_snapshot` |
| Management repo/service | `provider_management_repository.py` (+reconcile/resolve/list_all + enrich), `service.py` (+list_all_discovered_models) |
| Probe service | `management/probe.py` — viết lại: test_connection / sync_models / probe_model + `ModelSyncResult`, `ModelProbeReceipt` |
| Routers | `providers.py` (+2 endpoints + pricing filter), `models.py` (merge + pricing filter) |
| Migration | `0016_binding_discovery_metadata.py` |
| ORM | `v3_models.py::EndpointModelBindingORM` (+6 columns) |
| FE contracts/client/hooks | `models.ts` (+pricing types/filter), `providers.ts` (+Sync/Test types), `client.ts` (+syncModels/testModel), `useProviders.ts` (+useSyncProviderModels/useTestProviderModel) |
| FE UI | `ProvidersPage` ([Sync Models]/[Sync All] + reconciliation panel), `ModelsPage` (pricing filter + badge), `ModelDetail` (Test Model per binding + receipt) |

## 8. Verification

| Suite | Kết quả |
| --- | --- |
| `tests/integration/test_p0_2_model_catalog.py` (8 test mới) | **passed** |
| Tổng backend liên quan: unit providers + P0.1 + P0.2 + phase10 | **211 passed** |
| Full `tests/contracts` (ignore phase7/phase16/code-video như baseline) | **539 passed, 31 skipped, 0 FAILED** |
| ruff toàn bộ file thay đổi | clean |
| Frontend workspaces vitest | all pass |
| Desktop type-check + build / Web typecheck + build + test | PASS / PASS |
| Migration check | head `0016`, đủ 6 cột |

Phase10 integration test được cập nhật theo semantics mới (test-connection health-only; sync là operation riêng) — worker ruleset loading, route lock, audit assertions giữ nguyên và vẫn pass.

## Gate

```text
P0_2_MODEL_CATALOG_LIVE = ACHIEVED
```

Next: **P0.3 — Routing Rules** (canonical story roles, provider→model selector thay text input, resolution order fail-closed `ROUTING_UNAVAILABLE`, fallback semantics, route receipts).
