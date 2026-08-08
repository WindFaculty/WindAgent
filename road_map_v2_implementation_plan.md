# Kế hoạch triển khai chi tiết Roadmap II — WindAgent Production Frontend

## 1. Mục tiêu tài liệu

Tài liệu này chuyển `road_map_v2.md` thành kế hoạch có thể triển khai và nghiệm thu cho toàn bộ Stage A–I, bao phủ UI Phase 0–50.

Kết quả cuối cùng cần đạt được:

- một Production Workspace dùng chung cho Desktop và Web;
- Script Workspace hỗ trợ structured mode, text mode, revision bất biến và AI proposal;
- Universal Asset Manager quản lý asset, provenance, license, preview, generation job và dependency;
- Script và Asset liên kết hai chiều trong cùng project/revision context;
- realtime, recovery và conflict handling có thể chứng minh bằng test;
- nền tảng sẵn sàng để bổ sung Video Workspace mà không tạo kiến trúc frontend thứ ba.

Tài liệu này không thay thế roadmap kiến trúc. `road_map_v2.md` vẫn là nguồn quyết định sản phẩm; tài liệu này là execution plan.

---

## 2. Baseline codebase và giả định triển khai

### 2.1 Baseline được quan sát

Baseline dùng khi viết kế hoạch:

```text
HEAD: 5662edee35893876264a599a9480cafb531466f1
Ngày đối chiếu: 2026-08-08
```

Các điểm có thể tái sử dụng:

- `core/windagent_core/domain/video_production/` đã có Production IR và nhiều capability 3D/audio/animation/asset normalization;
- screenplay identifiers/status và các cấu trúc scene/dialogue đã tồn tại trong production domain;
- `AssetLifecycleState`, `AssetStateMachine`, asset resolution và normalization đã có nền tảng;
- `apps/api/windagent_api/routers/v2_events.py` đã có SSE, WebSocket và replay theo `last_sequence`;
- `apps/web/src/clients/event_stream_client.ts` đã có event deduplication/client skeleton;
- `apps/web/src/state/state_recovery.ts` đã có recovery skeleton;
- Desktop đã có shell, sidebar, API client và nhiều màn hình hiện hữu cần được giữ nguyên;
- Web đã có application skeleton nhưng nhỏ hơn đáng kể so với Desktop.

Các khoảng trống chính:

- chưa có `frontend/` workspace và các shared production package;
- chưa có Production Workspace API/runtime route hoàn chỉnh theo Roadmap II;
- chưa có shared Script Workspace hoặc Asset Manager;
- chưa có project/revision context thống nhất giữa Script, Assets và Video;
- chưa có persistence production-grade cho workspace command/idempotency/read model;
- chưa có consumer test chứng minh cùng một Production UI chạy trong cả Desktop và Web.

Toolchain hiện chưa đồng nhất:

| Hạng mục | Desktop | Web |
| --- | --- | --- |
| React | 18.3.x | 18.2.x |
| TypeScript | 5.6.x | 5.2.x |
| Vite | 5.4.x | 5.1.x |
| Vitest | 4.1.x | 1.4.x |
| State | Redux Toolkit + Zustand | Redux Toolkit |

### 2.2 Lưu ý về baseline freeze

Working tree tại thời điểm lập kế hoạch có nhiều thay đổi và artifact chưa commit. Vì vậy UI0 không được ghi nhận `HEAD` hiện tại là baseline một cách máy móc. Trước khi freeze phải:

1. phân loại thay đổi nào thuộc Roadmap I/3D đang tiếp tục;
2. chọn một candidate SHA hoặc tạo baseline manifest có danh sách file thay đổi được chấp nhận;
3. chạy test từ candidate đó;
4. lưu receipt tái tạo được.

Không sửa, xóa hoặc reset các thay đổi hiện hữu chỉ để tạo baseline UI.

### 2.3 Giả định tổ chức

Kế hoạch dùng ba workstream logic:

- Platform/API: domain, repository, migration, API, event và security;
- Production UI: shared packages, Script, Assets, integration và recovery;
- Verification: contract, component, integration, E2E, performance và release evidence.

Một người có thể đảm nhiệm nhiều workstream. Kích thước `S/M/L/XL` trong tài liệu là độ phức tạp tương đối, không phải cam kết ngày công.

---

## 3. Nguyên tắc thực thi bắt buộc

1. Backend production domain là source of truth.
2. `LOCKED` revision không bao giờ bị sửa tại chỗ.
3. Mọi mutation đi qua canonical command, revision check, idempotency và domain validation.
4. AI chỉ tạo proposal; proposal không phải canonical state.
5. Asset có license không hợp lệ hoặc chưa rõ phải fail closed ở final-production boundary.
6. Shared Production UI không import Tauri hoặc browser API trực tiếp.
7. Text screenplay chỉ là representation của structured screenplay.
8. Snapshot và event stream phải tạo cùng một chuỗi state không gap và không double-apply.
9. Không trả filesystem path nội bộ ra API.
10. Stage H không phải lúc bắt đầu viết test; test được làm cùng từng Phase, Stage H là giai đoạn hoàn thiện ma trận và E2E.

---

## 4. Definition of Ready và Definition of Done

### 4.1 Definition of Ready cho một Phase

Một Phase chỉ bắt đầu khi:

- dependency bắt buộc đã pass gate;
- API/domain contract đầu vào đã version hoặc có fixture;
- acceptance criteria và negative cases đã được ghi;
- migration/compatibility impact đã được xác định;
- có owner cho code, test và evidence.

### 4.2 Definition of Done chung

Một Phase hoàn tất khi:

- code, migration và generated contract liên quan đã hoàn tất;
- unit test và integration/component test pass;
- error, loading, empty, stale và permission state đã được xử lý;
- telemetry/audit không làm lộ prompt, token, filesystem path hoặc secret;
- tài liệu contract được cập nhật;
- receipt/gate tương ứng có thể tái tạo bằng lệnh CI;
- Desktop/Web không bị regression ngoài phạm vi Production.

---

## 5. Thứ tự triển khai tổng thể

```text
Wave 0: Stage A — Foundation
              |
              v
Wave 1: Stage B — API + realtime
              |
              +-------------------+
              v                   v
Wave 2A: Stage C — Script   Wave 2B: Stage D — Assets
              +-------------------+
                          |
                          v
Wave 3: Stage E + Stage F — Integration + collaboration
                          |
                          v
Wave 4: Stage G — Recovery + conflict
                          |
                          v
Wave 5: Stage H — Full verification
                          |
                          v
Wave 6: Stage I — Golden acceptance
```

Stage C và D được phép chạy song song sau UI7. Contract test của Stage H bắt đầu từ Stage B, không chờ đến cuối.

### 5.1 Ma trận dependency cấp Stage

| Stage | Dependency cứng | Có thể song song với | Kết quả |
| --- | --- | --- | --- |
| A | Baseline được chọn | Roadmap I không chạm frontend ABI | Shared foundation |
| B | A/UI1–UI3 | A/UI4 hardening | API, command, realtime |
| C | B/UI5–UI7 | D | Script Workspace |
| D | B/UI5–UI7 | C | Asset Manager |
| E | C/UI18, D/UI33 | F/timeline read model | Script ↔ Asset |
| F | B/UI6–UI7, proposal capability của C/D | E | Human/agent control |
| G | A state, B command/event, C semantic diff | F hardening | Recovery/conflict |
| H | Các capability cần test | Chạy liên tục | Verification matrix |
| I | A–H pass | Không | Release acceptance |

---

# Stage A — Shared Production Frontend Foundation

