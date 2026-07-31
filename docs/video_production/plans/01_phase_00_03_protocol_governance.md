# Kế hoạch 01 — Phase 0–3: Protocol và Governance

## 1. Mục đích

Kế hoạch này biến phần Phase 0–3 trong [`road_map.md`](../../../road_map.md) thành các bước thực thi có thể kiểm chứng. Kết quả cuối cùng là một baseline bất biến, quyết định tiếp nhận upstream rõ ràng, bộ yêu cầu Director theo clean-room và `VideoProductionPackage v1` đủ ổn định để các phase sau cùng triển khai trên một protocol duy nhất.

Tài liệu này là kế hoạch con. Nếu có mâu thuẫn, `road_map.md` và ADR đã được phê duyệt có quyền cao hơn.

## 2. Kết quả cần đạt

```text
verified WindAgent baseline
        ├── approved VideoClaw adoption boundary
        ├── independent ViMax-derived requirements
        └── canonical video production protocol
                         ↓
            READY_FOR_VIDEOCLAW_INTAKE
```

Các verdict phải đạt theo thứ tự:

```text
VP0_BASELINE_FROZEN
VP1_UPSTREAM_ADOPTION_APPROVED
VP2_DIRECTOR_REQUIREMENTS_FROZEN
VP3_CANONICAL_PROTOCOL_VERIFIED
```

## 3. Phạm vi và ngoài phạm vi

### Trong phạm vi

- Chứng nhận commit baseline và trạng thái repository.
- Legal, license, security, dependency và provenance review cho VideoClaw.
- Nghiên cứu hành vi ViMax theo quy trình clean-room.
- Định nghĩa domain model, schema, events, ports và quy tắc revision.
- Tạo validator, fixture và compatibility tests cho protocol.
- Tạo evidence có thể truy vết từ verdict về commit và test run.

### Ngoài phạm vi

- Không vendor source VideoClaw trong Phase 0–3.
- Không thêm VideoClaw hoặc ViMax vào workspace/runtime.
- Không triển khai Director, storyboard, browser automation hoặc Flow.
- Không tạo media thật và không tiêu Flow credits.
- Không thay đổi authority hiện có của project, task, artifact hoặc approval.

## 4. Điều kiện bắt đầu

- Repository có thể checkout hoặc xác minh commit:
  `cbf7257643d4a1705fa221ae37e9391b6ee3f40e`.
- Các lệnh test canonical của Python, web, desktop, CLI và architecture checker được xác định từ repository.
- Worktree hiện tại được kiểm kê; thay đổi của người dùng không bị ghi đè.
- Người chịu trách nhiệm phê duyệt legal/security và protocol được chỉ định.
- Mọi evidence dùng thời gian UTC, SHA đầy đủ và đường dẫn tương đối với repository.

Nếu commit baseline không tồn tại hoặc test baseline không thể tái lập, Phase 0 mang verdict `BLOCKED`; không được tự chọn commit thay thế.

## 5. Quy ước thực thi chung

### 5.1 Branch

```text
feat/video-production-phase0-baseline
feat/video-production-phase1-upstream
feat/video-production-phase2-clean-room
feat/video-production-phase3-protocol
```

Mỗi branch bắt đầu từ SHA đã được phase trước chứng nhận. Phase 1 và Phase 2 có thể làm song song sau Phase 0; Phase 3 chỉ bắt đầu khi cả hai gate đã pass.

### 5.2 Evidence tối thiểu cho mỗi phase

```text
artifacts/video_production/phase_XX/
├── input_manifest.json
├── implementation_manifest.json
├── test_receipt.json
├── architecture_report.json
├── risk_register.json
├── phase_report.md
└── phase_verdict.json
```

`phase_verdict.json` phải chứa tối thiểu:

```json
{
  "phase": 0,
  "baseline_sha": "<full-sha>",
  "candidate_sha": "<full-sha>",
  "status": "PASSED",
  "gate": "VP0_BASELINE_FROZEN",
  "evidence": [],
  "blocking_reasons": []
}
```

Verdict chỉ được phát hành sau khi evidence đã tồn tại, được hash và không mâu thuẫn với phase report. Trạng thái hợp lệ là `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED` hoặc `PASSED`.

### 5.3 Definition of Done chung

