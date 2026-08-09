# Kế hoạch Stage A — Shared Production Frontend Foundation

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | A |
| Phạm vi | UI0–UI4 |
| Kết quả chính | Shared Production shell chạy trong Desktop và Web |
| Dependency đầu vào | Candidate baseline được xác định |
| Bàn giao cho | Stage B, C, D và G |
| Độ phức tạp tương đối | L |

## 2. Mục tiêu

Tạo nền tảng frontend production dùng chung mà không phá các màn hình hiện hữu. Khi Stage A hoàn tất:

- có một npm workspace riêng tại `frontend/`;
- Production UI, contracts, client, state và platform boundary có package rõ ràng;
- Desktop và Web render cùng `ProductionShell`;
- mọi khác biệt Tauri/browser nằm sau adapter;
- Script, Assets và Video placeholder dùng chung project/revision context;
- deep-link có cùng semantics trong hai application.

## 3. Baseline và khoảng trống

Baseline khi lập kế hoạch:

```text
HEAD: 5662edee35893876264a599a9480cafb531466f1
Ngày đối chiếu: 2026-08-08
```

Hiện trạng có thể tái sử dụng:

- Desktop đã có React/Tauri shell, sidebar, API client và nhiều page hoàn chỉnh;
- Web đã có application skeleton, event client và recovery skeleton;
- cả hai app đều đã dùng Redux Toolkit;
- Desktop có thể làm visual/shell reference ban đầu.

Khoảng trống:

- chưa có `frontend/` workspace;
- chưa có shared production package;
- React, TypeScript, Vite, Vitest giữa Desktop/Web chưa đồng nhất;
- navigation hiện hữu chưa có shared Production route contract;
- chưa có platform adapter cho file import/download.

Working tree có nhiều thay đổi chưa commit. UI0 phải chọn candidate baseline có chủ ý; không reset thay đổi người dùng để tạo một tree sạch giả tạo.

## 4. Phạm vi

### Trong phạm vi

- baseline/evidence freeze;
- frontend workspace và toolchain;
- package boundaries;
- platform adapters;
- project/revision context;
- Production shell và routing;
- smoke regression cho page hiện hữu.

### Ngoài phạm vi

- Production query/command API thật;
- screenplay editor;
- asset library;
- offline merge;
- Video Workspace hoàn chỉnh.

Các phần này chỉ dùng fake/fixture contract trong Stage A.

## 5. Kiến trúc mục tiêu

```text
frontend/packages/production-contracts
                 ^
                 |
production-platform       production-client
                 ^         ^
                  \       /
                production-state
                       ^
                       |
                 production-ui
                  /           \
       apps/desktop             apps/web
       DesktopAdapter           WebAdapter
```

Dependency rules:

1. `production-contracts` không phụ thuộc React hoặc application;
2. `production-client` không biết Tauri;
3. `production-state` chỉ phụ thuộc contracts/client;
4. `production-ui` chỉ gọi public APIs của state/platform;
5. Desktop/Web là composition root;
6. shared package không import source nội bộ của consumer.

## 6. Kế hoạch UI0 — Baseline Freeze

### Backlog

- `A-UI0-01`: phân loại dirty worktree theo Roadmap I, Roadmap II, artifact và thay đổi ngoài phạm vi;
- `A-UI0-02`: chọn candidate SHA hoặc tạo baseline manifest chứa accepted dirty paths;
- `A-UI0-03`: inventory `apps/desktop`, `apps/web`, `apps/api`, production domain, storage, workflows và orchestration;
- `A-UI0-04`: ghi Node/npm/Python, OS, React, TypeScript, Vite và Vitest versions;
- `A-UI0-05`: chạy Desktop test/build/typecheck;
- `A-UI0-06`: chạy Web test/build/typecheck;
- `A-UI0-07`: chạy API và video-production test suite phù hợp;
- `A-UI0-08`: snapshot OpenAPI, API routes, event contracts và frontend state;
- `A-UI0-09`: smoke Dashboard, Agents, Agent Workspace, Workflows, Browser, Files, Memory, Models, Router và Settings;
- `A-UI0-10`: ghi known failures và ownership; không đổi failure thành PASS bằng skip;
- `A-UI0-11`: tạo script/CI command tái tạo evidence;
- `A-UI0-12`: tạo phase verdict.

### Deliverable