## 6. Mục tiêu Stage A

Tạo ranh giới frontend dùng chung nhưng không phá shell hiện có. Sau Stage A, Desktop và Web phải render được một Production shell tối thiểu từ cùng package, dùng adapter riêng và cùng project context.

Độ phức tạp tương đối: `L`.

## 6.1 UI0 — Baseline Freeze

### Công việc

- `A-UI0-01`: chốt candidate SHA/baseline manifest sau khi phân loại dirty worktree;
- `A-UI0-02`: inventory `apps/desktop`, `apps/web`, `apps/api`, production domain, storage, workflows và orchestration;
- `A-UI0-03`: ghi phiên bản Node/npm/Python, package manager, React, TypeScript, Vite và Vitest;
- `A-UI0-04`: chạy và lưu kết quả test Desktop, Web, API và video-production theo candidate;
- `A-UI0-05`: snapshot API V2/OpenAPI, event types, frontend state và existing route behavior;
- `A-UI0-06`: tạo smoke checklist cho Dashboard, Agents, Agent Workspace, Workflows, Browser, Files, Memory, Models, Router và Settings;
- `A-UI0-07`: định nghĩa budget regression: bundle, startup, test duration và API health;
- `A-UI0-08`: tạo evidence manifest chứa command, exit code, artifact path và timestamp.

### Deliverable

```text
artifacts/production_ui/phase_00/
├── baseline_manifest.json
├── toolchain_inventory.json
├── api_contract_snapshot.json
├── event_contract_snapshot.json
├── desktop_test_receipt.json
├── web_test_receipt.json
├── api_test_receipt.json
└── phase_verdict.json
```

### Acceptance

- baseline có thể tái tạo;
- không có file người dùng bị reset hoặc ghi đè;
- tất cả regression đã biết được ghi rõ, không bị che thành PASS;
- gate `VP3D_UI_P0_BASELINE_FROZEN` được tạo.

## 6.2 UI1 — Frontend Workspace Foundation

### Quyết định đề xuất

Dùng npm workspace tại `frontend/` và một lockfile duy nhất cho shared packages. Hai application vẫn giữ build riêng. Pin exact version trong workspace; không dùng range `^` cho ABI/tooling cốt lõi.

Redux Toolkit được dùng cho `production-state` vì cả hai app đã phụ thuộc package này. Store được export dưới dạng reducer/store factory/selectors, không yêu cầu app thay toàn bộ state hiện hữu.

### Công việc

- `A-UI1-01`: tạo root `frontend/package.json`, `package-lock.json` và workspace config;
- `A-UI1-02`: tạo package skeleton `production-contracts`, `production-client`, `production-state`, `production-platform`, `production-ui`;
- `A-UI1-03`: pin Node, npm, React, TypeScript, Vite, Vitest, Testing Library và ESLint compatibility matrix;
- `A-UI1-04`: tạo base `tsconfig`, package exports, source maps và build order;
- `A-UI1-05`: quy định dependency direction bằng architecture test;
- `A-UI1-06`: cấu hình unit/component test chung;
- `A-UI1-07`: tích hợp workspace package vào Desktop và Web bằng một component placeholder;
- `A-UI1-08`: thêm CI jobs `frontend:typecheck`, `frontend:test`, `frontend:build`;
- `A-UI1-09`: tạo package API report để phát hiện accidental export/ABI break.

### Dependency rule

```text
production-contracts
       ^
production-platform     production-client
       ^                      ^
       +------ production-state
                       ^
                 production-ui
                       ^
              apps/desktop, apps/web
```

Không package nào được import source file riêng của `apps/desktop` hoặc `apps/web`.

### Acceptance

- clean install chỉ cần một command tại `frontend/`;
- cả hai consumer build được;
- package test chạy độc lập;
- không có duplicate React runtime;
- gate `VP3D_UI_P1_FRONTEND_WORKSPACE_VERIFIED` pass.

## 6.3 UI2 — Platform Adapter Boundary

### Công việc

- `A-UI2-01`: chốt `ProductionPlatformAdapter` và capability flags;
- `A-UI2-02`: thêm typed errors cho cancel, permission denied, unsupported và transfer failure;
- `A-UI2-03`: implement `DesktopProductionPlatformAdapter` bằng Tauri API;
- `A-UI2-04`: implement `WebProductionPlatformAdapter` bằng File API/download;
- `A-UI2-05`: chuẩn hóa `SelectedFile` để không truyền raw internal path vào domain;
- `A-UI2-06`: tạo fake adapter dùng cho component test/Storybook-like harness;
- `A-UI2-07`: thêm architecture test cấm `window.__TAURI__`, `@tauri-apps/api` và direct DOM file access trong shared UI;
- `A-UI2-08`: test cancel picker, multi-file, oversized file, download và unsupported operation.

### Acceptance

- cùng một Import component chạy dưới fake, Desktop và Web adapter;
- domain/client chỉ nhận upload handle hoặc artifact id;
- gate `VP3D_UI_P2_PLATFORM_BOUNDARY_VERIFIED` pass.

## 6.4 UI3 — Production Project Context

### Công việc

- `A-UI3-01`: định nghĩa `ProductionProjectContextState` và runtime validation schema;
- `A-UI3-02`: tạo reducer, selectors và actions cho project/revision/screenplay/sequence/sync/backend status;
- `A-UI3-03`: tạo bootstrap flow: decode route → fetch project → fetch workspace → connect events;
- `A-UI3-04`: chặn render editor khi project và revision chưa coherent;
- `A-UI3-05`: implement explicit project switch, unsaved-change guard và context reset;
- `A-UI3-06`: thêm header hiển thị project, revision, lock, sequence và backend state;
- `A-UI3-07`: test không thể vô tình mở Script project A và Assets project B trong cùng workspace;
- `A-UI3-08`: định nghĩa context extension point cho Video Workspace.

### Acceptance

- Script, Assets và placeholder Video đọc cùng một context;
- project switch có confirmation nếu có local draft;
- context lỗi/stale không silently fallback sang project khác.

## 6.5 UI4 — Production Routing

### Công việc

- `A-UI4-01`: tạo `ProductionRoute` và codec parse/serialize dùng chung;
- `A-UI4-02`: hỗ trợ `projectId`, `page`, `entityId`, `revisionId` và view-specific query;
- `A-UI4-03`: Web map codec vào browser URL/history;
- `A-UI4-04`: Desktop map codec vào navigation state/deep-link handler;
- `A-UI4-05`: thêm Production group vào sidebar mà không đổi behavior page cũ;
- `A-UI4-06`: tạo not-found, missing-project và inaccessible-revision states;
- `A-UI4-07`: test back/forward, reload, direct link và Script ↔ Assets placeholder navigation;
- `A-UI4-08`: cấm component tự nối route string thủ công.

### Stage A gate

Stage A hoàn tất khi:

- Desktop và Web render cùng `ProductionShell`;
- adapter boundary test pass;
- project context và route round-trip test pass;
- smoke test màn hình cũ pass;
- gate `VP3D_UI_P4_PRODUCTION_NAVIGATION_VERIFIED` pass.

---

# Stage B — Production API Foundation

## 7. Mục tiêu Stage B

Thay PoC/in-memory semantics bằng application service và repository thật; cung cấp snapshot, canonical command và event replay để frontend có một protocol duy nhất.

Độ phức tạp tương đối: `XL`.

## 7.1 Nền persistence và application service dùng chung

Trước UI5/UI6, hoàn thành các logical persistence contract sau. Tên bảng vật lý có thể điều chỉnh theo storage convention hiện hữu.