- Implementation và tài liệu không vượt phạm vi phase.
- Unit, integration, schema và architecture checks liên quan đều pass.
- Không có secret, cookie, token hoặc đường dẫn profile trong log/evidence.
- Mọi file sinh ra có owner, schema/version và provenance.
- Gate được derive từ acceptance criteria, không nhập `PASSED` thủ công.
- Draft PR không merge khi `blocking_reasons` còn phần tử.

---

# Phase 0 — Freeze baseline và mở program

## 6. Mục tiêu

Chứng minh chương trình video production bắt đầu từ đúng baseline đã được xác nhận, không làm thay đổi runtime và có bộ số liệu so sánh cho các phase sau.

## 7. Workstream

### 7.1 Kiểm kê repository

1. Ghi lại:
   - repository root;
   - current branch và HEAD;
   - `git status --short`;
   - tracked/untracked file inventory;
   - submodule, worktree và ignored-file summary;
   - phiên bản Python, Node, package manager, FFmpeg nếu đã có.
2. Xác minh commit baseline tồn tại và đọc được.
3. Xác minh lineage giữa branch làm việc và baseline.
4. Phân loại thay đổi hiện có thành:
   - baseline-owned;
   - user-owned/unrelated;
   - generated evidence;
   - unknown.
5. Không tự dọn hoặc reset thay đổi không thuộc phase.

### 7.2 Chốt test matrix baseline

Từ các entrypoint canonical hiện có, lập manifest lệnh cho:

- architecture/import boundary checks;
- full Python unit và integration tests;
- CLI verification;
- web unit tests và build;
- desktop unit tests và build;
- database checks trên backend mặc định;
- version/lock consistency;
- artifact/evidence validation hiện hành.

Mỗi command record:

```text
command_id
working_directory
argv
environment_allowlist
started_at / finished_at
exit_code
stdout/stderr artifact
tool_versions
candidate_sha
```

Không coi test bị skip do thiếu dependency là pass. Skip phải được phân loại `EXPECTED`, `ENVIRONMENT_BLOCKED` hoặc `DEFECT`.

### 7.3 Chạy và đóng băng baseline

- Chạy test trên commit baseline trong môi trường sạch hoặc worktree cô lập.
- Ghi tổng số pass/fail/skip và thời lượng.
- Ghi architecture package inventory để phát hiện dependency mới về sau.
- So sánh lockfile và version declarations.
- Tạo baseline verdict; không sửa runtime để làm xanh baseline trong phase này.

## 8. Deliverables

```text
artifacts/video_production/phase_00/
├── baseline_commit.json
├── workspace_inventory.json
├── toolchain_inventory.json
├── test_command_manifest.json
├── test_baseline.json
├── architecture_baseline.json
├── known_baseline_failures.json
└── baseline_verdict.json
```

## 9. Acceptance gate

`VP0_BASELINE_FROZEN` chỉ pass khi:

1. Baseline SHA khớp đầy đủ với SHA được chỉ định.
2. Worktree dùng để test sạch và có inventory.
3. Không có runtime change trong diff của Phase 0.
4. Mọi test baseline đã chạy hoặc có blocker môi trường được chứng minh.
5. Baseline failure, nếu có, được ghi rõ và không bị trình bày thành pass.
6. Tất cả phase sau có thể tham chiếu cùng một `baseline_commit.json`.

---

# Phase 1 — Upstream legal, security và provenance review

## 10. Mục tiêu

Chọn đúng commit VideoClaw và quyết định từng capability/file/dependency được tiếp nhận, viết lại, chỉ tham khảo hay loại bỏ trước khi source được vendor.

## 11. Workstream

### 11.1 Pin và xác thực upstream

- Ghi repository URL canonical, commit SHA đầy đủ, commit date và tag gần nhất.
- Lưu hash archive/source tree và phương pháp tải.
- Xác minh `LICENSE`, copyright notice và lịch sử thay đổi license.
- Không dùng `main`, release URL không pin hoặc archive không có checksum.

### 11.2 License và attribution

Tạo legal inventory cho:

- source VideoClaw;
- Python và Node direct/transitive dependencies;
- model weights hoặc sample assets nếu có;
- FFmpeg/binary được bundle;
- font, ảnh, âm thanh, fixture và generated sample;
- nội dung cần đưa vào `LICENSE`, `NOTICE.md` và distribution.

Mọi mục có license chưa rõ phải là `UNKNOWN` và chặn gate nếu nằm trong phạm vi tiếp nhận.