```text
artifacts/production_ui/phase_00/
├── baseline_manifest.json
├── toolchain_inventory.json
├── api_contract_snapshot.json
├── event_contract_snapshot.json
├── desktop_test_receipt.json
├── web_test_receipt.json
├── backend_test_receipt.json
├── regression_smoke_receipt.json
└── phase_verdict.json
```

### Acceptance

- baseline có commit/manifest định danh duy nhất;
- command và environment đủ để tái tạo test;
- mọi failure đã biết có trạng thái và owner;
- không có file hiện hữu bị reset/xóa;
- `VP3D_UI_P0_BASELINE_FROZEN` pass.

## 7. Kế hoạch UI1 — Frontend Workspace Foundation

### Quyết định triển khai

- dùng npm workspace tại `frontend/`;
- có một lockfile cho shared packages;
- hai app giữ build và entry point riêng;
- pin exact versions cho ABI/tooling cốt lõi;
- dùng Redux Toolkit cho `production-state` vì cả hai app đã có dependency;
- không yêu cầu Desktop bỏ Zustand ở module hiện hữu.

### Backlog

- `A-UI1-01`: tạo `frontend/package.json` và npm workspace config;
- `A-UI1-02`: tạo `package-lock.json` từ clean install;
- `A-UI1-03`: tạo `tsconfig.base.json` và package build configs;
- `A-UI1-04`: tạo package `production-contracts`;
- `A-UI1-05`: tạo package `production-client`;
- `A-UI1-06`: tạo package `production-state`;
- `A-UI1-07`: tạo package `production-platform`;
- `A-UI1-08`: tạo package `production-ui`;
- `A-UI1-09`: chốt compatibility target cho React/TS/Vite/Vitest;
- `A-UI1-10`: thêm ESLint và architecture boundary rules;
- `A-UI1-11`: cấu hình Vitest/Testing Library dùng chung;
- `A-UI1-12`: thêm `ProductionPlaceholder` vào Desktop;
- `A-UI1-13`: thêm cùng placeholder vào Web;
- `A-UI1-14`: thêm CI install/typecheck/test/build;
- `A-UI1-15`: kiểm tra chỉ có một React runtime trong từng consumer bundle.

### Package public surface tối thiểu

```text
@windagent/production-contracts
@windagent/production-client
@windagent/production-state
@windagent/production-platform
@windagent/production-ui
```

### Acceptance

- clean install tại `frontend/` thành công;
- từng package build/test độc lập;
- Desktop và Web consume package bằng public exports;
- không có cross-import giữa hai app;
- `VP3D_UI_P1_FRONTEND_WORKSPACE_VERIFIED` pass.

## 8. Kế hoạch UI2 — Platform Adapter Boundary

### Contract mục tiêu

```ts
interface ProductionPlatformAdapter {
  selectLocalFile(options?: SelectFileOptions): Promise<SelectedFile[]>;
  revealFile?(artifactId: string): Promise<void>;
  openExternal(url: string): Promise<void>;
  downloadArtifact(id: string): Promise<void>;
  supportsLocalFilesystem(): boolean;
}
```

`SelectedFile` chỉ chứa browser `File`/upload handle hoặc metadata an toàn. Domain không nhận internal filesystem path.

### Backlog

- `A-UI2-01`: chốt adapter types và capability flags;
- `A-UI2-02`: định nghĩa typed errors `CANCELLED`, `DENIED`, `UNSUPPORTED`, `TRANSFER_FAILED`;
- `A-UI2-03`: implement Desktop adapter bằng Tauri APIs;
- `A-UI2-04`: implement Web adapter bằng File API và HTTP download;
- `A-UI2-05`: implement fake adapter cho test;
- `A-UI2-06`: tạo shared Import button/dialog;
- `A-UI2-07`: test picker cancel, multi-file, size/type validation;
- `A-UI2-08`: test open external/download/reveal capability;
- `A-UI2-09`: architecture test cấm `window.__TAURI__` và `@tauri-apps/api` trong shared package;
- `A-UI2-10`: architecture test cấm direct file input logic ngoài adapter/composition boundary.

### Acceptance

- cùng component import chạy với fake, Desktop và Web adapter;
- unsupported action có UX rõ ràng;
- không lộ native path vào state/API DTO;
- `VP3D_UI_P2_PLATFORM_BOUNDARY_VERIFIED` pass.

## 9. Kế hoạch UI3 — Production Project Context

### State mục tiêu

```text
ProductionProjectContext
├── projectId, projectStatus
├── revisionId, revisionStatus
├── screenplayId, screenplayStatus
├── currentSequence
├── activePage, selectedEntity
├── syncStatus
└── backendStatus
```