| Logical record | Mục đích |
| --- | --- |
| ProductionProject | project identity và lifecycle |
| ProductionRevision | parent, status, sequence, content hash |
| ProductionReadModel | workspace projection theo revision |
| ProductionIdempotencyRecord | key, request hash, response, expiry |
| ProductionDomainEvent | sequence, aggregate, revision, payload |
| ProjectionCheckpoint | consumer/read-model offset |

### Công việc nền

- `B-BASE-01`: inventory repository/UoW/event store hiện có và tái sử dụng `SqlEventStore` nơi phù hợp;
- `B-BASE-02`: định nghĩa repository ports trong core/application boundary;
- `B-BASE-03`: implement SQLite và Postgres migration/repository theo convention hiện tại;
- `B-BASE-04`: transaction boundary phải bao gồm mutation, event append và idempotency result;
- `B-BASE-05`: thêm optimistic concurrency trên revision/version;
- `B-BASE-06`: tạo fixture factory cho project/revision/screenplay/asset;
- `B-BASE-07`: test restart process không làm mất revision hoặc idempotency record.

## 7.2 UI5 — Production Query API

### Công việc backend

- `B-UI5-01`: tạo project detail query service;
- `B-UI5-02`: tạo `ProductionWorkspaceView` projector;
- `B-UI5-03`: expose `GET /api/v2/video-production/projects/{project_id}`;
- `B-UI5-04`: expose `GET /api/v2/video-production/projects/{project_id}/workspace`;
- `B-UI5-05`: trả `current_sequence` lấy cùng consistency boundary với snapshot;
- `B-UI5-06`: chuẩn hóa RFC 7807 cho not found, forbidden, stale projection và backend unavailable;
- `B-UI5-07`: loại filesystem path, raw provider secret và internal prompt khỏi DTO;
- `B-UI5-08`: hỗ trợ conditional request/ETag nếu projection lớn;
- `B-UI5-09`: generate OpenAPI schema và TS contract.

### Công việc frontend

- `B-UI5-10`: implement `projectClient` và typed runtime decoder;
- `B-UI5-11`: map loading/empty/error/stale state vào project store;
- `B-UI5-12`: không để component tự join nhiều endpoint cho initial workspace.

### Acceptance

- snapshot luôn có project, active revision, screenplay summary, asset summary, pipeline summary và sequence;
- snapshot không chứa internal path;
- contract fixture decode được ở TypeScript;
- database restart không thay đổi response semantics.

## 7.3 UI6 — Canonical Command API

### Công việc backend

- `B-UI6-01`: định nghĩa `ProductionCommandEnvelope` và discriminated payload schema;
- `B-UI6-02`: tạo command registry/handler thay vì endpoint mutation rải rác;
- `B-UI6-03`: validate `X-Idempotency-Key`, request hash và key reuse mismatch;
- `B-UI6-04`: kiểm tra project, target revision, revision status và permission;
- `B-UI6-05`: trả `409 REJECTED_STALE` kèm current revision/sequence, không tự merge;
- `B-UI6-06`: từ chối mutation vào `LOCKED` revision;
- `B-UI6-07`: commit domain state, event và idempotency response trong một transaction;
- `B-UI6-08`: trả updated revision/snapshot delta và correlation id;
- `B-UI6-09`: audit actor type `HUMAN | AGENT | SYSTEM`;
- `B-UI6-10`: rate/size limit cho command payload.

### Công việc frontend

- `B-UI6-11`: implement `commandClient` sinh idempotency key theo user intent;
- `B-UI6-12`: chỉ retry network-safe khi chưa nhận response và giữ nguyên key;
- `B-UI6-13`: map 409 vào conflict state, không blind retry;
- `B-UI6-14`: tạo command lifecycle `IDLE/SUBMITTING/ACKNOWLEDGED/CONFLICT/FAILED`;
- `B-UI6-15`: component chỉ dispatch typed command, không gọi fetch mutation trực tiếp.

### Acceptance

- cùng key + cùng payload trả cùng result và không double event;
- cùng key + khác payload bị từ chối;
- stale revision không mutate dữ liệu;
- locked revision không mutate dữ liệu;
- event sequence tăng đúng một lần cho command thành công.

## 7.4 UI7 — Real-time Production Synchronization

### Chiến lược

Tái sử dụng SSE/WebSocket replay đã có, nhưng bổ sung production event filter, typed event contract và shared client. Không tạo event subsystem thứ hai.

### Công việc

- `B-UI7-01`: inventory exact route và semantics của `v2_events.py`;
- `B-UI7-02`: chốt canonical production event envelope;
- `B-UI7-03`: thêm project/revision/aggregate metadata vào event;
- `B-UI7-04`: hỗ trợ subscribe từ `last_sequence` và filter theo project;
- `B-UI7-05`: chuyển Web event client skeleton vào `production-client` hoặc bọc bằng shared implementation;
- `B-UI7-06`: implement state machine `CONNECTED/RECONNECTING/REPLAYING/STALE/OFFLINE`;
- `B-UI7-07`: implement idempotent event projection và bounded dedupe cache;
- `B-UI7-08`: phát hiện sequence gap, dừng apply và refetch snapshot;
- `B-UI7-09`: exponential backoff có jitter, online/offline awareness và cancellation;
- `B-UI7-10`: test disconnect sau N, replay N+1..M, duplicate, out-of-order và expired cursor;
- `B-UI7-11`: expose sync indicator và manual reconnect/refetch action;
- `B-UI7-12`: ghi metrics reconnect count, replay size, projection lag và gap count.

### Stage B gate

- snapshot + event replay tạo state cuối giống fresh snapshot;
- command/idempotency/revision integration test pass trên SQLite và Postgres lane được hỗ trợ;
- Web và Desktop dùng cùng client/projection;
- gate `VP3D_UI_P7_REALTIME_STATE_VERIFIED` pass.

---

# Stage C — Screenplay Workspace

## 8. Mục tiêu Stage C

Tạo Script Workspace có thể dùng trong production: structured edit, text edit có round-trip, draft/lock revision, semantic diff, impact, AI proposal và validation gate.

Độ phức tạp tương đối: `XXL`.

## 8.1 UI8 — Screenplay Read Model

- `C-UI8-01`: map domain screenplay hiện có sang `ScreenplayWorkspaceView`;
- `C-UI8-02`: gom screenplay, ordered scenes, dialogue, characters, locations, validation, duration, revision và downstream bindings;
- `C-UI8-03`: giữ stable id và explicit order trong DTO;
- `C-UI8-04`: thêm `GET .../screenplay` hoặc embed projection đầy đủ trong workspace query theo size budget;
- `C-UI8-05`: tạo incremental projector cho scene/dialogue events;
- `C-UI8-06`: tạo TypeScript decoder, normalizer và selectors;
- `C-UI8-07`: test projection từ empty, legacy-migrated, large và invalid screenplay;
- `C-UI8-08`: benchmark projection để tránh N+1 query.

## 8.2 UI9 — Script Workspace Layout

- `C-UI9-01`: dựng `ScreenplayWorkspace` với header, story tree, editor, inspector và bottom panel;
- `C-UI9-02`: implement resize/collapse cho ba pane;
- `C-UI9-03`: hỗ trợ keyboard navigation và focus management;
- `C-UI9-04`: định nghĩa responsive mode cho Web nhỏ, không ép desktop layout vào mobile width;
- `C-UI9-05`: tạo skeleton, empty, permission denied, offline và corrupted-view state;
- `C-UI9-06`: preserve selected scene/editor mode trong route/context;
- `C-UI9-07`: accessibility test cho landmark, label, focus và contrast.

