# Asset Resolver Contract (VP3D Phase 5)

Authority: `docs/video_production/3d_animation_plans/stage_c_asset_production.md` Phase 5 + `road_map.md` §405-444.

## 1. Mục đích

`AssetResolverPort` là gateway DUY NHẤT cho mọi nhu cầu 3D asset: local library, Internet, Mesh API, Mesh MCP và future generator. Director/Scene Compiler KHÔNG gọi provider trực tiếp; mọi kênh trả về cùng ngữ nghĩa qua DTO trung lập provider.

## 2. Surface contract

```text
core/windagent_core/contracts/video_production/asset_resolver.py
    AssetResolverPort (Protocol, runtime_checkable)
        async discover(request) -> AssetResolutionResult      # DISCOVERED candidates
        async acquire(candidate, request) -> AssetResolutionResult  # content-addressed asset
        capabilities() -> list[AssetProviderCapability]
```

DTO (core domain `asset_resolution/`): `AssetRequirement`, `AssetCandidate`, `AssetResolutionRequest`, `AssetResolutionResult`, `AssetResolutionAttempt`, `AssetProviderCapability`, `AssetBudget`.

## 3. Bất biến bắt buộc

1. **Capability matching trước call** — adapter không đáp ứng requirement bị loại bằng typed rejection (`CapabilityRejectedError`); provider không được gọi khi không thể phục vụ.
2. **Idempotency** — key = `sha256(canonical requirement + adapter_id + adapter_version)`; lookup cache TRƯỚC network/generation; version adapter khác KHÔNG reuse cache cũ.
3. **Discover ≠ Acquire** — `AssetCandidate` chỉ là kết quả `DISCOVERED`, chưa bao giờ là asset được phép dùng; chỉ `acquire` tạo `ReferenceAsset` content-addressed kèm `AssetAcquisitionRecord`.
4. **Fail-closed** — provider chưa cấu hình → typed rejection (`ASSET_CAPABILITY_REJECTED` / `ASSET_PROVIDER_UNAVAILABLE` / `ASSET_GENERATION_NOT_ENABLED`); không partial result, không asset giả.
5. **Không credential** — request/candidate/receipt không chứa credential; config chỉ giữ secret REFERENCE (`env:VAR`); `SecretLeakError` nếu giá trị dạng secret lọt vào payload.
6. **Execution envelope** — timeout, retry budget, circuit breaker (CLOSED/OPEN/HALF_OPEN), cooperative cancellation, per-provider concurrency semaphore áp dụng cho mọi call.

## 4. Typed rejections (chung cho mọi adapter)

| Error | Code | Retryable | Ý nghĩa |
|---|---|---|---|
| `CapabilityRejectedError` | `ASSET_CAPABILITY_REJECTED` | no | Provider không đáp ứng requirement |
| `NoCapableAdapterError` | `ASSET_NO_CAPABLE_ADAPTER` | no | Không adapter nào khớp |
| `ProviderUnavailableError` | `ASSET_PROVIDER_UNAVAILABLE` | yes | Chưa cấu hình transport/backend |
| `ProviderTimeoutError` | `ASSET_PROVIDER_TIMEOUT` | yes | Quá timeout |
| `ProviderExecutionError` | `ASSET_PROVIDER_EXECUTION` | yes | Lỗi không phân loại (retry) |
| `CircuitOpenError` | `ASSET_CIRCUIT_OPEN` | yes | Breaker đang OPEN |
| `RetryBudgetExhaustedError` | `ASSET_RETRY_BUDGET_EXHAUSTED` | no | Hết budget retry |
| `ResolutionCancelledError` | `ASSET_RESOLUTION_CANCELLED` | no | Hủy giữa chừng |
| `GenerationNotEnabledError` | `ASSET_GENERATION_NOT_ENABLED` | no | Generator chưa bật |
| `SecretLeakError` | `ASSET_SECRET_LEAK` | no | Credential lọt payload |

## 5. Adapter registry & composition

- `AssetAdapterRegistry`: đăng ký theo `adapter_id` ổn định; trùng id là configuration error.
- Adapters nằm trong `providers/windagent_providers/assets/`; shared download/validation tiếp tục ở `tools/windagent_tools/media_assets/` và được INJECT vào `InternetAssetAdapter` qua structural ports tại composition root (providers chỉ phụ thuộc `windagent_core`).
- Mesh API/MCP: config chỉ chứa `base_url` + `api_key_ref`/`client_ref` (reference, không raw); transport resolve reference lúc call.
- `FutureGeneratorAdapter`: slot cho generation tương lai; chưa có backend → typed rejection.

## 6. Status semantics

`AssetResolutionStatus`: `DISCOVERED` (tìm thấy, chưa acquire), `RESOLVED` (đã acquire thành asset), `NOT_FOUND`, `REJECTED`, `TIMEOUT`, `CANCELLED`, `FAILED`.

## 7. Kiểm thử

- `tests/unit/core/test_phase5_asset_requirement.py` — canonical fields/hash/cache key/status.
- `tests/unit/providers/test_phase5_asset_gateway.py` — matching, cache hit/miss, discover/acquire, timeout, retry, circuit breaker, cancellation, concurrency, redaction, real adapters.
- `tests/contracts/asset_adapter_contract.py` + `test_asset_adapter_contract_suite.py` — contract chung cho MỌI adapter (fake + real).
- `tests/architecture/test_phase5_asset_gateway_architecture.py` — core không import providers/tools; providers/assets chỉ import core; port không lộ SDK/transport/credential.

## 8. Phạm vi Phase 6 (chưa thuộc Phase 5)

- Mở rộng `AssetSourceType`/`LicenseState` đầy đủ (Phase 5 đã bổ sung `LOCAL_LIBRARY`).
- QUARANTINED/APPROVED lifecycle bắt buộc, lineage conversion, signed-URL redaction trong receipt.
