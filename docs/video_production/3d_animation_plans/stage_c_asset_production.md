# Stage C — Asset Production

## 1. Kết quả cần đạt

Mọi nhu cầu 3D được giải quyết qua một gateway duy nhất, asset có quyền sử dụng và provenance đầy đủ, sau đó được normalize về chuẩn nội bộ trước khi Scene Compiler tiêu thụ. Director không gọi Internet, Mesh API/MCP hoặc Blender trực tiếp.

## 2. Điều kiện đầu vào

- Stage B tạo được preview scene/render deterministic.
- Production IR đã có `AssetRequirement`/asset reference versioned hoặc được mở rộng trong Phase 5.
- Security boundary cho download, subprocess và workspace đã có.
- Xác định budget mặc định cho polygon, texture, file size và VRAM preview.

## 3. Phase 5 — Universal Asset Gateway

### Contract

Tạo `AssetResolverPort` và các DTO trung lập provider:

```text
AssetRequirement
AssetCandidate
AssetResolutionRequest
AssetResolutionResult
AssetProviderCapability
```

Adapters dự kiến nằm trong `providers/windagent_providers/assets/`: local, internet, Mesh API, Mesh MCP và future generator. `tools/windagent_tools/media_assets/` tiếp tục chứa download/validation dùng chung.

### Backlog

1. Chuẩn hóa loại asset, style, topology, rig requirement, texture resolution, license constraint và budget.
2. Capability matching trước khi gọi adapter; provider không hỗ trợ yêu cầu phải trả typed rejection.
3. Idempotency theo canonical requirement + adapter/version; lookup cache trước network/generation.
4. Tách discover khỏi acquire; kết quả search chưa phải asset được phép dùng.
5. Thêm timeout, retry budget, circuit breaker, cancellation và per-provider concurrency.
6. Không lưu credential trong request/artifact; receipt chỉ lưu secret reference đã redact.
7. Fake adapters cho CI và contract test chung để mọi adapter trả cùng semantics.

## 4. Phase 6 — Asset Trust & Provenance

### Backlog

1. Mở rộng `AssetSourceType` và `LicenseState` cho local library, Internet, API, MCP và generated asset.
2. Bắt buộc provenance: source/provider/author/license/download time/original hash/tool/model/prompt hash/seed khi áp dụng.
3. Asset `UNKNOWN`, thiếu quyền cho commercial use hoặc không xác minh checksum phải vào `QUARANTINED`.
4. Downloader chỉ HTTP(S), revalidate redirect/IP, giới hạn bytes/decompression, MIME sniffing và chặn executable/path traversal.
5. Scan archive/mesh/texture; không auto-run embedded script, driver hoặc add-on từ asset.
6. Ghi conversion lineage: mỗi derived asset trỏ về source hash và normalization receipt.
7. Approval riêng cho likeness, trademark hoặc license cần attribution.

### Negative tests

- SSRF/private IP, redirect độc hại, MIME giả, zip bomb và path traversal bị chặn.
- Asset đổi nội dung tại cùng URL tạo hash/version mới.
- Unknown license không thể chuyển sang `APPROVED` chỉ bằng metadata provider.
- Log/receipt không chứa token hoặc signed download URL còn hiệu lực.

### Gate — HOÀN TẤT

**Trạng thái: HOÀN TẤT** (2026-08-08) — `VP3D_P6_ASSET_TRUST_PROVENANCE_VERIFIED` PASS.

- ✅ `QUARANTINED` lifecycle state + fail-closed promotion (human review record bắt buộc).
- ✅ Provenance đầy đủ cho generated asset (tool/model/prompt_hash/seed/generation_receipt).
- ✅ Trust enforcer: UNKNOWN license / checksum unverified / commercial-use unverified / trademark chưa duyệt → QUARANTINED; metadata alone không auto-approve.
- ✅ `AssetContentScanner`: chặn embedded executable/script/add-on + zip-slip path traversal; không auto-run.
- ✅ Conversion lineage: derived asset → source content hash + normalization receipt.
- ✅ Approval riêng cho likeness/trademark/attribution (human-approved).
- ✅ Negative tests: zip bomb, path traversal, content-change→new hash, unknown-license-not-approved-by-metadata, receipt redaction token/signed URL.
- 19 test mới pass (test_phase6_asset_trust.py), 45 tổng (kèm phase07), architecture imports 0 violation.

