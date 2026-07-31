# Kế hoạch 02 — Phase 4–7: VideoClaw Pre-production Kernel

## 1. Mục đích

Kế hoạch này triển khai việc tiếp nhận VideoClaw theo mô hình:

```text
vendor snapshot
→ quarantine
→ characterize
→ extract/rewrite capability
→ retire upstream runtime dependency
→ secure asset acquisition
```

Đầu ra là pre-production kernel của WindAgent tạo được `VideoProductionPackage v1`, không trao project/session/orchestration authority cho VideoClaw và không phụ thuộc runtime vào `third_party`.

Tài liệu này kế thừa [`road_map.md`](../../../road_map.md) và [Kế hoạch 01](01_phase_00_03_protocol_governance.md).

## 2. Gate và kết quả cần đạt

```text
VP4_VIDEOCLAW_QUARANTINED
VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED
VP6_PREPRODUCTION_KERNEL_CANONICAL
VP7_ASSET_PIPELINE_VERIFIED
```

Kết quả handoff:

```text
idea / brief
     ↓
canonical screenplay + entity/style bibles
     ↓
validated and provenance-aware reference assets
     ↓
VideoProductionPackage v1
     ↓
READY_FOR_DIRECTOR_LAYER
```

## 3. Điều kiện bắt đầu

- `VP0_BASELINE_FROZEN`, `VP1_UPSTREAM_ADOPTION_APPROVED` và `VP3_CANONICAL_PROTOCOL_VERIFIED` đã pass.
- Có pinned VideoClaw SHA, source content hash và adoption matrix đã duyệt.
- License/notice obligations đã xác định.
- Protocol fixtures, validator và provider-agnostic LLM/VLM ports dùng được.
- Chưa có source VideoClaw trong workspace/runtime.

Nếu upstream snapshot không khớp hash Phase 1, dừng Phase 4 và review lại; không cập nhật pin âm thầm.

## 4. Phạm vi

### Giữ lại dưới dạng capability

- Idea expansion, creative brief và story outline.
- Multi-scene screenplay, dialogue và narration.
- Character, location và prop extraction.
- Style definition và plot continuation.
- Prompt cho asset đầu vào.
- Tìm kiếm/tạo/tải/validate asset và provenance.

### Loại khỏi kernel

- Upstream video generation và final editing.
- Upstream project/session/task authority.
- Local JSON task database và resume authority.
- Upstream WebUI, provider config và composition root.
- Upstream storyboard/orchestration authority.
- Mọi direct runtime import từ `third_party`.

## 5. Package mục tiêu

```text
intelligence/windagent_intelligence/video/
├── ideation/
├── screenplay/
├── entity_extraction/
└── style_design/

tools/windagent_tools/
├── video_preproduction/
└── media_assets/

third_party/videoclaw/
├── upstream/
├── PATCHES.md
├── UPSTREAM_MANIFEST.json
├── LICENSE
└── NOTICE.md
```

Các domain object và ports vẫn thuộc `core`; logic LLM/VLM thuộc `intelligence`; network/file acquisition thuộc `tools`.

## 6. Quy ước branch và evidence

```text
feat/video-production-phase4-videoclaw-intake
feat/video-production-phase5-characterization
feat/video-production-phase6-preproduction
feat/video-production-phase7-assets
```

Mỗi phase tạo:

```text
artifacts/video_production/phase_XX/
├── input_manifest.json
├── test_receipt.json
├── architecture_report.json
├── phase_report.md
└── phase_verdict.json
```

Không commit API key, output model chứa dữ liệu nhạy cảm, cache dependency, browser profile hoặc downloaded asset chưa qua review.

---

# Phase 4 — Tải và quarantine VideoClaw upstream

## 7. Mục tiêu

Đưa đúng snapshot đã duyệt vào repository để phục vụ audit/characterization, trong khi architecture và build đảm bảo snapshot không thể trở thành runtime dependency.

## 8. Workstream

### 8.1 Intake có kiểm soát

