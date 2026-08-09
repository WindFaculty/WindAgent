# Kế hoạch Stage H — Testing & Verification

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | H |
| Phạm vi | UI41–UI46 |
| Kết quả chính | Test matrix và release evidence cho Desktop/Web |
| Dependency đầu vào | Capability A–G có release candidate |
| Khởi động sớm | Contract/unit tests bắt đầu từ Stage A/B |
| Bàn giao cho | Stage I |
| Độ phức tạp tương đối | XL |

## 2. Mục tiêu

Chứng minh Roadmap II đúng ở cả contract, domain invariants, shared UI và hai consumer. Stage H không phải thời điểm bắt đầu viết test; test thuộc Definition of Done của từng Phase. Stage H hoàn thiện:

- schema/contract compatibility;
- Script/Asset behavioral coverage;
- shared package consumer parity;
- Desktop Tauri E2E;
- browser E2E;
- negative/security/recovery/concurrency lanes;
- evidence bundle có thể tái tạo.

## 3. Quality principles

1. Invariant quan trọng phải có test tầng domain/API, không chỉ E2E.
2. Parser/diff/projection/recovery phải có pure deterministic tests.
3. Cùng behavioral fixture chạy trong Desktop và Web khi behavior shared.
4. External provider dùng deterministic fake trong blocking CI; live smoke là lane riêng.
5. Test failure phải tạo artifact đủ debug nhưng không chứa secret.
6. Không dùng snapshot UI lớn để thay assertion behavior.
7. Không skip platform lane để đạt gate giả.

## 4. Test pyramid

```text
             Golden E2E
        Desktop / Browser E2E
      API + DB + Event integration
   Shared component / consumer tests
 Domain / parser / reducer / contract unit
```

Mục tiêu là nhiều test deterministic ở đáy; E2E chỉ giữ canonical workflows và platform boundaries.

## 5. Environment và fixtures

### Environments

- Python unit/no database;
- SQLite integration;
- Postgres integration;
- shared frontend happy-dom/browser-like;
- browser E2E;
- Tauri/Desktop E2E;
- deterministic worker/provider fakes;
- optional live provider smoke.

### Canonical fixtures

```text
Bunny Episode 01
├── revisions: locked ancestor + active draft
├── scenes: dialogue, locations, props
├── assets: Bunny, Park, missing Ball
├── license: approved, unknown, incompatible examples
├── jobs: success, retryable failure, terminal failure
├── proposals: pending, stale, approved, rejected
└── events: replay, duplicate, gap scenarios
```

### Backlog nền

- `H-BASE-01`: fixture builders cho project/revision/screenplay/asset/job/proposal;
- `H-BASE-02`: deterministic IDs/timestamps/sequences;
- `H-BASE-03`: database seed/reset helpers;
- `H-BASE-04`: fake asset resolver/generator;
- `H-BASE-05`: event disconnect/gap/duplicate injection;
- `H-BASE-06`: API stale/timeout/failure injection;
- `H-BASE-07`: screenshot/video/trace/log artifact policy;
- `H-BASE-08`: secret/path redaction checks;
- `H-BASE-09`: flake retry/quarantine policy không che regression.

## 6. Kế hoạch UI41 — Contract Tests

### Backlog

- `H-UI41-01`: generate TypeScript types từ OpenAPI/JSON Schema;
- `H-UI41-02`: CI check generated files clean/up-to-date;
- `H-UI41-03`: Python response fixture → TS runtime decoder tests;
- `H-UI41-04`: command envelope fixture tests;
- `H-UI41-05`: event envelope fixture tests;
- `H-UI41-06`: RFC 7807/error code fixture tests;
- `H-UI41-07`: add optional field compatibility;
- `H-UI41-08`: remove required field failure;
- `H-UI41-09`: enum mismatch/unknown handling;
- `H-UI41-10`: invalid revision/status tests;
- `H-UI41-11`: snapshot current sequence contract;
- `H-UI41-12`: no filesystem path/secret contract assertions;
- `H-UI41-13`: schema diff report;
- `H-UI41-14`: version-breaking change approval mechanism.

### Acceptance

- backend/frontend contract drift bị CI phát hiện;
- fixtures đại diện success/error/stale/permission;
- breaking change chưa version chặn merge;
- schema generation deterministic.