## 8.3 UI10 — Structured Screenplay Editor

- `C-UI10-01`: form edit screenplay title/logline/metadata;
- `C-UI10-02`: scene editor cho title, location, time of day, action, characters và dialogue;
- `C-UI10-03`: scene add/delete/duplicate/split/merge/move/drag reorder;
- `C-UI10-04`: dialogue add/delete/reorder và character/delivery edit;
- `C-UI10-05`: dùng stable temporary id cho entity mới trước khi server acknowledge;
- `C-UI10-06`: gom user action thành edit unit, không command từng keystroke;
- `C-UI10-07`: client validation cho phản hồi nhanh nhưng server vẫn authoritative;
- `C-UI10-08`: undo/redo chỉ trong local draft buffer;
- `C-UI10-09`: test reorder, focus, selection và command payload;
- `C-UI10-10`: test large screenplay virtualization nếu scene count vượt performance budget.

## 8.4 UI11 — Text Screenplay Editor

- `C-UI11-01`: chốt grammar nội bộ cho heading, action, character, dialogue và metadata;
- `C-UI11-02`: implement serializer deterministic;
- `C-UI11-03`: implement parser trả structured candidate, diagnostics và confidence;
- `C-UI11-04`: giữ ID mapping bằng session sidecar/anchors không lộ trong text hiển thị;
- `C-UI11-05`: parse không chắc chắn phải trả `PARSE_REQUIRES_REVIEW`;
- `C-UI11-06`: hiển thị diagnostics theo dòng và semantic preview;
- `C-UI11-07`: chỉ cho Apply sau validation + diff review;
- `C-UI11-08`: không persist raw textarea như source of truth;
- `C-UI11-09`: test Unicode, line ending, empty blocks, duplicate heading và malformed dialogue.

## 8.5 UI12 — Hybrid Round-trip Contract

- `C-UI12-01`: định nghĩa semantic equivalence bỏ qua formatting nhưng giữ meaning/order/id;
- `C-UI12-02`: tạo golden corpus từ screenplay fixtures;
- `C-UI12-03`: test structured → text → structured;
- `C-UI12-04`: test text → candidate → text deterministic;
- `C-UI12-05`: property-based test cho scene/dialogue order và optional metadata;
- `C-UI12-06`: test ID stability qua nhiều lần chuyển mode;
- `C-UI12-07`: lưu parser version trong local draft để migration rõ ràng;
- `C-UI12-08`: chặn release nếu semantic round-trip corpus có regression.

## 8.6 UI13 — Screenplay Draft Editing

- `C-UI13-01`: implement local buffer state `SERVER/LOCAL_MODIFIED/SAVING/SAVED/CONFLICT`;
- `C-UI13-02`: track base revision, dirty edit units và last acknowledged command;
- `C-UI13-03`: debounce chỉ cho local derive/validation, persistence theo edit unit hoặc explicit save;
- `C-UI13-04`: navigation/project-switch guard;
- `C-UI13-05`: optimistic UI chỉ khi có deterministic rollback;
- `C-UI13-06`: recovery snapshot cho unsaved buffer;
- `C-UI13-07`: test double-click save, network timeout, duplicate response và close tab/app.

## 8.7 UI14 — Immutable LOCKED Revision

- `C-UI14-01`: server invariant từ chối mọi edit command nhắm vào locked revision;
- `C-UI14-02`: tạo `CREATE_REVISION` với `parent_revision_id` và reason;
- `C-UI14-03`: khi user edit locked view, hiển thị flow tạo draft mới trước khi apply;
- `C-UI14-04`: hiển thị lineage và active/current distinction;
- `C-UI14-05`: ngăn race tạo nhiều draft ngoài ý muốn bằng idempotency;
- `C-UI14-06`: test immutable payload/hash của mọi ancestor locked revision;
- `C-UI14-07`: audit actor/reason cho create và lock.

## 8.8 UI15 — Revision Comparison

- `C-UI15-01`: tạo semantic diff service ở backend/application layer;
- `C-UI15-02`: diff screenplay, scene, action, dialogue, character, location và bindings;
- `C-UI15-03`: group diff theo scene/entity, không chỉ theo text line;
- `C-UI15-04`: expose compare query theo two revision ids;
- `C-UI15-05`: tạo `ScreenplayDiff` UI với filter và deep-link;
- `C-UI15-06`: test add/delete/move/modify cùng lúc và stable ordering.

## 8.9 UI16 — Production Impact Analyzer

- `C-UI16-01`: mở rộng `InvalidationIntent` thành `ScreenplayChangeImpact` projection;
- `C-UI16-02`: map changed entity sang shot/audio/animation/asset/render dependencies;
- `C-UI16-03`: phân biệt exact impact, conservative estimate và unknown;
- `C-UI16-04`: tạo dry-run command hoặc impact query trước commit;
- `C-UI16-05`: hiển thị impact summary và drill-down;
- `C-UI16-06`: yêu cầu confirmation cho destructive/high-cost invalidation;
- `C-UI16-07`: test impact không bỏ sót downstream binding.

## 8.10 UI17 — AI-assisted Screenplay Editing

- `C-UI17-01`: định nghĩa `ScriptRevisionProposal` contract;
- `C-UI17-02`: tạo selection/instruction request với bounded context;
- `C-UI17-03`: validate output thành structured candidate, không nhận raw mutation;
- `C-UI17-04`: chạy semantic diff và impact analyzer;
- `C-UI17-05`: UI preview APPROVE/REJECT với actor/model metadata phù hợp policy;
- `C-UI17-06`: approve phát canonical command nhắm đúng revision;
- `C-UI17-07`: stale proposal phải rebase/review lại, không auto-apply;
- `C-UI17-08`: test prompt injection content không vượt command/permission boundary.

## 8.11 UI18 — Screenplay Validation Gate

- `C-UI18-01`: hợp nhất validator cho order, location, character, dialogue, duration, continuity, story, production và required references;
- `C-UI18-02`: chuẩn hóa severity `BLOCKING/WARNING/INFO`, code, entity id và remediation;
- `C-UI18-03`: expose validate command/query và cache theo revision hash;
- `C-UI18-04`: UI summary, filter, click-to-entity và rerun;
- `C-UI18-05`: `LOCK_REVISION` bắt buộc chạy server validation trong cùng consistency boundary;
- `C-UI18-06`: blocking count > 0 luôn disable/reject lock;
- `C-UI18-07`: validation tạo `AssetRequirement[]` cho Stage E;
- `C-UI18-08`: test TOCTOU: revision đổi giữa validate và lock.

### Stage C gate

- structured và text editor dùng cùng canonical structured model;
- round-trip corpus giữ semantic và stable IDs;
- locked revision không đổi hash sau mọi negative test;
- AI proposal không mutate trước approval;
- blocking validation chặn lock;
- gate `VP3D_UI_SCRIPT_WORKSPACE_VERIFIED` pass.

---

# Stage D — Universal Production Asset Domain

## 9. Mục tiêu Stage D

Mở rộng asset pipeline hiện có thành thư viện production resource có aggregate, revision, lifecycle, query/command, preview, license, acquisition, jobs và dependency.

Độ phức tạp tương đối: `XXL`.

## 9.1 UI19 — Production Asset Taxonomy

