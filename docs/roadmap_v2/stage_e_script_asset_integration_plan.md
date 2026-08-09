# Kế hoạch Stage E — Script ↔ Asset Integration

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | E |
| Phạm vi | UI34–UI36 |
| Kết quả chính | Workflow liên tục từ screenplay requirement đến asset binding |
| Dependency đầu vào | Stage C/UI18 và Stage D/UI33 pass |
| Có thể phối hợp | Stage F timeline/proposal read models |
| Bàn giao cho | Stage G, H và I |
| Độ phức tạp tương đối | L |

## 2. Mục tiêu

Kết nối Script Workspace và Asset Manager thành một production workflow duy nhất. Sau Stage E:

- screenplay entities có binding trạng thái rõ ràng;
- chỉ asset eligible mới được bind;
- bind/unbind revision-aware và event-emitting;
- Script có thể mở đúng Asset, Asset có thể mở đúng Scene/Shot;
- missing asset validation tạo requirement có thể giải quyết;
- resolution flow đi qua search/acquire/generate/normalize/validate/license/approve;
- hoàn tất binding sẽ revalidate screenplay;
- không cần sửa DB, JSON hoặc copy file thủ công.

## 3. Phạm vi

### Trong phạm vi

- entity-to-asset binding model và eligibility;
- Script Inspector binding UI;
- deep-link/cross-navigation;
- missing asset requirements và resolver workflow;
- read-model/event integration hai chiều;
- integration tests từ Script tới Assets.

### Ngoài phạm vi

- xây lại Script/Asset capabilities;
- agent auto-approval;
- generic conflict merge;
- final render;
- Video Workspace.

## 4. Dependency contract

Stage C phải cung cấp:

- stable screenplay/scene/character/location/prop IDs;
- `AssetRequirement[]`;
- active project/revision context;
- validation rerun;
- locked revision/create draft flow.

Stage D phải cung cấp:

- asset kind/lifecycle/license/validation eligibility;
- asset list/search/detail;
- bind/unbind commands;
- acquisition/generation workflows;
- usage/dependency projection;
- active asset revision.

## 5. Binding model mục tiêu

```text
ProductionAssetBinding
├── bindingId
├── projectId
├── productionRevisionId
├── screenplayEntityType
├── screenplayEntityId
├── role/requirementKey
├── assetId
├── assetRevisionId
├── status
├── createdBy/createdAt
└── supersedes/unboundAt
```

Invariants:

- project/revision/entity tồn tại và cùng context;
- asset kind đáp ứng requirement;
- asset lifecycle cho phép sử dụng;
- validation không có blocking issue theo policy;
- license hợp lệ cho intended usage;
- locked production revision không bị sửa tại chỗ;
- binding history không overwrite.

## 6. Kế hoạch UI34 — Entity Binding

### Backend/domain backlog

- `E-UI34-01`: chốt binding entity/aggregate/invariants;
- `E-UI34-02`: định nghĩa entity types và role keys;
- `E-UI34-03`: tạo eligibility service;
- `E-UI34-04`: validate project/revision/entity coherence;
- `E-UI34-05`: validate kind/media compatibility;
- `E-UI34-06`: validate lifecycle/validation/license;
- `E-UI34-07`: implement `BIND_ASSET` handler;
- `E-UI34-08`: implement `UNBIND_ASSET` handler;
- `E-UI34-09`: locked revision tạo draft trước mutation;
- `E-UI34-10`: persist immutable binding history;
- `E-UI34-11`: emit binding/unbinding/invalidation events;
- `E-UI34-12`: update Script và Asset projections;
- `E-UI34-13`: audit actor/reason;
- `E-UI34-14`: concurrency/stale/idempotency tests.

### Frontend backlog

- `E-UI34-15`: Script Inspector sections Characters/Location/Props;
- `E-UI34-16`: states bound/missing/invalid/stale/processing;
- `E-UI34-17`: open asset picker với prefilled requirement;
- `E-UI34-18`: show eligibility reason;
- `E-UI34-19`: bind confirmation và impact summary;
- `E-UI34-20`: unbind confirmation;
- `E-UI34-21`: reflect realtime binding events;
- `E-UI34-22`: route/entity selection preservation;
- `E-UI34-23`: component/accessibility tests.

### Negative cases

- asset sai kind;
- asset rejected/archived;
- validation blocking;
- license unknown/incompatible;
- asset revision không tồn tại;
- screenplay entity bị xóa;
- project/revision mismatch;
- target revision locked;
- concurrent binding change;
- duplicate submit.

### Acceptance

- không bind được asset ineligible;
- binding event cập nhật cả hai workspace;
- locked revision không mutate;
- stale command không silently overwrite;
- usage history giữ đúng asset revision.

## 7. Kế hoạch UI35 — Cross Navigation

### Route examples

```text
/production/vp_01/script?revision=rev_13&scene=sc_07&entity=char_bunny
/production/vp_01/assets?revision=rev_13&asset=asset_bunny
```

### Backlog

- `E-UI35-01`: mở Asset từ character/location/prop binding;
- `E-UI35-02`: mở Asset từ validation/missing requirement;
- `E-UI35-03`: mở Script Scene từ Asset Usage;
- `E-UI35-04`: mở Shot/Scene phù hợp từ dependency node;
- `E-UI35-05`: preserve projectId/revisionId/entityId/assetId;
- `E-UI35-06`: back/forward restore selection/focus;
- `E-UI35-07`: Desktop deep-link mapping;
- `E-UI35-08`: Web history/direct URL mapping;
- `E-UI35-09`: inaccessible/deleted/archived target state;
- `E-UI35-10`: route codec round-trip tests;
- `E-UI35-11`: permission-safe usage links;
- `E-UI35-12`: consumer E2E navigation tests.