## 7. Kế hoạch UI42 — Script Behavioral Tests

### Read/layout/navigation

- load empty/normal/large screenplay;
- select scene và deep-link;
- reload/back/forward;
- inspector/editor/tree synchronization;
- accessibility/focus/keyboard.

### Structured editor

- title/logline edit;
- scene add/delete/duplicate/split/merge/reorder;
- dialogue add/delete/reorder/edit;
- temporary/stable IDs;
- undo/redo;
- local/server validation.

### Text/hybrid

- serialize/parse golden corpus;
- malformed/ambiguous diagnostics;
- Unicode/line endings;
- stable scene/dialogue IDs;
- metadata/order preservation;
- repeated mode switching;
- `PARSE_REQUIRES_REVIEW`.

### Revision/draft

- local modified/save/ack/failure;
- double submit/idempotency;
- edit locked → new draft;
- locked ancestor hash immutable;
- semantic revision diff;
- impact/stale impact;
- validation/lock TOCTOU.

### AI/proposal/conflict

- proposal create/preview/approve/reject;
- no mutation before approve;
- stale proposal;
- agent bypass;
- reconnect/replay;
- stale save/merge/discard;
- restart/recovery.

### Required layers

- parser/serializer/diff/reducer: unit/property/golden;
- editor components: component tests;
- revision/lock/proposal: API integration;
- full flow: one E2E per consumer where needed.

## 8. Kế hoạch UI43 — Asset Behavioral Tests

### Library/query

- list/search/filter/sort/pagination;
- project permission filtering;
- large library/virtualization;
- selection race/loading/empty/error.

### Asset domain/commands

- taxonomy compatibility;
- immutable revision/content hash;
- lifecycle transitions;
- processing state independence;
- import/upload invalid/duplicate;
- normalize/validate;
- approve/reject/archive/version;
- idempotency/restart/concurrency.

### Governance/preview

- provenance fields/redaction;
- license unknown/expired/revoked/incompatible;
- final-production server block;
- 3D supported/oversized/invalid/WebGL unavailable;
- image/audio/animation/material/camera/light preview;
- signed URL expiry;
- GPU/media cleanup.

### Acquisition/jobs

- upload cancel/permission denied;
- URL validation/SSRF rejection;
- library reuse;
- generation request/candidate;
- progress/replay/restart;
- cancel/retryable/terminal failure;
- no blind retry/no duplicate job.

### Binding/dependency/version

- eligible/ineligible bind;
- unbind/history;
- usage/dependency/cycle;
- cross-navigation;
- replacement impact/stale impact;
- partial failure consistency.

## 9. Kế hoạch UI44 — Shared Package Consumer Tests

### Backlog

- `H-UI44-01`: package unit/component suite độc lập;
- `H-UI44-02`: browser consumer harness;
- `H-UI44-03`: Desktop/Tauri consumer harness;
- `H-UI44-04`: same fixture/behavior adapter matrix;
- `H-UI44-05`: production package exports test;
- `H-UI44-06`: single React runtime check;
- `H-UI44-07`: no Tauri import in shared packages;
- `H-UI44-08`: no direct browser file API outside adapter;
- `H-UI44-09`: route codec parity;
- `H-UI44-10`: event projection parity;
- `H-UI44-11`: visual snapshots cho critical components;
- `H-UI44-12`: bundle/platform dependency report;

### Acceptance

```text
production-ui browser test PASS
production-ui desktop test PASS
```

Pass chỉ khi cùng public package build được trong cả hai consumer, không phải hai bản copy source.

## 10. Kế hoạch UI45 — Desktop E2E

### Golden Desktop lane

```text
Launch Tauri
→ API/sidecar ready
→ open Production
→ select project
→ Script structured/text edit
→ create/lock revision
→ Assets import GLB via native picker
→ normalize/validate/license/preview/approve
→ bind to screenplay entity
→ restart app/API as specified
→ recover context/draft/events
→ verify timeline and state
```

### Negative Desktop lanes

- native picker cancel;
- native permission denied;
- unsupported/reveal file capability;
- sidecar unavailable/restart;
- network timeout after command submit;
- replay after disconnect;
- stale revision conflict;
- GPU/WebGL preview fallback;
- restart with valid/corrupt recovery snapshot;
- old screens/sidebar regression.