- `D-UI19-01`: thêm `ProductionAssetKind` tách khỏi `MediaType` và MIME;
- `D-UI19-02`: lập mapping tương thích từ `ReferenceAsset`/asset resolution model hiện có;
- `D-UI19-03`: chốt enum taxonomy và policy mở rộng;
- `D-UI19-04`: định nghĩa kind/media/mime compatibility rules;
- `D-UI19-05`: migration/backfill cho asset hiện hữu;
- `D-UI19-06`: test unknown future enum không làm client crash.

## 9.2 UI20 — Asset Aggregate

- `D-UI20-01`: tạo `ProductionAsset` aggregate và invariant;
- `D-UI20-02`: tạo immutable `AssetRevision`, content hash và `supersedes` link;
- `D-UI20-03`: map normalization report/preview hiện có vào revision;
- `D-UI20-04`: tạo repository và migration cho asset/revision/tags/metadata;
- `D-UI20-05`: cấm overwrite bytes; active revision chỉ là pointer;
- `D-UI20-06`: deduplicate content bằng hash nhưng không gộp metadata/provenance sai;
- `D-UI20-07`: test revision lineage và concurrent create.

## 9.3 UI21 — Asset Lifecycle

- `D-UI21-01`: tái sử dụng và mở rộng `AssetStateMachine` hiện có;
- `D-UI21-02`: giữ `AssetLifecycleState` tách `AssetProcessingStatus`;
- `D-UI21-03`: định nghĩa transition matrix, actor và reason;
- `D-UI21-04`: mọi invalid transition fail closed;
- `D-UI21-05`: map normalization/job stage sang processing status;
- `D-UI21-06`: test failure/retry không vô tình approve asset.

## 9.4 UI22 — Asset Query API

- `D-UI22-01`: list/detail/revision/validation/provenance/bindings/dependencies query services;
- `D-UI22-02`: cursor pagination có deterministic sort;
- `D-UI22-03`: filter project, kind, lifecycle, processing, license, source, format, tag và query;
- `D-UI22-04`: tránh N+1 cho thumbnail, active revision và validation summary;
- `D-UI22-05`: signed/authorized artifact URL hoặc token, không internal path;
- `D-UI22-06`: generated TS contracts và MSW fixtures;
- `D-UI22-07`: load/performance test với large asset library.

## 9.5 UI23 — Asset Command API

- `D-UI23-01`: đăng ký toàn bộ asset command trong canonical command registry;
- `D-UI23-02`: import/upload dùng staged upload và content validation;
- `D-UI23-03`: normalize/validate/generate dispatch durable job;
- `D-UI23-04`: approve/reject/license update enforce permission và lifecycle;
- `D-UI23-05`: bind/unbind revision-aware và project-aware;
- `D-UI23-06`: archive không phá historical binding;
- `D-UI23-07`: event và audit cho mọi command;
- `D-UI23-08`: idempotency/restart tests cho job-creating command.

## 9.6 UI24 — Asset Library Page

- `D-UI24-01`: dựng Asset Workspace header/filter/library/inspector;
- `D-UI24-02`: grid và list dùng cùng query state;
- `D-UI24-03`: server-side pagination/filter/search;
- `D-UI24-04`: URL lưu filter, selection và view;
- `D-UI24-05`: thumbnail lazy loading, virtualization và object URL cleanup;
- `D-UI24-06`: bulk selection chỉ cho safe operation được policy cho phép;
- `D-UI24-07`: loading/empty/error/quarantine states;
- `D-UI24-08`: keyboard và accessibility test.

## 9.7 UI25 — Asset Inspector

- `D-UI25-01`: tabs Overview/Preview/Versions/Validation/Provenance/License/Dependencies/Usage;
- `D-UI25-02`: Overview hiển thị id/kind/format/size/hash/lifecycle/revision/time;
- `D-UI25-03`: Validation nhóm PASS/WARNING/FAIL và raw report download an toàn;
- `D-UI25-04`: Provenance hiển thị source/provider/author/url/model/prompt hash/seed/time;
- `D-UI25-05`: Versions hiển thị lineage và active revision;
- `D-UI25-06`: tab data load độc lập, cancel request khi đổi asset;
- `D-UI25-07`: không hiển thị secret hoặc raw provider credential.

## 9.8 UI26 — Asset License Governance

- `D-UI26-01`: chuẩn hóa license state, evidence và constraint;
- `D-UI26-02`: `LICENSE_UNKNOWN` không thể approve/final-use;
- `D-UI26-03`: attach/update license là audited command;
- `D-UI26-04`: render boundary kiểm tra license server-side, không tin UI;
- `D-UI26-05`: UI không có “Use Anyway” nếu chưa có explicit override policy;
- `D-UI26-06`: test expired/revoked/unknown/incompatible license;
- `D-UI26-07`: test asset revision mới không tự kế thừa license sai.

## 9.9 UI27 — 3D Preview System

- `D-UI27-01`: định nghĩa preview derivative contract và version;
- `D-UI27-02`: compiler tạo GLB từ supported source qua backend/worker;
- `D-UI27-03`: lưu derivative theo asset revision/content hash;
- `D-UI27-04`: shared viewer bằng Three.js/React Three Fiber;
- `D-UI27-05`: orbit/zoom/pan/wireframe/skeleton/bounds/material/texture/animation/stats;
- `D-UI27-06`: resource limits cho geometry, texture, animation và memory;
- `D-UI27-07`: fallback thumbnail/report khi WebGL unavailable;
- `D-UI27-08`: không parse `.blend` trực tiếp ở frontend;
- `D-UI27-09`: visual/smoke test cùng GLB trên Desktop và Web.

## 9.10 UI28 — Non-3D Resource Preview

- `D-UI28-01`: registry chọn previewer theo kind/media/mime;
- `D-UI28-02`: image viewer có size/zoom và safe decode;
- `D-UI28-03`: audio waveform/playback/duration/sample rate;
- `D-UI28-04`: animation dùng 3D viewer + clip selector;
- `D-UI28-05`: material sphere derivative;
- `D-UI28-06`: camera metadata và optional preview;
- `D-UI28-07`: lighting thumbnail/render derivative;
- `D-UI28-08`: unsupported/failed preview không chặn inspector phần còn lại.

## 9.11 UI29 — Asset Acquisition Workspace

- `D-UI29-01`: wizard Upload Local/Import URL/Search Internet/Generate/Reuse;
- `D-UI29-02`: tạo `AssetRequirement` input thống nhất;
- `D-UI29-03`: gọi `AssetResolverPort`, không hardcode provider vào UI;
- `D-UI29-04`: preview source/provenance/license trước khi import;
- `D-UI29-05`: validate URL scheme, content size/type và SSRF boundary phía backend;
- `D-UI29-06`: upload resumable hoặc recoverable cho file lớn nếu cần;
- `D-UI29-07`: explicit provider override chỉ khi policy/user yêu cầu.

## 9.12 UI30 — Asset Generation Request

- `D-UI30-01`: typed form theo asset kind;
- `D-UI30-02`: validate description/style/rig/poly/texture/usage budget;
- `D-UI30-03`: estimate capability/cost nếu provider hỗ trợ;
- `D-UI30-04`: submit `AssetGenerationRequest` bằng command idempotent;
- `D-UI30-05`: persist request và provenance before job dispatch;
- `D-UI30-06`: candidate output không auto-approve;
- `D-UI30-07`: test cancel, provider failure, partial candidate và retry.

## 9.13 UI31 — Asset Job Monitor

- `D-UI31-01`: map durable job events vào shared job projection;
- `D-UI31-02`: card progress và job detail;
- `D-UI31-03`: hiển thị current stage, progress, time, failure và retry policy;
- `D-UI31-04`: Cancel/Retry là command có permission và idempotency;
- `D-UI31-05`: reconnect/restart khôi phục đúng job state;
- `D-UI31-06`: sanitize log hiển thị cho người dùng;
- `D-UI31-07`: không blind retry non-retryable failure.

