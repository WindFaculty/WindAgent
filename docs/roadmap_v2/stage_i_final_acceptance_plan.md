# Kế hoạch Stage I — Final Acceptance

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | I |
| Phạm vi | UI47–UI50 |
| Kết quả chính | Golden workflows pass và Video Workspace foundation ready |
| Dependency đầu vào | Stage A–H pass trên cùng release candidate |
| Kết quả cuối | Roadmap II accepted/releasable |
| Độ phức tạp tương đối | M |

## 2. Mục tiêu

Nghiệm thu Roadmap II trên một release candidate bất biến. Stage I không bổ sung capability sản phẩm lớn; nó chứng minh:

- Script golden workflow hoàn chỉnh;
- Asset golden workflow hoàn chỉnh;
- Script ↔ Asset integrated workflow không cần thao tác ngoài hệ thống;
- revision, proposal, validation, license, event, recovery và audit invariants được giữ;
- shared infrastructure đủ để bổ sung Video Workspace bằng public package APIs;
- evidence, migration, rollback và release ownership hoàn chỉnh.

## 3. Điều kiện vào Stage

Không bắt đầu acceptance chính thức nếu thiếu một trong các điều kiện:

- candidate commit SHA đã khóa;
- Stage A–G gates pass;
- Stage H test matrix pass;
- no blocker/critical defect;
- schema/API/package/Desktop/Web versions đã ghi;
- clean database và upgrade database fixtures sẵn sàng;
- deterministic provider/job fixtures sẵn sàng;
- supported Desktop/Web runners sẵn sàng;
- evidence output location và redaction policy sẵn sàng.

## 4. Acceptance environment

### Canonical project fixture

```text
Bunny Episode 01
├── screenplay with Scene 03
├── locked revision rev_12
├── active/new draft flow
├── required: Bunny, Park, Ball
├── Bunny asset approved/eligible
├── Park asset approved/eligible
├── Ball missing
├── unknown-license negative asset
├── deterministic asset generation provider
├── event history with sequence cursor
└── proposal/activity history
```

### Environment backlog

- `I-PREP-01`: lock candidate SHA;
- `I-PREP-02`: build/version Desktop, Web, API, worker và packages;
- `I-PREP-03`: seed clean database fixture;
- `I-PREP-04`: prepare previous-schema upgrade fixture;
- `I-PREP-05`: configure deterministic fake generator/resolver;
- `I-PREP-06`: configure artifact/media storage;
- `I-PREP-07`: resettable event sequence/project fixture;
- `I-PREP-08`: enable sanitized logs/traces/screenshots;
- `I-PREP-09`: verify license/security policies active;
- `I-PREP-10`: smoke non-Production screens;
- `I-PREP-11`: create acceptance run manifest;
- `I-PREP-12`: assign approver/go-no-go owner.

## 5. Kế hoạch UI47 — Script Golden Workflow

### Workflow

```text
Create/open screenplay
→ Structured edit
→ Save edit unit
→ Switch to Text mode
→ Text edit
→ Parse + semantic diff
→ Apply candidate
→ Request AI revision proposal
→ Preview diff/impact
→ Human approve
→ Validate
→ Lock
→ Attempt edit on locked screenplay
→ Create new draft revision
→ Apply edit to new draft
```

### Execution checklist

- `I-UI47-01`: capture initial project/revision/screenplay hashes;
- `I-UI47-02`: structured scene/dialogue edit;
- `I-UI47-03`: verify command/idempotency/event/timeline;
- `I-UI47-04`: switch to text và perform semantic edit;
- `I-UI47-05`: verify parser diagnostics/diff/ID stability;
- `I-UI47-06`: create AI proposal;
- `I-UI47-07`: verify no canonical mutation before approval;
- `I-UI47-08`: approve proposal and verify command/revision;
- `I-UI47-09`: run validation and resolve expected warnings;
- `I-UI47-10`: lock revision;
- `I-UI47-11`: verify blocking issue policy in negative subcase;
- `I-UI47-12`: attempt edit locked revision;
- `I-UI47-13`: verify new draft lineage;
- `I-UI47-14`: verify locked ancestor hash unchanged;
- `I-UI47-15`: restart/reload and verify recovered final state;
- `I-UI47-16`: collect evidence/checksums.

### Acceptance

- structured/text semantic round-trip đúng;
- stable IDs/order giữ đúng;
- AI proposal không mutate trước approval;
- blocking validation chặn lock;
- lock thành công chỉ trên valid revision;
- edit locked tạo draft mới;
- locked ancestor hash bất biến;
- audit/timeline/replay đầy đủ;
- `VP3D_UI_SCRIPT_GOLDEN_WORKFLOW_PASSED` pass.