### Acceptance

- navigation không đổi project/revision ngoài ý muốn;
- direct link/reload mở đúng entity;
- missing/inaccessible target có actionable state;
- back trả đúng selection và view state;
- Desktop/Web cùng route semantics.

## 8. Kế hoạch UI36 — Missing Asset Resolver

### Flow mục tiêu

```text
Screenplay validation
→ AssetRequirement[]
→ choose Search Library / Internet / Generate / Upload
→ candidate
→ normalize
→ validate
→ license
→ approve
→ confirm binding
→ revalidate screenplay
```

### Requirement contract

```text
AssetRequirement
├── requirementId
├── projectId/revisionId
├── screenplayEntityId/type
├── requiredKind/media/capabilities
├── description/style/constraints
├── severity
├── status
└── currentCandidates
```

### Backend backlog

- `E-UI36-01`: deterministic requirement generation;
- `E-UI36-02`: stable requirement ID theo revision/entity/rule;
- `E-UI36-03`: requirement status projection;
- `E-UI36-04`: candidate eligibility ranking;
- `E-UI36-05`: link acquisition/generation jobs;
- `E-UI36-06`: invalidate/recompute khi screenplay đổi;
- `E-UI36-07`: close requirement khi eligible binding tồn tại;
- `E-UI36-08`: re-open khi asset/license/binding mất eligibility.

### Frontend backlog

- `E-UI36-09`: Production Resources summary counts;
- `E-UI36-10`: missing requirements list/filter;
- `E-UI36-11`: action Search Library;
- `E-UI36-12`: action Search Internet;
- `E-UI36-13`: action Generate;
- `E-UI36-14`: action Upload;
- `E-UI36-15`: prefill acquisition form;
- `E-UI36-16`: display job/progress/candidate state;
- `E-UI36-17`: explicit bind confirmation;
- `E-UI36-18`: return to Script entity;
- `E-UI36-19`: rerun validation and update counts;
- `E-UI36-20`: persist resolution progress qua navigation/reconnect.

### Acceptance

- requirements deterministic cho cùng revision;
- stale requirement không bind vào revision mới mà không review;
- candidate không auto-approve/auto-bind ngoài policy;
- successful bind làm validation resource issue biến mất;
- failure ở acquisition/job giữ actionable retry/cancel state.

## 9. Event/read-model integration

Events tối thiểu:

```text
ASSET_REQUIREMENT_CREATED
ASSET_REQUIREMENT_UPDATED
ASSET_BINDING_CREATED
ASSET_BINDING_REMOVED
ASSET_BINDING_INVALIDATED
ASSET_ELIGIBILITY_CHANGED
SCREENPLAY_VALIDATION_UPDATED
```

Projection rules:

- idempotent theo event id/sequence;
- Script binding summary và Asset usage cùng nguồn events;
- gap buộc snapshot/refetch;
- license/validation/revision change có thể làm binding stale/invalid;
- không xóa historical usage khi unbind.

## 10. Test strategy

| Tầng | Nội dung |
| --- | --- |
| Domain | eligibility/binding invariants |
| API | bind/unbind/stale/locked/idempotent |
| Projection | Script summary và Asset usage convergence |
| Component | inspector, picker, resolver, progress |
| Routing | two-way deep-link Desktop/Web |
| E2E | missing requirement → acquire/generate → approve → bind |
| Security | permission, license, cross-project leakage |

Canonical E2E fixture:

```text
Scene 03 requires Bunny, Park, Ball
Bunny/Park eligible, Ball missing
→ generate/import Ball
→ normalize/validate/license/approve
→ bind to Scene 03
→ validate screenplay
→ resource count becomes complete
```

## 11. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Script/Asset projections lệch | event-sourced projection convergence tests |
| Bind asset sai revision | explicit assetRevisionId + stale check |
| Cross-project deep-link leak | permission-filtered route/query |
| Candidate auto-bind quá sớm | explicit eligibility + confirmation |
| Requirement IDs drift | deterministic ID contract |
| License thay đổi sau binding | eligibility change event + invalid state |
| Locked screenplay bị bind tại chỗ | create-draft invariant |

## 12. Stage gate và exit checklist

Gate đề xuất:

```text
VP3D_UI_SCRIPT_ASSET_BINDING_VERIFIED
```

- [ ] Binding aggregate và eligibility service hoàn chỉnh.
- [ ] Bind/unbind revision-aware/idempotent/audited.
- [ ] Script Inspector hiển thị đầy đủ states.
- [ ] Cross-navigation pass Desktop/Web.
- [ ] Missing requirement flow nối được Stage D acquisition.
- [ ] Successful binding rerun validation.
- [ ] Invalid/unknown license bị chặn server-side.
- [ ] Locked/stale/concurrent negative tests pass.
- [ ] Script và Asset projections converge sau replay.
- [ ] Gate `VP3D_UI_SCRIPT_ASSET_BINDING_VERIFIED` pass.

## 13. Bàn giao

Stage F nhận binding/license/approval operations để đưa vào unified proposal và timeline.

Stage G nhận binding draft/context để recovery/conflict không làm mất resolution progress.

Stage I nhận integrated fixture và deterministic golden-flow steps.