### Backlog

- `A-UI3-01`: định nghĩa TS contract và runtime decoder;
- `A-UI3-02`: tạo reducer/store factory, selectors và actions;
- `A-UI3-03`: tạo bootstrap state machine;
- `A-UI3-04`: tạo fake workspace snapshot fixture;
- `A-UI3-05`: dựng shared project/revision header;
- `A-UI3-06`: implement explicit project switch;
- `A-UI3-07`: thêm unsaved-change guard hook;
- `A-UI3-08`: reset selection/draft đúng khi đổi project;
- `A-UI3-09`: chặn editor render khi project/revision incoherent;
- `A-UI3-10`: thêm extension fields cho future Video Workspace;
- `A-UI3-11`: test Script/Assets/Video placeholder luôn cùng project;
- `A-UI3-12`: test backend offline/stale context.

### Acceptance

- không thể vô tình mở ba project khác nhau trong cùng Production Workspace;
- project switch là explicit action;
- context invalid không silently fallback;
- header luôn phản ánh đúng revision/lock/sync state.

## 10. Kế hoạch UI4 — Production Routing

### Contract mục tiêu

```ts
interface ProductionRoute {
  projectId: string;
  page: "script" | "assets" | "video";
  entityId?: string;
  revisionId?: string;
}
```

### Backlog

- `A-UI4-01`: tạo shared route parser/serializer;
- `A-UI4-02`: chuẩn hóa query cho scene/asset/shot;
- `A-UI4-03`: Web host map vào browser URL/history;
- `A-UI4-04`: Desktop host map vào navigation/deep-link state;
- `A-UI4-05`: thêm Production group vào sidebar;
- `A-UI4-06`: tạo Script/Assets/Video placeholder routes;
- `A-UI4-07`: tạo missing project/revision/entity states;
- `A-UI4-08`: test direct link, reload, back/forward;
- `A-UI4-09`: test Desktop restore/deep-link;
- `A-UI4-10`: test route round-trip và encoded IDs;
- `A-UI4-11`: cấm component tự nối URL string;
- `A-UI4-12`: smoke regression sidebar/page hiện hữu.

### Acceptance

- cùng route object có semantics giống nhau ở hai app;
- reload/back/forward giữ project/page/entity;
- invalid deep-link không crash hoặc mở sai project;
- `VP3D_UI_P4_PRODUCTION_NAVIGATION_VERIFIED` pass.

## 11. Test strategy

| Tầng | Kiểm thử |
| --- | --- |
| Unit | route codec, reducers, selectors, capability detection |
| Component | shell, header, switcher, import dialog, error states |
| Consumer | Desktop và Web render cùng fixture |
| Architecture | dependency direction, platform leak, React singleton |
| Smoke | toàn bộ page hiện hữu ngoài Production |

Negative cases bắt buộc:

- picker bị cancel;
- platform capability không hỗ trợ;
- malformed route;
- missing project/revision;
- project switch khi dirty;
- offline backend;
- duplicated React/toolchain mismatch.

## 12. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Toolchain upgrade làm hỏng app cũ | pin version, consumer lanes, upgrade theo bước |
| Shared package import app internals | architecture test |
| Redux/Zustand tạo hai source of truth | production-state có owner rõ; app state chỉ compose |
| Tauri leak vào shared UI | adapter + static rule |
| Dirty baseline không tái tạo | candidate manifest + evidence receipt |
| Desktop shell bị thay đổi ngoài ý muốn | visual/smoke regression |

## 13. Stage exit checklist

- [ ] UI0 baseline và receipts hoàn chỉnh.
- [ ] UI1 workspace clean-install/build/test thành công.
- [ ] UI2 adapter contract chạy ở Desktop và Web.
- [ ] UI3 project/revision context coherent.
- [ ] UI4 route round-trip và deep-link pass.
- [ ] Không regression các page hiện hữu.
- [ ] Không platform-specific import trong shared UI.
- [ ] Public package APIs được ghi tài liệu.
- [ ] Các gate UI0, UI1, UI2 và UI4 pass trên cùng candidate.

## 14. Bàn giao sang Stage B

Stage B nhận:

- package contracts/client/state skeleton;
- fake workspace snapshot và event fixtures;
- project/revision context;
- route codec;
- platform adapter;
- CI frontend matrix.

Stage B phải thay fake query/command/event bằng runtime implementation mà không đổi public UI composition boundary.