1. Tải archive từ repository và commit đã pin.
2. Xác minh archive/source-tree hash với Phase 1.
3. Giải nén trong thư mục tạm, kiểm tra path traversal, symlink và file bất thường.
4. So sánh file inventory với adoption matrix.
5. Chép nguyên snapshot đã duyệt vào `third_party/videoclaw/upstream/`.
6. Không format, normalize line ending hoặc sửa upstream source trong bước intake.

Mọi sai khác phải tạo `intake_diff.json`; không tự chấp nhận vì upstream có commit mới hơn.

### 8.2 Manifest và notice

`UPSTREAM_MANIFEST.json` tối thiểu gồm:

```json
{
  "source_repository": "HITsz-TMG/VideoClaw",
  "source_commit": "<full-sha>",
  "license": "MIT",
  "imported_at": "<UTC>",
  "archive_sha256": "<sha256>",
  "content_sha256": "<sha256>",
  "file_count": 0,
  "patch_policy": "NO_DIRECT_RUNTIME_IMPORT"
}
```

- `LICENSE` giữ nguyên notice cần thiết.
- `NOTICE.md` mô tả phạm vi sử dụng và các phần bị loại.
- `PATCHES.md` ban đầu ghi `no patches`; mọi patch sau phải có lý do, hash và liên kết issue.

### 8.3 Quarantine boundary

- Không thêm upstream vào `[tool.uv.workspace].members`.
- Không thêm vào `PYTHONPATH`, Node workspace hoặc packaged desktop assets.
- Không import upstream từ `core`, `intelligence`, `tools`, `workflows`, `orchestration`, `storage`, `apps` hoặc `providers`.
- Không dùng upstream API server, frontend, config hoặc task DB làm entrypoint.
- Không cho CI mặc định cài dependency của upstream.
- Distribution build không chứa snapshot trừ khi release policy yêu cầu source notice riêng.

### 8.4 Automated architecture checks

Thêm negative checks cho:

```text
import third_party
import videoclaw
sys.path mutation tới upstream
dynamic import của upstream
subprocess khởi chạy upstream server/UI
workspace membership
packaging include pattern quá rộng
```

## 9. Kiểm thử và evidence

- Hash snapshot tái tạo được.
- Manifest file count/hash khớp filesystem.
- Canonical test suite chạy mà không cài upstream dependencies.
- Architecture negative fixture cố import upstream phải fail.
- Python/Node/package build không kéo upstream vào artifact.
- Secret scan và binary inventory không có finding chưa xử lý.

```text
artifacts/video_production/phase_04/
├── source_archive_receipt.json
├── source_inventory.json
├── content_hash_receipt.json
├── quarantine_boundary_report.json
├── secret_scan_receipt.json
└── phase_verdict.json
```

## 10. Acceptance gate

`VP4_VIDEOCLAW_QUARANTINED` chỉ pass khi snapshot khớp pin, license/notice đầy đủ, architecture checks fail closed và canonical runtime/build không phụ thuộc upstream.

---

# Phase 5 — Characterization testing

## 11. Mục tiêu

Ghi lại hành vi thực tế cần bảo tồn trước khi refactor, bao gồm cả lỗi và nondeterminism. Characterization mô tả upstream; nó không tự định nghĩa hành vi canonical mong muốn.

## 12. Test harness

### 12.1 Cách ly

- Harness chạy ngoài canonical composition root.
- Credential dùng fake/local test provider; live model chỉ chạy khi có explicit approval.
- Network mặc định bị chặn; test cần network được gắn nhãn riêng.
- Input/output ở thư mục tạm, không dùng upstream home/session mặc định.
- Timeout và process cleanup bắt buộc.

### 12.2 Fixture

```text
tests/fixtures/video_production/videoclaw_characterization/
├── fixture_short_cartoon/
├── fixture_two_character_dialogue/
└── fixture_multi_scene_drama/
```

Mỗi fixture có:

- idea/brief đầu vào;
- provider responses được pin hoặc recorded-and-sanitized;
- expected capability path;
- canonicalization policy;
- expected stable fields;
- allowed variation;
- known defect references.