## 6. Kế hoạch UI48 — Asset Golden Workflow

### Workflow

```text
Asset requirement
→ acquire or generate candidate
→ download/import
→ normalize
→ generate preview
→ validate
→ attach/check license
→ approve
→ bind/use in project
→ create asset revision
→ review replacement impact
→ apply selected scope
```

### Execution checklist

- `I-UI48-01`: start from deterministic requirement;
- `I-UI48-02`: acquire/generate candidate;
- `I-UI48-03`: verify request/job idempotency;
- `I-UI48-04`: observe progress through reconnect;
- `I-UI48-05`: verify normalization report/artifact hash;
- `I-UI48-06`: verify 3D/non-3D preview as appropriate;
- `I-UI48-07`: run validation;
- `I-UI48-08`: run unknown-license negative subcase;
- `I-UI48-09`: attach valid license evidence;
- `I-UI48-10`: approve asset;
- `I-UI48-11`: bind/use in project;
- `I-UI48-12`: create new immutable asset revision;
- `I-UI48-13`: calculate affected projects/scenes/shots/rerenders;
- `I-UI48-14`: apply selected replacement scope;
- `I-UI48-15`: verify old revision/history intact;
- `I-UI48-16`: collect evidence/checksums.

### Acceptance

- candidate không auto-approve;
- provenance/license/validation đầy đủ;
- unknown license bị server chặn;
- job state recover qua reconnect/restart;
- bytes/revision cũ không overwrite;
- replacement không tự apply toàn cục;
- stale impact result bị từ chối;
- `VP3D_UI_ASSET_GOLDEN_WORKFLOW_PASSED` pass.

## 7. Kế hoạch UI49 — Script + Asset Integrated E2E

### Scenario

```text
Scene 03 requires Bunny, Park, Ball

Bunny: eligible
Park: eligible
Ball: missing

→ open missing asset resolver
→ generate/import Ball
→ normalize/validate/license/preview
→ approve Ball
→ bind Ball to Scene 03
→ rerun screenplay validation
→ lock production revision
```

### Execution checklist

- `I-UI49-01`: verify initial resource count/validation;
- `I-UI49-02`: deep-link Script requirement → Assets;
- `I-UI49-03`: acquisition/generation with prefilled requirement;
- `I-UI49-04`: complete asset lifecycle/processing;
- `I-UI49-05`: bind eligible asset revision;
- `I-UI49-06`: verify Asset Usage → Script deep-link;
- `I-UI49-07`: verify both projections after event replay;
- `I-UI49-08`: verify requirement closed/resource counts updated;
- `I-UI49-09`: revalidate screenplay;
- `I-UI49-10`: lock revision;
- `I-UI49-11`: restart/reload and verify same state;
- `I-UI49-12`: verify activity timeline/correlation;
- `I-UI49-13`: assert no direct DB edit;
- `I-UI49-14`: assert no direct JSON edit;
- `I-UI49-15`: assert no manual filesystem copy;
- `I-UI49-16`: collect integrated evidence.

### Acceptance

- project/revision context không drift qua navigation;
- requirement→candidate→asset→binding→validation traceable;
- Script/Asset projections converge;
- license/validation enforce server-side;
- lock chỉ thành công sau requirement được giải quyết;
- `VP3D_UI_SCRIPT_ASSET_INTEGRATION_PASSED` pass.

## 8. Kế hoạch UI50 — Video Workspace Foundation Ready

Roadmap II không xây Video page đầy đủ. UI50 là architecture readiness audit.

### Required public capabilities

```text
ProductionProjectContext
ProductionRevisionContext
Event Stream + replay
Jobs
Asset Binding
Scene IDs + Shot IDs
Artifact Preview
Approval/Proposal
Impact/Invalidation
Routing/deep-link
Recovery/conflict primitives
```

### Audit backlog

- `I-UI50-01`: audit public package exports;
- `I-UI50-02`: audit project/revision/scene/shot contracts;
- `I-UI50-03`: audit video event namespace extension;
- `I-UI50-04`: audit job state/projectors;
- `I-UI50-05`: audit artifact preview registry;
- `I-UI50-06`: audit approval/proposal composition;
- `I-UI50-07`: audit invalidation/impact link to shot/render;
- `I-UI50-08`: audit route codec supports video/shot/artifact;
- `I-UI50-09`: create `production-ui/video/` placeholder;
- `I-UI50-10`: placeholder imports only public APIs;
- `I-UI50-11`: architecture test cấm import internal Script/Assets modules;
- `I-UI50-12`: build placeholder in Desktop/Web;
- `I-UI50-13`: document Video Workspace follow-up backlog;
- `I-UI50-14`: confirm no third frontend architecture required.