### 11.3 Security review

Kiểm tra tĩnh và lập threat inventory cho:

- secret/API key handling;
- network endpoint, proxy và telemetry;
- file download, archive extraction và path handling;
- dynamic import/eval;
- subprocess và shell invocation;
- deserialization;
- local web server và CORS;
- frontend/backend trust boundary;
- model/provider fallback;
- local artifact/session database;
- update/download-at-runtime behavior.

Không chạy source upstream với credential thật trong review.

### 11.4 Adoption matrix

Mỗi capability hoặc nhóm file có một record:

```text
item_id
upstream_path
capability
classification
reason
license_obligation
security_findings
target_windagent_module
test_or_fixture_reuse_policy
approver
```

Classification:

```text
ADOPT_AND_REFACTOR
REWRITE_FOR_WINDAGENT
REFERENCE_ONLY
REJECT
UNKNOWN
```

`ADOPT_AND_REFACTOR` phải chỉ rõ notice cần giữ. `REWRITE_FOR_WINDAGENT` phải chỉ rõ contract đầu ra. `REFERENCE_ONLY` và `REJECT` không được xuất hiện trong runtime imports.

## 12. Deliverables

```text
docs/upstream/videoclaw/
├── source_commit.md
├── license_review.md
├── dependency_inventory.md
├── security_inventory.md
├── feature_inventory.md
└── adoption_matrix.md

artifacts/video_production/phase_01/
├── upstream_source_receipt.json
├── source_tree_hashes.json
├── license_scan_receipt.json
├── dependency_scan_receipt.json
└── phase_verdict.json
```

## 13. Acceptance gate

`VP1_UPSTREAM_ADOPTION_APPROVED` chỉ pass khi:

1. Upstream commit và content hash đã pin.
2. Tất cả item dự kiến dùng có classification khác `UNKNOWN`.
3. Không có secret, binary, model weight hoặc dependency không rõ nguồn trong phạm vi tiếp nhận.
4. MIT notice và nghĩa vụ dependency đã được ánh xạ vào distribution.
5. Security finding mức chặn có quyết định `fix before intake` hoặc `reject`.
6. Adoption matrix được legal/security/technical owner phê duyệt.

---

# Phase 2 — Clean-room specification từ ViMax

## 14. Mục tiêu

Chuyển các hành vi đáng học từ ViMax thành yêu cầu độc lập mà không đưa source, prompt, schema hoặc fixture của ViMax vào implementation WindAgent.

## 15. Workstream

### 15.1 Behavior inventory

Mô tả ở mức black-box:

- input quan sát được;
- output và side effect;
- invariant;
- checkpoint/resume behavior;
- parallelization behavior;
- failure mode;
- acceptance behavior.

Tập trung vào screenplay-to-shot planning, reference selection, camera continuity, render checkpoint và resume. Không sao chép đoạn mã hoặc prompt.

### 15.2 Independent requirements

Mỗi requirement có ID riêng:

```text
DIR-REQ-001
problem_statement
input_contract
output_contract
invariants
failure_behavior
acceptance_test
source_of_observation
independent_design_notes
```

Yêu cầu phải mô tả vấn đề và hành vi, không mô tả class hierarchy/private method của ViMax.

### 15.3 Terminology và negative design

- Ánh xạ thuật ngữ sang tên canonical trong roadmap.
- Ghi rõ thiết kế bị loại và lý do.
- Cấm tên/schema upstream lọt vào public API nếu chưa được quyết định độc lập.
- Gắn requirement vào package WindAgent dự kiến, không gắn vào source path ViMax.

### 15.4 Clean-room attestation

Attestation xác nhận:

- không vendor hoặc import ViMax;
- không sao chép prompt, fixture, comment dài hoặc source;
- người viết specification và người review implementation tuân thủ boundary;
- mọi attribution nghiên cứu được giữ trong docs/ADR;
- test của WindAgent được tạo từ requirement độc lập.

## 16. Deliverables

```text
docs/video_production/director_research/
├── vimax_behavior_inventory.md
├── independent_requirements.md
├── terminology_mapping.md
├── rejected_designs.md
└── clean_room_attestation.md
```

## 17. Acceptance gate

`VP2_DIRECTOR_REQUIREMENTS_FROZEN` chỉ pass khi:

1. Mọi capability dự kiến dùng có requirement ID.
2. Mỗi requirement có invariant, failure behavior và acceptance test.
3. Terminology khớp roadmap.
4. Không có source/prompt/schema/fixture ViMax trong repo runtime.
5. Clean-room attestation được review độc lập.

---

# Phase 3 — Canonical Video Production Protocol

## 18. Mục tiêu

Triển khai protocol trung gian làm source of truth duy nhất giữa pre-production, Director, orchestration và media provider.

## 19. Thiết kế package dự kiến

```text
core/windagent_core/
├── domain/video_production/
├── contracts/video_production/
└── events/video_production.py
```

Không để `core` import `intelligence`, `tools`, `providers`, `workflows`, `storage` hoặc `third_party`.

## 20. Workstream

### 20.1 Domain model và identity

Triển khai các aggregate/value object trong roadmap, tối thiểu:

- `VideoProject` và `ProductionRevision`;
- creative brief, story concept và screenplay;
- scene, character/location/prop/style bible và dialogue;
- cinematic plan, shot và dependency;
- continuity, reference asset và generation records;
- review, approval và final deliverable.

Quy tắc ID:

- ID là opaque stable identifier, không sinh từ display name.
- Thứ tự scene/shot là explicit integer hoặc sortable key.
- Reference giữa object dùng ID, không duplicate object tùy ý.
- Xóa/đổi tên entity không được tái sử dụng ID cũ.

### 20.2 Revision và immutability

- Mọi revision có `revision_id`, `parent_revision_id`, `created_at`, `created_by` và content hash.
- Artifact locked không được mutate; thay đổi tạo revision mới.
- Screenplay change bắt buộc làm rõ downstream invalidation intent.
- Approval luôn trỏ vào revision/hash cụ thể.
- Serialization canonical phải cho cùng hash với cùng nội dung logic.

### 20.3 Schema và compatibility

- Định nghĩa `VideoProductionPackage v1` bằng schema machine-readable.
- Phân biệt required, optional, nullable và default.
- Từ chối unknown major version.
- Cho phép additive compatible field trong cùng major theo policy được ghi rõ.
- Cung cấp parser/serializer và validator canonical.
- Tạo invalid fixture cho missing ID, duplicate ID, broken reference, unordered shot, asset không hash và mutation sau lock.

### 20.4 Ports

Tạo Protocol/ABC không phụ thuộc implementation cho:

```text
PreproductionPort
VideoDirectionPort
MediaGenerationProviderPort
AssetStoragePort
QualityReviewPort
```

`MediaGenerationProviderPort` phải hỗ trợ semantics cho:

- image generation;
- video generation;
- video extension;
- job inspection;
- result download.

Không đưa selector, cookie, Flow project URL hoặc browser session object vào core contract.

### 20.5 Event protocol

Mỗi event có:

```text
event_id
event_type
schema_version
project_id
revision_id
aggregate_id
causation_id
correlation_id
occurred_at
payload
```

Định nghĩa transition hợp lệ cho danh mục event trong roadmap. Consumer phải idempotent theo `event_id`; duplicate event không được tạo duplicate generation hoặc approval.

### 20.6 Approval và provenance

- Approval ghi actor, role, decision, reason, timestamp và target hash.
- Asset có content hash, media type, source type, source URL nếu có, license state và acquisition record.
- Generated candidate truy được về request hash, prompt version, reference hashes, provider và parameters.
- Trường nhạy cảm không được nằm trong package portable.

## 21. Kiểm thử

### Unit

- Domain invariants và invalid transitions.
- Stable serialization/hash.
- Revision immutability.
- Duplicate/broken reference detection.
- Event envelope validation.
- Approval target hash.

### Contract

- Round-trip JSON: object → JSON → object.
- Backward-compatible additive fields.
- Unknown major version fail closed.
- Provider fake tuân thủ `MediaGenerationProviderPort`.
- Consumer xử lý duplicate event idempotently.

### Architecture

- `core` không import implementation package.
- Không import `third_party`.
- Schema/event catalog chỉ có một canonical definition.
- Không tạo package monolith `video_system/`.

## 22. Deliverables

```text
docs/video_production/protocol/
├── video_production_package_v1.md
├── versioning_policy.md
├── event_catalog.md
├── revision_and_locking.md
└── provider_port_contract.md

artifacts/video_production/phase_03/
├── schema_validation_matrix.json
├── contract_test_receipt.json
├── architecture_report.json
├── compatibility_report.json
└── phase_verdict.json
```