Không tái sử dụng fixture upstream nếu adoption matrix không cho phép.

### 12.3 Behavior matrix

Bao phủ 16 tình huống trong roadmap và bổ sung:

- Unicode/Vietnamese screenplay;
- empty/oversized input;
- repeated character names nhưng ID khác;
- broken provider response;
- partial artifact write;
- cancellation giữa capability;
- deterministic rerun với cùng provider fixture.

Mỗi case ghi:

```text
case_id
capability
preconditions
input_fixture
observed_output
stable_fields
unstable_fields
side_effects
failure_class
canonical_target_behavior
```

### 12.4 Canonicalization

Chỉ loại bỏ field thực sự không ổn định:

- timestamp;
- random/session ID;
- absolute path;
- unordered metadata được chứng minh không có ý nghĩa;
- provider metadata không thuộc contract.

Không canonicalize mất nội dung, thứ tự scene, lỗi, warning hoặc artifact relationship.

## 13. Deliverables và gate

```text
artifacts/video_production/phase_05/
├── behavior_matrix.json
├── golden_outputs.json
├── canonicalization_rules.json
├── defect_inventory.json
├── nondeterminism_inventory.json
├── harness_test_receipt.json
└── phase_verdict.json
```

`VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED` chỉ pass khi:

1. Tất cả capability được giữ lại có ít nhất một happy-path và failure-path test.
2. Ba golden fixture chạy lặp lại với kết quả stable sau canonicalization.
3. Defect không bị biến thành expected canonical behavior mà không có quyết định.
4. Nondeterminism có nguyên nhân hoặc boundary chấp nhận rõ ràng.
5. Harness không làm upstream trở thành runtime dependency.

---

# Phase 6 — Tách Pre-production Kernel

## 14. Mục tiêu

Triển khai capability canonical theo Architecture V2, so sánh với characterization và kết thúc với zero runtime import từ upstream.

## 15. Thứ tự extraction

Triển khai theo lát dọc, mỗi lát hoàn tất contract → implementation → test → evidence trước lát tiếp theo:

```text
1. creative brief / idea expansion
2. story outline
3. multi-scene screenplay
4. dialogue and narration
5. character/location/prop extraction
6. style bible
7. plot continuation and revision proposal
8. asset prompt specification
9. assemble VideoProductionPackage
```

Không di chuyển hàng loạt file upstream rồi sửa dần trong canonical package.

## 16. Workstream

### 16.1 Ports và provider neutrality

- LLM/VLM request đi qua contract hiện có hoặc port canonical.
- Model ID, temperature, token limit và response schema là parameter/versioned config.
- Provider response được parse/validate trước khi vào domain.
- Retry chỉ áp dụng lỗi retryable và có giới hạn.
- Không để provider SDK object lọt vào package/event.

### 16.2 Service design

Mỗi capability:

- nhận domain input rõ ràng;
- trả domain object hoặc typed failure;
- không tự ghi project/session DB;
- không tự lock screenplay hoặc approve asset;
- không gọi video generation;
- phát event qua boundary do workflow điều phối;
- có prompt/template version và hash nếu dùng model.

### 16.3 Screenplay và entity consistency

- Scene order xác định.
- Dialogue trỏ đúng character ID.
- Character/location/prop occurrence truy được về scene.
- Duplicate display name không làm merge identity.
- Story continuation tạo revision proposal, không mutate screenplay locked.
- Output luôn validate bằng schema Phase 3 trước publish.

### 16.4 Equivalence policy

So sánh theo semantic field, không ép text model giống từng ký tự:

| Capability | Blocking equivalence |
|---|---|
| Brief | mục tiêu, audience, duration/constraint không mất |
| Outline | scene/beat coverage và thứ tự hợp lệ |
| Screenplay | đủ scene, dialogue attribution, narration |
| Entity extraction | precision/recall trên golden fixture đạt ngưỡng được duyệt |
| Style | các style constraint bắt buộc được giữ |
| Continuation | không phá locked facts và existing IDs |