### Evidence

- app/API versions;
- database/schema version;
- test trace/screenshots/video on failure;
- sanitized logs;
- commands/exit codes;
- artifact checksums.

## 11. Kế hoạch UI46 — Browser E2E

### Golden Browser lane

Chạy workflow tương đương Desktop nhưng:

- import qua browser File API + HTTP;
- không Tauri/native/internal path;
- history/deep-link/reload hoạt động;
- reconnect/replay hoạt động;
- same shared Production UI behavior.

### Negative Browser lanes

- file input cancel/invalid/oversized;
- HTTP upload failure/retry;
- browser offline/online;
- refresh with dirty draft;
- two-tab stale conflict;
- direct link unauthorized/deleted entity;
- signed URL expired;
- WebGL unavailable;
- storage quota/corrupt recovery;
- event cursor gap.

## 12. Non-functional verification

### Performance budgets cần chốt bằng baseline

- workspace snapshot latency/size;
- asset list query latency;
- event projection/replay lag;
- large screenplay interaction;
- large asset library scroll/filter;
- preview load/memory cleanup;
- frontend bundle delta;
- Desktop startup impact.

### Accessibility

- keyboard-only navigation;
- focus restore trong modal/panes;
- labels/descriptions/errors;
- contrast/status không chỉ bằng màu;
- media controls;
- virtualized list semantics;
- screen reader announcement save/conflict/job state.

### Security/privacy

- project/route/event authorization;
- upload/content/URL validation;
- SSRF/path traversal checks;
- signed artifact access;
- license enforcement bypass;
- agent direct mutation bypass;
- local recovery secret scanning;
- log/timeline redaction.

## 13. CI matrix

| Job | Trigger | Blocking |
| --- | --- | --- |
| Python unit | PR | Có |
| SQLite integration | PR | Có |
| Postgres integration | PR/release | Có cho release |
| Contract generation/diff | PR | Có |
| Shared frontend unit/component | PR | Có |
| Web build/consumer | PR | Có |
| Desktop build/consumer | PR hoặc supported runner | Có |
| Browser E2E core | PR/release | Có |
| Desktop E2E core | release candidate | Có |
| Security negative suite | PR/release | Có |
| Live provider smoke | scheduled/manual | Không thay fake blocking lane |

## 14. Defect policy

- blocker/critical: không được waive Stage I;
- invariant violation lock/idempotency/license/permission: blocker;
- flaky test phải có root cause/quarantine expiry, không retry vô hạn;
- defect fix phải thêm regression test tầng thấp nhất phù hợp;
- known failure cần owner, issue, impact và decision rõ;
- evidence thiếu/tái tạo không được xem là PASS.

## 15. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| E2E quá nhiều/flaky | test pyramid + deterministic fakes |
| Desktop lane bị bỏ qua | dedicated supported runner/release gate |
| Fixtures lệch production contract | generate từ schema/domain builders |
| Snapshot tests che behavior | explicit semantic assertions |
| Live provider gây CI bất ổn | fake blocking, live separate |
| Logs/evidence lộ secret | redaction + scanning |
| Retry che race bug | bounded retry và failure artifact |

## 16. Stage gate và exit checklist

Gate đề xuất:

```text
VP3D_UI_TEST_MATRIX_VERIFIED
```

- [ ] UI41 contract generation/diff/decoder tests pass.
- [ ] UI42 Script behavior và invariants pass.
- [ ] UI43 Asset behavior và governance pass.
- [ ] UI44 same shared package passes browser/desktop.
- [ ] UI45 Desktop golden + negative core lanes pass.
- [ ] UI46 Browser golden + negative core lanes pass.
- [ ] Recovery/concurrency/security lanes pass.
- [ ] Performance/accessibility budgets evaluated.
- [ ] No blocker/critical defect open.
- [ ] Evidence bundle reproducible and redacted.
- [ ] Gate `VP3D_UI_TEST_MATRIX_VERIFIED` pass.

## 17. Bàn giao sang Stage I

Stage I nhận:

- immutable release candidate SHA;
- schema/API/package/app versions;
- deterministic golden fixtures;
- test/evidence bundle;
- defect/risk register;
- exact acceptance commands;
- release/rollback checklist draft.
