# Phase 05 — Universal Asset Gateway (Stage C)

## Kết quả

`AssetResolverPort` là gateway duy nhất cho mọi nhu cầu 3D asset. Director không gọi Internet/Mesh trực tiếp: mọi kênh (local library, Internet, Mesh API, Mesh MCP, future generator) trả về cùng ngữ nghĩa qua DTO trung lập provider, capability matching trước mọi provider call, idempotency bằng canonical requirement + adapter/version, discover tách khỏi acquire, execution envelope (timeout/retry/circuit breaker/cancellation/per-provider concurrency), credential không bao giờ vào request/receipt.

## Backlog Phase 5 — trạng thái

1. **Chuẩn hóa loại asset, style, topology, rig, texture resolution, license constraint, budget** — DONE: `AssetKind`/`AssetStyle`/`TopologyPolicy`/`RigRequirement`/`LicenseConstraint`/`TextureResolution` + `AssetBudget` (polygon/texture/file/VRAM defaults).
2. **Capability matching trước khi gọi adapter; typed rejection** — DONE: `CapabilityMatcher`; `CapabilityRejectedError`/`NoCapableAdapterError`/`ProviderUnavailableError`/`GenerationNotEnabledError`; unconfigured providers bị rejection TRƯỚC call (test chứng minh provider không được gọi).
3. **Idempotency theo canonical requirement + adapter/version; lookup cache trước network/generation** — DONE: `AssetRequirement.canonical_hash` + `cache_key`; `AssetResolutionCache` (bounded LRU); cache hit/miss + version-isolation + provider-not-recalled tests.
4. **Tách discover khỏi acquire** — DONE: `AssetCandidate` chỉ `DISCOVERED`; chỉ `acquire` tạo `ReferenceAsset` + `AssetAcquisitionRecord`; candidate hash mismatch → REJECTED.
5. **Timeout, retry budget, circuit breaker, cancellation, per-provider concurrency** — DONE: `ExecutionPolicy`/`CircuitBreaker` (CLOSED/OPEN/HALF_OPEN)/`CancellationScope`/semaphore; test: timeout → `ASSET_PROVIDER_TIMEOUT`, retry 3 attempts → `ASSET_RETRY_BUDGET_EXHAUSTED`, breaker OPEN chặn trước execution, cancel giữa chừng → CANCELLED không publish side effect, concurrency peak = limit.
6. **Không lưu credential; receipt chỉ lưu secret reference đã redact** — DONE: `assert_no_credentials` (value-based; `env:VAR` reference được phép, giá trị secret bị chặn `SecretLeakError`); config mesh chỉ có `api_key_ref`/`client_ref`; receipts redact.
7. **Fake adapters cho CI + contract test chung** — DONE: 5 fake adapters deterministic; `tests/contracts/asset_adapter_contract.py` suite áp cho fake VÀ real adapters (cùng semantics, fail-closed branch riêng).

## Kiến trúc

```text
core/contracts/video_production/asset_resolver.py        AssetResolverPort
core/domain/video_production/asset_resolution/           DTOs + typed errors (provider-neutral)
providers/windagent_providers/assets/                    adapters + matcher + cache + execution + resolver + fakes
tools/windagent_tools/media_assets/                      shared download/validation (giữ nguyên; inject qua ports)
```

`AssetResolver` triển khai `AssetResolverPort`: plan adapters → capability match → cache lookup → concurrent discover (semaphore per provider) → typed result; acquire kiểm tra capability lần nữa, cache reuse, side effects chỉ qua outcome OK.

## Kiểm thử

- 113 passed / 31 skipped (skip = not-READY adapter, fail-closed branch có test riêng) / 0 failed.
- Negative: unsupported kind rejection trước call, unknown adapter id, candidate hash mismatch, credential leak fail-closed, path traversal, generator disabled, circuit OPEN.
- Regression: core + architecture + media_assets + tools suites 638 passed; 1 pre-existing failure thuộc Phase 4 untracked work (FrameManifest), không liên quan Phase 5.

## Evidence

`artifacts/video_production_3d/phase_05/`: input_manifest.json, implementation_manifest.json (SHA-256 mọi file), test_receipt.json, architecture_report.json, risk_register.json, phase_report.md, phase_verdict.json.

## Gate

`VP3D_P5_ASSET_GATEWAY_VERIFIED` — mọi backlog item hoàn tất, test + architecture + negative pass, docs deliverables (resolver_contract.md, provider_capability_matrix.md) có mặt.

## Known limitations / deferred

- Mesh API/MCP transport thật, generation backend thật: Phase 6+ (Phase 5 = surface + fail-closed).
- QUARANTINED/APPROVED license lifecycle, signed-URL redaction: Phase 6.
- Sandboxed mesh import + VRAM estimate + preview render: Phase 7.
- Cache in-memory: persistence deferred (key canonical sẵn sàng cho storage).