Ngưỡng cụ thể được chốt trong `equivalence_policy.md` trước khi chạy verdict; không hạ ngưỡng sau khi xem kết quả.

### 16.5 Retire upstream dependency

- Search/import graph không có canonical reference tới upstream.
- Characterization harness là nơi duy nhất có thể khởi chạy upstream.
- Canonical integration tests chạy sau khi tạm thời làm upstream path không tồn tại.
- Build/package không thay đổi khi xóa snapshot khỏi test environment.

## 17. Kiểm thử

- Unit test từng capability với deterministic provider fake.
- Contract test invalid/partial model response.
- Integration test idea → complete package.
- Golden semantic comparison.
- Retry/timeout/cancel tests.
- Unicode, duplicate names và multi-scene relationships.
- Architecture imports.
- Serialization và schema validation.

## 18. Deliverables và gate

```text
docs/video_production/preproduction/
├── capability_contracts.md
├── prompt_versioning.md
├── equivalence_policy.md
└── upstream_retirement.md

artifacts/video_production/phase_06/
├── capability_matrix.json
├── golden_comparison.json
├── provider_contract_receipt.json
├── no_upstream_import_report.json
├── integration_test_receipt.json
└── phase_verdict.json
```

`VP6_PREPRODUCTION_KERNEL_CANONICAL` chỉ pass khi package hợp lệ, equivalence policy đạt, tests pass và upstream có thể vắng mặt mà runtime vẫn hoạt động.

---

# Phase 7 — Asset acquisition và provenance

## 19. Mục tiêu

Tạo pipeline asset an toàn cho ảnh model-generated hoặc ảnh tải hợp pháp, với provenance, validation, human approval và content hash trước khi bind vào project.

## 20. Thành phần

```text
AssetSearchService
AssetDownloadService
AssetValidationService
AssetProvenanceService
IdentityReferenceBuilder
LocationReferenceBuilder
```

Search/download thuộc `tools`; policy, metadata và state transition dùng contract/domain canonical.

## 21. Workstream

### 21.1 Search và acquisition contract

- Query, source provider, result URL và retrieval time được ghi lại.
- Search result chỉ ở trạng thái `DISCOVERED`, chưa được dùng làm reference.
- Download chỉ nhận HTTP/HTTPS và domain/policy được phép.
- Mọi redirect được resolve và kiểm tra lại.
- DNS resolve phải chặn localhost, link-local, private/reserved IP và DNS rebinding.
- Timeout, max redirects, max bytes và concurrency được cấu hình.

### 21.2 File validation

Thứ tự bắt buộc:

```text
stream to quarantine
→ size limit
→ content hash
→ MIME signature/sniff
→ decoder validation
→ pixel/decompression limit
→ metadata inspection
→ malware scan when available
→ EXIF sanitization
→ publish to content-addressed store
```

- Extension không phải bằng chứng MIME.
- File 0 byte, polyglot, executable hoặc archive bị từ chối.
- SVG bị cấm trong Release 0.1 trừ khi có sanitizer đã kiểm chứng.
- Validation failure không publish partial artifact.

### 21.3 Provenance và license

Mỗi asset record có:

```text
asset_id
content_sha256
source_type
source_url/provider
retrieved_at
original_license
license_evidence
creator/attribution
transformation_history
validation_receipt
approval_state
```

`LICENSE_UNKNOWN` không được tự chuyển thành `APPROVED`.

### 21.4 Identity và likeness

- Character reference builder không gộp identity chỉ dựa trên tên.
- Reference master gắn với character ID và revision.
- Ảnh người thật/likeness yêu cầu human approval và evidence về quyền sử dụng.
- Rejected asset không được chọn lại qua duplicate URL/hash.
- Biến thể generated truy được về source reference và prompt.

### 21.5 State machine

Transition hợp lệ:

```text
DISCOVERED → DOWNLOADED → VALIDATED
VALIDATED → LICENSE_UNKNOWN | APPROVED | REJECTED
LICENSE_UNKNOWN → APPROVED | REJECTED
APPROVED → BOUND_TO_PROJECT
```