## 9.14 UI32 — Asset Usage & Dependency Graph

- `D-UI32-01`: tạo read model usage project → scene → shot;
- `D-UI32-02`: tạo asset dependency edges có type và revision;
- `D-UI32-03`: cycle detection và missing dependency validation;
- `D-UI32-04`: tree view cho usage và graph/tree view cho dependencies;
- `D-UI32-05`: click node deep-link đúng project/revision/entity;
- `D-UI32-06`: phân quyền để không lộ project không được phép xem.

## 9.15 UI33 — Asset Version Replacement

- `D-UI33-01`: impact query từ old revision sang candidate revision;
- `D-UI33-02`: tính affected project/scene/shot/animation/rerender;
- `D-UI33-03`: hỗ trợ current project, selected bindings và create project revision;
- `D-UI33-04`: không global replace mặc định;
- `D-UI33-05`: apply dùng transaction/command batch có audit;
- `D-UI33-06`: stale impact result phải recompute trước apply;
- `D-UI33-07`: test rollback/partial failure không tạo mixed binding.

### Stage D gate đề xuất

```text
VP3D_UI_ASSET_MANAGER_VERIFIED
```

Gate pass khi:

- asset bytes immutable và revision lineage đúng;
- lifecycle và processing state độc lập;
- unknown license bị chặn ở server final-production boundary;
- library/inspector/preview chạy ở cả Desktop và Web;
- generation job recover sau reconnect/restart;
- version replacement luôn có impact review.

---

# Stage E — Script ↔ Asset Integration

## 10. Mục tiêu Stage E

Biến screenplay requirements và production assets thành một workflow liên tục, có binding revision-aware và deep-link hai chiều.

Độ phức tạp tương đối: `L`.

## 10.1 UI34 — Entity Binding

- `E-UI34-01`: chốt binding aggregate: project revision, screenplay entity, role, asset revision;
- `E-UI34-02`: tạo eligibility policy theo kind, lifecycle, validation và license;
- `E-UI34-03`: Script Inspector hiển thị bound/missing/invalid/stale;
- `E-UI34-04`: Bind/Unbind qua canonical command;
- `E-UI34-05`: binding locked project revision phải tạo draft mới;
- `E-UI34-06`: binding event cập nhật cả Script và Asset projection;
- `E-UI34-07`: test không bind asset sai kind, rejected hoặc license-blocked.

## 10.2 UI35 — Cross Navigation

- `E-UI35-01`: mở asset từ character/location/prop trong Script;
- `E-UI35-02`: mở scene/shot từ Usage trong Asset;
- `E-UI35-03`: preserve projectId/revisionId/entityId/assetId;
- `E-UI35-04`: xử lý inaccessible/deleted/archived target;
- `E-UI35-05`: back/forward trả đúng selection và scroll/focus;
- `E-UI35-06`: route codec round-trip test ở cả consumer.

## 10.3 UI36 — Missing Asset Resolver

- `E-UI36-01`: validator phát `AssetRequirement[]` deterministic;
- `E-UI36-02`: resource summary theo character/location/prop và severity;
- `E-UI36-03`: prefill Search Library/Search Internet/Generate/Upload từ requirement;
- `E-UI36-04`: candidate resolver result phải qua normalize/validate/license/approve;
- `E-UI36-05`: sau approve, user xác nhận bind; không auto-bind ngoài policy;
- `E-UI36-06`: resolution progress giữ được qua navigation/reconnect;
- `E-UI36-07`: revalidate screenplay sau binding.

### Stage E gate đề xuất

```text
VP3D_UI_SCRIPT_ASSET_BINDING_VERIFIED
```

Gate pass khi missing requirement có thể đi từ Script sang Assets, tạo/import asset, approve, bind và quay lại Script mà không sửa DB/JSON/filesystem thủ công.

---

# Stage F — Human + Agent Collaboration

## 11. Mục tiêu Stage F

Đưa mọi thay đổi nhạy cảm của agent vào cùng proposal/approval protocol và cung cấp timeline production có thể hiểu bởi con người.

Độ phức tạp tương đối: `M`.

## 11.1 UI37 — Unified Change Proposal

- `F-UI37-01`: tổng quát hóa proposal cho screenplay, binding, license và approval;
- `F-UI37-02`: fields bắt buộc gồm target revision, affected entities, diff, impact, actor và status;
- `F-UI37-03`: proposal payload immutable sau submit; update tạo proposal version mới nếu cần;
- `F-UI37-04`: validate permission/policy trước create và trước approve;
- `F-UI37-05`: preview dùng semantic diff/impact component chung;
- `F-UI37-06`: approve chuyển thành canonical command trong transaction rõ ràng;
- `F-UI37-07`: stale target chuyển `REQUIRES_REVIEW`, không auto-apply;
- `F-UI37-08`: reject lưu reason nhưng không mutate target;
- `F-UI37-09`: test agent không thể bypass proposal bằng gọi command nhạy cảm trực tiếp.

## 11.2 UI38 — Production Activity Timeline

- `F-UI38-01`: projector chuyển domain event thành human-readable activity;
- `F-UI38-02`: group event kỹ thuật thành một user intent khi phù hợp;
- `F-UI38-03`: hiển thị actor, action, entity, revision, status và time;
- `F-UI38-04`: filter Script/Assets/Jobs/Proposals/System;
- `F-UI38-05`: deep-link activity về entity/revision;
- `F-UI38-06`: pagination và realtime append không duplicate;
- `F-UI38-07`: không hiển thị raw debug log, secret hoặc prompt đầy đủ;
- `F-UI38-08`: test replay cho timeline giống fresh projection.

### Stage F gate đề xuất

```text
VP3D_UI_HUMAN_AGENT_COLLABORATION_VERIFIED
```

Gate pass khi agent không thể trực tiếp mutate bốn nhóm state nhạy cảm và toàn bộ approve/reject được truy vết trên timeline.

---

# Stage G — Offline / Recovery / Conflict Handling

## 12. Mục tiêu Stage G

Đảm bảo refresh, restart, mất mạng và concurrent edit không làm mất local work hoặc silently ghi đè revision mới.

Độ phức tạp tương đối: `L`.

## 12.1 UI39 — Frontend State Recovery

- `G-UI39-01`: định nghĩa versioned `ProductionRecoverySnapshot`;
- `G-UI39-02`: persist project/page/selection/editor mode/last sequence/draft metadata;
- `G-UI39-03`: dùng IndexedDB hoặc adapter storage cho draft lớn; localStorage chỉ giữ preference nhỏ;
- `G-UI39-04`: không persist signed URL/token/secret;
- `G-UI39-05`: bootstrap: load cache → fetch server snapshot → compare revision → replay/refetch;
- `G-UI39-06`: cached state chỉ là hint, không tự apply lên canonical state;
- `G-UI39-07`: migrate/expire recovery schema cũ;
- `G-UI39-08`: corrupt cache phải fail safe và cho clear;
- `G-UI39-09`: restart Desktop và reload Web E2E;
- `G-UI39-10`: test offline read-only mode và explicit reconnect.

## 12.2 UI40 — Concurrent Edit Conflict