## 23. Acceptance gate

`VP3_CANONICAL_PROTOCOL_VERIFIED` chỉ pass khi:

1. Toàn bộ domain model tối thiểu serialize/validate được.
2. Các invariant trong roadmap có automated test.
3. Revision và approval không thể silently mutate.
4. Event schema có idempotency/correlation metadata.
5. Ports không rò rỉ browser/provider implementation detail.
6. Architecture checker chứng minh không có reverse dependency.
7. Golden valid/invalid fixtures chạy trong CI.

## 24. Handoff sang Phase 4–7

Handoff package gồm:

- baseline SHA và architecture inventory;
- pinned VideoClaw SHA, content hash và adoption matrix;
- clean-room requirement IDs;
- versioned schema và fixtures;
- canonical ports và event catalog;
- danh sách rủi ro còn mở nhưng không chặn;
- migration note nếu protocol làm thay đổi storage/API hiện hữu.

Phase 4 không được bắt đầu nếu handoff thiếu upstream content hash hoặc gate Phase 3 chưa pass.

## 25. Rủi ro và biện pháp

| Rủi ro | Dấu hiệu | Biện pháp |
|---|---|---|
| Baseline không tái lập | Test khác nhau giữa hai lần chạy | Pin toolchain, ghi environment, phân loại flaky test |
| License scope mơ hồ | Item `UNKNOWN` được đưa vào intake | Fail gate, không vendor item đó |
| Clean-room bị nhiễm | Tên/schema/prompt ViMax xuất hiện trong runtime | Review provenance và loại bỏ trước implementation |
| Schema quá gắn Flow | Core chứa selector/session/credit UI field | Đẩy detail vào provider adapter |
| Schema thay đổi liên tục | Phase sau sửa trực tiếp v1 | Versioning + revision proposal + compatibility tests |
| Verdict không đáng tin | Report nói pass nhưng receipt fail | Generate verdict từ evidence manifest |

## 26. Checklist đóng kế hoạch

- [x] `VP0_BASELINE_FROZEN` — PASSED (2026-07-31). Baseline `1d98e26` (build/verify finalizer refactor) certified từ clean detached checkout: 949 passed, 3 skipped, 0 failed, **0 tracked mutations** (tree SHA `98dc0d38` không đổi). KB-003 đã đóng. Evidence: `artifacts/video_production/phase_00/baseline_verdict.json`, `phase_verdict.json`, `full_rerun_results.json`, `cleanliness_report.json`.
- [x] `VP1_UPSTREAM_ADOPTION_APPROVED` — PASSED (2026-07-31). Evidence: `artifacts/video_production/phase_01/phase_verdict.json`.
- [x] `VP2_DIRECTOR_REQUIREMENTS_FROZEN` — PASSED (2026-07-31). Evidence: `artifacts/video_production/phase_02/phase_verdict.json`.
- [x] `VP3_CANONICAL_PROTOCOL_VERIFIED` — PASSED (2026-07-31). Evidence: `artifacts/video_production/phase_03/phase_verdict.json` (34 tests, ruff F clean, architecture & duplicate-model gates clean).
- [x] Không có VideoClaw/ViMax runtime dependency — verified: 0 runtime files modified.
- [x] Protocol fixtures và validators chạy trong CI — `tests/unit/core/test_phase03_*.py` + `tests/architecture/test_phase03_video_production_architecture.py` nằm trong `tests/unit` / `tests/architecture` mà CI `python-unit-sqlite` / `python-unit-windows` đã chạy.
- [x] Handoff package đã được hash và review — PASSED (2026-07-31). Evidence: `artifacts/video_production/handoff/phase_verdict.json` (gate `VP0_3_HANDOFF_PACKAGE_VERIFIED`, SHA-256 checksums, migration note `NO_MIGRATION_REQUIRED`).
- [x] Sẵn sàng bắt đầu Phase 4 — handoff có upstream content hash `e3b0c442…2b855`, gate Phase 3 `VP3_CANONICAL_PROTOCOL_VERIFIED` pass, và VP0 `VP0_BASELINE_FROZEN` đã PASSED với baseline `1d98e26` (KB-003 resolved, không còn open risk blocking). Evidence: `artifacts/video_production/handoff/phase_verdict.json` (gate `VP0_3_HANDOFF_PACKAGE_VERIFIED`).