Không cho `DOWNLOADED → BOUND_TO_PROJECT` hoặc `REJECTED → APPROVED` nếu không có review record mới.

## 22. Kiểm thử bảo mật và tích hợp

- Localhost/private IP, redirect sang private IP và DNS rebinding.
- Oversize response, decompression bomb, wrong MIME, zero byte, truncated image.
- Malicious EXIF, path traversal filename, duplicate content.
- License unknown và missing attribution.
- Human approval required cho real-person likeness.
- Atomic publish: cancel/crash không để artifact hợp lệ giả.
- End-to-end brief → screenplay → bibles → approved references → package.

## 23. Deliverables và gate

```text
docs/video_production/assets/
├── acquisition_policy.md
├── supported_media_types.md
├── provenance_schema.md
├── likeness_approval_policy.md
└── retention_and_rejection.md

artifacts/video_production/phase_07/
├── downloader_security_matrix.json
├── media_validation_receipt.json
├── provenance_contract_receipt.json
├── state_machine_test_receipt.json
├── e2e_package_receipt.json
└── phase_verdict.json
```

`VP7_ASSET_PIPELINE_VERIFIED` chỉ pass khi:

1. SSRF/redirect/MIME/size/pixel controls có automated negative tests.
2. Mọi approved/bound asset có hash, validation và provenance.
3. Unknown license hoặc real-person likeness không vượt human gate.
4. Partial/invalid download không xuất hiện trong canonical store.
5. Pre-production E2E tạo package hợp lệ mà không import upstream.

## 24. Handoff sang Director Layer

Handoff phải gồm:

- `VideoProductionPackage v1` fixture cho ba kịch bản;
- screenplay revision đã lock hoặc trạng thái lock rõ ràng;
- stable IDs cho scene/character/location/prop;
- approved identity/location references và content hashes;
- style bible và production constraints;
- prompt/template version của pre-production;
- unresolved creative ambiguity dưới dạng issue, không ẩn trong text.

Director không được nhận upstream session ID, local JSON path hoặc VideoClaw provider object.

## 25. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Upstream lẻn vào runtime qua dynamic import | Architecture check cho import, `sys.path`, subprocess và packaging |
| Golden snapshot che mất defect | Tách observed behavior khỏi canonical expected behavior |
| Refactor big-bang khó review | Extraction theo capability và PR nhỏ |
| LLM output không ổn định | Structured output, deterministic fake và semantic comparison policy |
| Downloader tạo SSRF/decompression risk | Quarantine stream, revalidation và bounded decode |
| Asset không đủ quyền sử dụng | `LICENSE_UNKNOWN` fail closed và human approval |
| Tráo identity do trùng tên | Stable character ID và reference binding theo revision |

## 26. Checklist đóng kế hoạch

- [x] Snapshot đúng pinned hash và đang quarantine — **Phase 4 PASSED** (2026-08-01). Re-pin amendment: pin Phase 1 metadata cũ (`7b328a99…1234`, không tồn tại upstream, GitHub API 422) được thay bằng HEAD thật `5a16ae23…` (main, 2026-07-17) với ghi chú amendment trong `upstream_source_receipt.json`. Snapshot 443 files (46MB) vendor tại `third_party/videoclaw/upstream/`; archive SHA-256 `6353b4cc…`; content digest `86a8af…`; 0 symlink, 0 path traversal. Evidence: `artifacts/video_production/phase_04/phase_verdict.json` (gate `VP4_VIDEOCLAW_QUARANTINED`).
- [x] Characterization matrix đủ happy/failure paths — **Phase 5 PASSED** (2026-08-01). 27 behavior cases (16 roadmap + 11 extended: Unicode/Vietnamese, empty/oversized, duplicate names, broken response, partial write, cancellation, deterministic rerun, hash-seed ordering) bao phủ 5 capabilities (CAP-001..005) đều có happy + failure path. Evidence: `artifacts/video_production/phase_05/phase_verdict.json` (gate `VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED`).
- [x] Canonical pre-production không import upstream — quarantine boundary được enforced: `check_videoclaw_quarantine` trong `scripts/check_architecture_imports.py` (5 negative rules) + `verify_phase4_intake.py`; architecture check PASS 0 violations. Harness isolation: upstream chỉ được launch qua `scripts/verification/phase5_upstream_probe.py` (subprocess, temp CWD, network-blocked stubs, `PYTHONHASHSEED=0` + `PYTHONDONTWRITEBYTECODE=1`); `tests/architecture/test_phase05_characterization_harness.py` chứng minh canonical code không import/launch upstream.
- [ ] Ba fixture tạo được `VideoProductionPackage v1` — **Phase 6 chưa thực hiện**.
- [ ] Asset pipeline vượt security negative tests — **Phase 7 chưa thực hiện**.
- [ ] Provenance và likeness approval fail closed — **Phase 7 chưa thực hiện**.
- [x] `VP4` **PASSED** (2026-08-01); `VP5` **PASSED** (2026-08-01); `VP6`/`VP7` — chưa thực hiện.
- [ ] Handoff Director Layer đã được review — chờ các phase 6-7.