- `G-UI40-01`: chuẩn hóa 409 payload gồm base/current revision và correlation;
- `G-UI40-02`: lưu base snapshot/hash đủ cho three-way semantic comparison;
- `G-UI40-03`: hiển thị local vs server diff theo entity;
- `G-UI40-04`: hỗ trợ View Changes, Merge Into New Revision, Discard Local;
- `G-UI40-05`: auto-merge chỉ cho non-overlapping edit được chứng minh;
- `G-UI40-06`: overlapping/ambiguous edit bắt buộc human review;
- `G-UI40-07`: merge luôn tạo command/revision mới trên latest base;
- `G-UI40-08`: giữ local draft đến khi merge/discard được xác nhận;
- `G-UI40-09`: test Frontend vs Agent, Worker vs Frontend và two-tab Web;
- `G-UI40-10`: test conflict lặp lại không tạo revision storm.

### Stage G gate đề xuất

```text
VP3D_UI_RECOVERY_CONFLICT_VERIFIED
```

Gate pass khi:

- refresh/restart không mất unsaved draft;
- cached state không overwrite server;
- stale edit không blind retry;
- conflict có thể merge thành revision mới hoặc discard có chủ ý.

---

# Stage H — Testing

## 13. Mục tiêu Stage H

Hoàn chỉnh test pyramid và chứng minh shared package chạy đúng trong hai consumer. Mỗi defect tìm thấy phải được bổ sung regression test ở tầng thấp nhất phù hợp.

Độ phức tạp tương đối: `XL`.

## 13.1 UI41 — Contract Tests

- `H-UI41-01`: generate TS types từ OpenAPI/JSON Schema ở CI;
- `H-UI41-02`: consumer decode test trên API fixtures thật;
- `H-UI41-03`: backward/forward compatibility tests;
- `H-UI41-04`: enum, required field, revision và command payload negative tests;
- `H-UI41-05`: snapshot/event consistency contract;
- `H-UI41-06`: schema-diff CI chặn breaking change chưa version;
- `H-UI41-07`: contract fixtures không chứa internal path/secret.

## 13.2 UI42 — Script Behavioral Tests

Test suite tối thiểu:

- load/select/navigate screenplay;
- structured add/edit/delete/reorder/split/merge;
- text parse/diagnostic/apply;
- structured/text round-trip và ID stability;
- draft save/recovery;
- locked edit tạo revision mới;
- semantic diff và impact;
- AI proposal approve/reject/stale;
- validation và lock;
- stale conflict và reconnect.

Phân tầng:

- pure unit cho parser/serializer/diff/reducer;
- component test cho editor/inspector/dialog;
- API integration cho command/revision/lock;
- E2E cho golden flow.

## 13.3 UI43 — Asset Behavioral Tests

Test suite tối thiểu:

- list/search/filter/pagination;
- import/upload và invalid file;
- preview supported/unsupported/failure;
- normalize/validate/license unknown;
- approve/reject/version/archive;
- bind/unbind và eligibility;
- usage/dependency/cycle;
- generation job progress/cancel/failure/retry/recovery;
- version replacement impact;
- Script cross-navigation.

## 13.4 UI44 — Shared Package Consumer Tests

- `H-UI44-01`: build/test `production-ui` trong browser harness;
- `H-UI44-02`: build/test cùng package trong Desktop/Tauri harness;
- `H-UI44-03`: architecture test cấm platform leak;
- `H-UI44-04`: package export/React singleton test;
- `H-UI44-05`: chạy cùng behavioral fixture cho hai consumer;
- `H-UI44-06`: visual snapshots cho critical shared component;
- `H-UI44-07`: gate browser PASS và desktop PASS.

## 13.5 UI45 — Desktop E2E

Canonical lane:

```text
Launch Tauri
→ open Production
→ select project
→ edit screenplay
→ create/lock revision
→ import GLB
→ validate/approve/bind
→ restart app
→ recover context and verify state
```

Bổ sung negative lanes:

- file picker cancel/permission denied;
- sidecar/API restart giữa command và replay;
- offline/reconnect;
- stale revision conflict;
- unsupported preview.

## 13.6 UI46 — Browser E2E

Chạy workflow tương đương Desktop nhưng bắt buộc:

- import qua File API + HTTP;
- không có Tauri/native/filesystem assumption;
- browser history/deep-link/reload đúng;
- two-tab conflict đúng;
- service unavailable/offline state đúng.

## 13.7 CI matrix và quality gates

| Lane | Mục tiêu |
| --- | --- |
| Python unit | domain/application/repository |
| Python integration SQLite | migration, command, event, projection |
| Python integration Postgres | concurrency và production persistence |
| Frontend contract | generated types + fixtures |
| Shared unit/component | reducer/client/UI |
| Desktop consumer | build/test/Tauri smoke |
| Web consumer | build/test/browser smoke |
| E2E golden | Script, Asset, integrated |
| Architecture | dependency/platform/source-of-truth rules |
| Security | upload, URL, license, permission, data leakage |

### Stage H gate đề xuất

```text
VP3D_UI_TEST_MATRIX_VERIFIED
```

Không pass nếu chỉ có happy-path E2E mà thiếu invariant tests cho lock, idempotency, license và stale revision.

---

# Stage I — Final Acceptance

## 14. Mục tiêu Stage I

Chạy ba golden workflow trên build release candidate và chứng minh foundation đủ cho Video Workspace.

Độ phức tạp tương đối: `M`.

## 14.1 Chuẩn bị acceptance environment

- `I-PREP-01`: tạo deterministic Bunny project fixture;
- `I-PREP-02`: seed screenplay, locked revision, asset candidates, missing Ball và event history;
- `I-PREP-03`: cấu hình provider fake/deterministic cho generation lane CI;
- `I-PREP-04`: tạo clean database và upgrade-from-previous schema lanes;
- `I-PREP-05`: ghi version app/API/schema/contract vào evidence bundle;
- `I-PREP-06`: chạy smoke màn hình ngoài Production.

## 14.2 UI47 — Script Golden Workflow

Thực thi và ghi evidence:

```text
Create screenplay
→ Structured edit
→ Text edit
→ AI revision proposal
→ Human approve
→ Validate
→ Lock
→ Attempt edit on locked revision
→ Create and edit a new draft revision
```

Acceptance:

- semantic round-trip đúng;
- ancestor locked revision giữ nguyên hash;
- proposal có audit;
- validation blocking rule được enforce;
- gate `VP3D_UI_SCRIPT_GOLDEN_WORKFLOW_PASSED` pass.

## 14.3 UI48 — Asset Golden Workflow

Thực thi và ghi evidence:

```text
Asset requirement
→ acquire/generate
→ normalize
→ validate
→ attach/check license
→ preview
→ approve
→ bind/use
→ create asset revision
→ impact review
```

Acceptance:

- provenance và license đầy đủ;
- asset revision cũ không bị overwrite;
- job state recover được;
- version replacement không tự apply toàn cục;
- gate `VP3D_UI_ASSET_GOLDEN_WORKFLOW_PASSED` pass.

## 14.4 UI49 — Script + Asset Integrated E2E

Fixture Scene 03 yêu cầu Bunny, Park và Ball:

- Bunny/Park đã tồn tại và eligible;
- Ball thiếu;
- resolve/generate Ball;
- normalize, validate, license và approve;
- bind Ball vào Scene 03;
- rerun screenplay validation;
- lock revision.

Acceptance:

- không sửa DB trực tiếp;
- không sửa JSON trực tiếp;
- không copy file thủ công;
- route/context giữ cùng project/revision;
- timeline phản ánh toàn bộ flow;
- gate `VP3D_UI_SCRIPT_ASSET_INTEGRATION_PASSED` pass.

## 14.5 UI50 — Foundation for Video Production Page