### Acceptance

- Video placeholder dùng existing shell/context/route/event/job/preview;
- không copy Script/Asset private state;
- scene/shot/artifact IDs có public contracts;
- future package path đủ: `production-ui/video/`;
- `VP3D_UI_VIDEO_WORKSPACE_FOUNDATION_READY` pass.

## 9. Cross-platform acceptance matrix

| Workflow | Desktop | Web |
| --- | --- | --- |
| Script golden | Bắt buộc | Bắt buộc |
| Asset golden | Bắt buộc | Bắt buộc |
| Integrated golden | Bắt buộc | Bắt buộc |
| Native file picker | Bắt buộc | N/A |
| Browser File API | N/A | Bắt buộc |
| Restart/recovery | Tauri restart | Reload/browser restart |
| Deep-link | Desktop route host | URL/history |
| Preview | Shared viewer | Shared viewer |

Platform-specific differences chỉ nằm ở adapter; business outcomes phải tương đương.

## 10. Evidence bundle

```text
artifacts/production_ui/final_acceptance/<candidate_sha>/
├── run_manifest.json
├── versions.json
├── environment.json
├── stage_gate_summary.json
├── script_golden_receipt.json
├── asset_golden_receipt.json
├── integrated_golden_receipt.json
├── video_foundation_receipt.json
├── migration_receipt.json
├── security_license_receipt.json
├── desktop_e2e/
├── web_e2e/
├── sanitized_logs/
└── checksums.json
```

Mỗi receipt cần:

- candidate SHA;
- app/API/schema/contract versions;
- command/test name;
- start/end timestamps;
- expected/actual result;
- exit status;
- related artifact/checksum;
- approver/verdict.

## 11. Release readiness

### Migration

- clean install migration pass;
- supported previous schema upgrade pass;
- migration restart/idempotency pass;
- no locked revision/asset hash changes ngoài migration policy;
- rollback/forward-fix strategy documented.

### Operations

- health/readiness checks include required storage/event components;
- metrics/alerts cho command conflicts, event gaps, job failure;
- artifact storage capacity/retention documented;
- support diagnostics redacted;
- feature flag/route entry disable path tested.

### Rollback

- xác định code rollback vs schema forward-fix;
- không rollback làm mất revision/event mới;
- Production entry point có thể disable mà không phá page cũ;
- client/server compatibility window documented;
- owner và go/no-go authority rõ.

## 12. Go/No-Go criteria

### Go

- tất cả required gates pass trên cùng candidate;
- no blocker/critical defect;
- Desktop/Web outcomes tương đương;
- migration/recovery/security/license pass;
- evidence reproducible/redacted;
- rollback/disable procedure xác nhận;
- Video foundation audit pass.

### No-Go

- locked revision hoặc asset bytes bị mutate;
- idempotency double execution;
- sequence gap silently ignored;
- agent direct sensitive mutation;
- unknown license có thể final-use;
- recovery cache overwrite server;
- Script/Asset projections không converge;
- một consumer không chạy shared package;
- evidence không tái tạo được.

## 13. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Acceptance biến thành phát triển tính năng mới | freeze scope, defect-only candidate |
| Golden test chỉ chạy một platform | matrix bắt buộc Desktop/Web |
| Provider ngoài gây flaky | deterministic fake; live smoke riêng |
| Evidence pass từ commit khác | SHA/version trong mọi receipt |
| Migration làm đổi immutable history | pre/post hashes |
| Video readiness chỉ là tuyên bố | placeholder build + architecture tests |
| Rollback phá dữ liệu mới | forward-fix/schema compatibility plan |

## 14. Final checklist

- [ ] Entry conditions được xác nhận.
- [ ] UI47 Script golden pass.
- [ ] UI48 Asset golden pass.
- [ ] UI49 integrated golden pass.
- [ ] UI50 Video foundation audit pass.
- [ ] Desktop/Web acceptance matrix pass.
- [ ] Migration clean/upgrade pass.
- [ ] Security/license/recovery negative checks pass.
- [ ] Evidence bundle complete và checksummed.
- [ ] No blocker/critical defect.
- [ ] Rollback/disable procedure tested.
- [ ] Go/No-Go owner ký verdict.

## 15. Stage outcome

Khi toàn bộ checklist pass, Roadmap II đạt trạng thái:

```text
SCRIPT WORKSPACE READY
ASSET MANAGER READY
SCRIPT ↔ ASSET INTEGRATION READY
DESKTOP/WEB SHARED UI VERIFIED
VIDEO WORKSPACE FOUNDATION READY
ROADMAP II ACCEPTED
```