### Ghi chú Phase 5 (characterization)

- Harness: `scripts/verification/phase5_upstream_probe.py` load 4 agent modules upstream qua synthetic package (`importlib.spec_from_file_location`, bypass `core/__init__.py` chain để không kéo FastAPI/OpenAI/DashScope), stub `config`/`models.*` (network blocked), CWD redirect tới temp workdir, stdout UTF-8, `sys.dont_write_bytecode = True` + env `PYTHONDONTWRITEBYTECODE=1` để không tạo `__pycache__`/`.pyc` bên trong `third_party/videoclaw/upstream/` (quarantine Phase 4 pin 443 files + content digest).
- Verifier `verify_phase5_characterization.py`: behavior matrix (27 cases), canonicalization rules (strip timestamp/uuid/absolute path; giữ order/error/relationship), golden stability 3 reruns (stable sau hash-seed pin; NONDET-005 ghi nhận upstream `sorted(set(names), key=len)` phụ thuộc hash seed), defect inventory DEF-001..005 (all decided, DEF-003 cross-ref NONDET-005), nondeterminism NONDET-001..005 (all explained), harness receipt (hash_seed_pinned), verdict derive từ real probe runs + quarantine check 0 violations. Hỗ trợ `--no-write`/`--verify-only`.
- Tests: `tests/architecture/test_phase05_characterization_harness.py` (launch/import patterns thay vì keyword-presence — docstring mention hợp lệ; `ALLOWED_LAUNCH_ZONES` = scripts/verification/, tests/, check_architecture_imports.py), `tests/unit/verification/test_phase05_characterization.py`, mở rộng `test_phase03_verifier_no_write.py` cho Phase 5. Full relevant suite 21 passed; architecture PASS 0 violations; Phase 3/4/5 + handoff `--no-write` đều PASSED.

### Ghi chú Phase 4 (re-pin amendment)

- Pin Phase 1 ban đầu `7b328a99…` là metadata-derived (`METADATA_REVIEW_ONLY_NO_SOURCE_VENDORED`) và **không tồn tại** trên GitHub. Đã được re-pin có kiểm soát về HEAD thật `5a16ae23a4f1cb6886c44c0205f7b7e52a34c276` theo quyết định review (mục 3: dừng Phase 4 nếu snapshot không khớp pin — không cập nhật âm thầm).
- Evidence Phase 1 (`upstream_source_receipt.json`, `source_tree_hashes.json`, `risk_register.json`), hằng số `verify_phase03_handoff.py` và handoff evidence đã được cập nhật/re-tạo tương ứng; handoff vẫn `VP0_3_HANDOFF_PACKAGE_VERIFIED` PASSED.
- Quy trình: `verify_phase4_intake.py` hỗ trợ `--no-write`/`--verify-only` (không ghi evidence khi re-run); archive SHA-256 là evidence download-time immutable, gate tái lập được là content digest tính từ tree đã commit.