- `I-UI50-01`: audit shared context có project/revision/scene/shot/artifact/job;
- `I-UI50-02`: audit event projection hỗ trợ video event namespace;
- `I-UI50-03`: audit artifact preview và approval component có thể tái sử dụng;
- `I-UI50-04`: audit invalidation/impact link đến shot/render;
- `I-UI50-05`: tạo `production-ui/video/` placeholder chỉ dùng public package API;
- `I-UI50-06`: viết architecture test chứng minh không cần import nội bộ Script/Assets;
- `I-UI50-07`: ghi backlog Video Workspace riêng, không mở rộng scope Roadmap II;
- `I-UI50-08`: gate `VP3D_UI_VIDEO_WORKSPACE_FOUNDATION_READY` pass.

## 14.6 Final release gate

Release candidate chỉ được chấp nhận khi:

- toàn bộ gate bắt buộc A–I pass trên cùng commit;
- migration forward pass và rollback strategy được tài liệu hóa;
- không có blocker/critical defect mở;
- security/privacy/license negative tests pass;
- Desktop và Web cùng dùng shared package build tương ứng;
- evidence bundle chứa command, version, result và artifact checksum;
- rollback/feature flag cho Production entry point được xác nhận.

---

## 15. Package/file plan đề xuất

```text
frontend/
├── package.json
├── package-lock.json
├── tsconfig.base.json
└── packages/
    ├── production-contracts/
    │   └── src/{project,screenplay,asset,revision,command,event,job,proposal}.ts
    ├── production-client/
    │   └── src/{http,project,screenplay,asset,command,event}.ts
    ├── production-state/
    │   └── src/{store,project,screenplay,asset,eventProjection,recovery}.ts
    ├── production-platform/
    │   └── src/{types,fakeAdapter}.ts
    └── production-ui/
        └── src/{common,screenplay,assets,proposals,timeline,video}/

apps/desktop/src/production/
├── DesktopProductionAdapter.ts
├── ProductionRouteHost.tsx
└── ProductionPage.tsx

apps/web/src/production/
├── WebProductionAdapter.ts
├── ProductionRouteHost.tsx
└── ProductionPage.tsx

apps/api/windagent_api/routers/
├── v2_production_projects.py
├── v2_production_commands.py
└── v2_production_assets.py
```

Tên file API có thể điều chỉnh theo router convention hiện hữu, nhưng domain logic không được đặt trong route handler.

---

## 16. Contract và event tối thiểu cần chốt sớm

### 16.1 Command envelope

```json
{
  "command_type": "UPDATE_SCENE",
  "project_id": "vp_001",
  "target_revision_id": "rev_012",
  "entity_id": "scene_04",
  "reason": "Manual screenplay edit",
  "payload": {},
  "client_context": {
    "base_sequence": 490
  }
}
```

Header bắt buộc:

```text
X-Idempotency-Key
```

### 16.2 Event envelope

```json
{
  "event_id": "evt_...",
  "sequence": 491,
  "event_type": "SCREENPLAY_SCENE_UPDATED",
  "project_id": "vp_001",
  "revision_id": "rev_013",
  "aggregate_type": "SCREENPLAY",
  "aggregate_id": "screenplay_01",
  "actor": {},
  "occurred_at": "...",
  "payload": {}
}
```

### 16.3 Conflict response

```json
{
  "type": ".../stale-revision",
  "status": 409,
  "code": "REJECTED_STALE",
  "target_revision_id": "rev_012",
  "current_revision_id": "rev_013",
  "current_sequence": 497,
  "correlation_id": "..."
}
```

---

## 17. Rủi ro chính và biện pháp giảm thiểu

| Rủi ro | Tác động | Giảm thiểu |
| --- | --- | --- |
| Dirty baseline bị coi là release baseline | Gate/test không tái tạo | UI0 candidate manifest, không reset worktree |
| Toolchain Desktop/Web lệch lớn | Duplicate React, test khác hành vi | Pin workspace, consumer matrix |
| DTO viết tay trôi khỏi Python domain | Runtime mismatch | OpenAPI/JSON Schema generation + decoder test |
| Snapshot và event không cùng sequence | UI gap/duplicate | consistency boundary, gap detection, replay tests |
| Locked revision bị sửa qua đường phụ | Mất audit/history | server invariant + hash regression tests |
| Parser đoán text mơ hồ | Hỏng semantic/ID | diagnostics + `PARSE_REQUIRES_REVIEW` |
| Asset lifecycle trộn job status | State transition sai | hai state machine độc lập |
| Preview file quá lớn/độc hại | Crash/security | backend derivative, size/resource limits |
| License chỉ kiểm tra ở UI | Final render dùng asset không hợp lệ | server fail-closed boundary |
| AI bypass proposal | Canonical state bị mutate | permission/command policy, adversarial tests |
| Local cache overwrite server | Mất revision mới | cache là hint, reconcile trước apply |
| E2E phụ thuộc provider không ổn định | CI flaky | deterministic fake provider + separate live smoke |

---

## 18. Milestone mapping và báo cáo tiến độ

| Milestone | Phase hoàn thành tối thiểu | Evidence chính |
| --- | --- | --- |
| F-M1 Shared workspace | UI0–UI1 | install/build/test receipt |
| F-M2 Shared UI consumers | UI2–UI4 | Desktop/Web shell tests |
| F-M3 API + event sync | UI5–UI7 | snapshot/command/replay integration |
| F-M4 Structured editor | UI8–UI10, UI13 | behavioral tests |
| F-M5 Text editor | UI11 | parser corpus |
| F-M6 Hybrid verified | UI12 | semantic round-trip report |
| F-M7 Immutable revision | UI14–UI16, UI18 | hash/lock/impact receipts |
| F-M8 AI proposal | UI17, UI37 | approval/bypass tests |
| F-M9 Asset Library | UI19–UI24 | API/library E2E |
| F-M10 Governance | UI25–UI26 | provenance/license tests |
| F-M11 Preview | UI27–UI28 | Desktop/Web preview matrix |
| F-M12 Asset jobs | UI29–UI31 | job recovery tests |
| F-M13 Binding | UI32–UI36 | integrated binding flow |
| F-M14 Desktop/Web E2E | UI41–UI49 | release evidence bundle |
| F-M15 Video-ready | UI50 | architecture audit |

Mỗi milestone report cần có:

- commit SHA;
- schema/contract version;
- phase status `NOT_STARTED/IN_PROGRESS/BLOCKED/PASSED`;
- test commands và kết quả;
- defect/risk còn mở;
- link evidence;
- quyết định go/no-go cho milestone kế tiếp.

---

## 19. Backlog ưu tiên để bắt đầu

Thứ tự 15 backlog item đầu tiên:

1. phân loại working tree và chọn UI0 candidate baseline;
2. chạy baseline test/evidence;
3. chốt Node/npm và toolchain compatibility target;
4. tạo `frontend/` workspace;
5. tạo package skeleton và architecture boundaries;
6. tích hợp placeholder shared component vào Desktop/Web;
7. chốt platform adapter contract và fake adapter;
8. chốt production project/revision TS contract;
9. tạo project context store;
10. tạo production route codec;
11. inventory repository/UoW/event store backend hiện có;
12. thiết kế persistence cho project/revision/idempotency/projection;
13. tạo workspace snapshot query service và OpenAPI schema;
14. tạo canonical command service với stale/idempotency tests;
15. chuyển event client/replay thành shared production client.

Sau item 15 và khi UI7 pass, tách team thành Script track UI8–18 và Asset track UI19–33.