Evidence:
- `docs/video_production_3d/assets/provenance_policy.md`
- `artifacts/video_production_3d/phase_06/phase_verdict.json`
- `artifacts/video_production_3d/phase_06/test_baseline.json`
- `artifacts/video_production_3d/phase_06/contract_tests.json`

## 5. Phase 7 — Asset Normalization

### Pipeline

```text
ingest → security → parse → unit/axis → mesh → material/texture
→ poly/VRAM budget → LOD → preview render → approval/cache
```

### Backlog

1. Canonical metadata dùng meter và Z-up; adapter import/export chịu trách nhiệm chuyển đổi trục thực tế.
2. Validate non-manifold, normals, UV, material slots, missing textures, unsupported shaders, skeleton và animation clips.
3. Chuẩn hóa PBR material; texture được content-addressed, giới hạn resolution/bit depth và có color-space metadata.
4. Tạo LOD theo policy, không overwrite source; mỗi LOD có hash và quality metrics.
5. Estimate geometry/texture VRAM trước preview; vượt hard limit thì `BLOCKED`, không thử render mù.
6. Render turntable/thumbnail bằng deterministic Blender profile của Stage B.
7. Publish asset bundle immutable gồm interchange file, textures, preview, manifest, provenance và validation report.

### Gate

`VP3D_P7_ASSET_NORMALIZATION_VERIFIED` yêu cầu tối thiểu một asset local, một Internet fixture và một generated/fake provider asset đi qua full pipeline; malicious fixtures đều fail-closed.

### Gate — HOÀN TẤT

**Trạng thái: HOÀN TẤT** (2026-08-08) — `VP3D_P7_ASSET_NORMALIZATION_VERIFIED` PASS.

- ✅ Canonical metadata meters + Z-up (`CanonicalMetadata` derive scale_factor từ detected unit, fail-closed UNKNOWN ⇒ meters); adapter chịu trách nhiệm convert trục.
- ✅ Host-side parsers engine-free cho GLTF/GLB/OBJ (`parse_asset`); FBX/USD/BLEND yêu cầu sandboxed Blender job, không có job runner ⇒ fail closed.
- ✅ Mesh validation fail-closed: degenerate faces, non-manifold heuristic, missing UV/textures, unsupported shader extensions, skeleton/animation report; poly budget ⇒ `BLOCKED`.
- ✅ PBR material + texture content-addressed (resolution cap, bit-depth, color-space metadata, metadata strip).
- ✅ VRAM estimate trước preview; over hard limit ⇒ `BLOCKED`, không render mù.
- ✅ LOD theo policy (`NONE/SINGLE/MULTI`), source không bao giờ overwrite; mỗi LOD có hash + quality metrics.
- ✅ Preview render deterministic (Cycles CPU, samples=8, 512x288, Standard color management) qua Blender job `execute_asset_job.py` (pure stdlib, auto-execution tắt) hoặc fake CI.
- ✅ Immutable bundle: manifest + validation_report + provenance + textures content-addressed + lods + preview, bundle hash deterministic.
- ✅ Negative tests: archive/executable/shebang rejected trước parse, content-hash mismatch, path-traversal texture URI, VRAM/poly BLOCKED không render, no-job-runner fail closed.
- ✅ Local + Internet fixture + generated/fake-provider asset đều đi full pipeline (integration suite).
- 45+ test mới pass (domain 8 + host 18 + job contract 8 + integration 11 + architecture 9), ruff clean, architecture imports 0 violation.

Evidence:
- `docs/video_production_3d/assets/normalization_profile.md`
- `artifacts/video_production_3d/phase_07/phase_verdict.json`
- `artifacts/video_production_3d/phase_07/test_receipt.json`
- `artifacts/video_production_3d/phase_07/implementation_manifest.json`

## 6. Deliverables và test matrix

```text
docs/video_production_3d/assets/
├── resolver_contract.md
├── provenance_policy.md
├── normalization_profile.md
└── provider_capability_matrix.md

artifacts/video_production_3d/phase_05..07/
```

Test phải bao phủ cache hit/miss, cancellation, provider timeout, duplicate request, license transition, conversion failure, preview render failure và deterministic bundle hash.

## 7. Rủi ro

- Format 3D không an toàn như media phẳng; import phải chạy trong sandboxed Blender job và tắt auto-execution.
- License metadata từ Internet không luôn đáng tin; state mặc định là quarantine.
- Auto-decimation có thể phá facial/skeletal topology; character asset cần profile riêng và approval ở Stage D.
