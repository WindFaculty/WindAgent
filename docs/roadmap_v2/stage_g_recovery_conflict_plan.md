# Kế hoạch Stage G — Offline, Recovery & Conflict Handling

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | G |
| Phạm vi | UI39–UI40 |
| Kết quả chính | Restart/reconnect an toàn và semantic conflict resolution |
| Dependency đầu vào | Stage A state, Stage B command/event, Stage C diff/draft |
| Phối hợp | Stage E/F state recovery |
| Bàn giao cho | Stage H và I |
| Độ phức tạp tương đối | L |

## 2. Mục tiêu

Đảm bảo frontend không mất local work hoặc silently overwrite canonical state khi refresh, restart, mất mạng hay concurrent edit. Sau Stage G:

- project/page/selection/editor mode/last sequence được restore;
- unsaved draft có versioned recovery snapshot;
- cache chỉ là hint, không phải canonical state;
- bootstrap luôn reconcile với server snapshot/revision;
- sequence gap buộc resync;
- `409 REJECTED_STALE` mở conflict workflow;
- non-overlapping changes có thể merge có kiểm soát;
- ambiguous overlap bắt buộc human review;
- merge tạo revision/command mới trên latest base.

## 3. Các nguồn conflict

Ngay cả single-user deployment vẫn có concurrent writers:

```text
Frontend Desktop
Frontend Web/tab khác
Agent proposal approval
Worker/system automation
Background workflow
```

Stage G không cố khóa toàn hệ thống để tránh conflict. Nó dùng optimistic concurrency, durable drafts và explicit resolution.

## 4. Phạm vi

### Trong phạm vi

- recovery schema/storage;
- bootstrap reconciliation;
- offline/read-only states;
- stale draft detection;
- semantic three-way diff/merge workflow;
- local draft retention/discard;
- restart/two-writer tests.

### Ngoài phạm vi

- full offline mutation queue đồng bộ tự động;
- CRDT/realtime collaborative text editing;
- silent auto-rebase ambiguous edits;
- recovery của raw provider secrets/signed URLs;
- backup/restore toàn database.

## 5. Recovery model mục tiêu

```text
ProductionRecoverySnapshot
├── schemaVersion
├── savedAt/expiresAt
├── projectId/page/route
├── revisionId/baseSequence
├── selectedSceneId/selectedAssetId
├── editorMode
├── draftKind/parserVersion
├── editUnits or encrypted/local draft payload
├── lastAcknowledgedCommand
└── checksum
```

Không persist:

- access/refresh tokens;
- signed artifact URLs;
- provider credentials;
- internal filesystem paths nếu không cần và không được adapter bảo vệ;
- raw server state như canonical truth.

## 6. Kế hoạch UI39 — Frontend State Recovery

### Storage strategy

- preference nhỏ: localStorage-like adapter;
- screenplay draft/structured payload lớn: IndexedDB hoặc platform storage adapter;
- Desktop có thể dùng secure/native storage adapter nếu cần;
- contract và reconciliation logic dùng chung;
- storage key scope theo user/workspace/project.

### Backlog

- `G-UI39-01`: inventory Web `StateRecoveryEngine` hiện có;
- `G-UI39-02`: define versioned recovery schema;
- `G-UI39-03`: storage adapter interface;
- `G-UI39-04`: Web implementation;
- `G-UI39-05`: Desktop implementation;
- `G-UI39-06`: checksum/corruption detection;
- `G-UI39-07`: debounce snapshot writes;
- `G-UI39-08`: save project/page/selection/mode/sequence;
- `G-UI39-09`: save screenplay draft/edit units;
- `G-UI39-10`: save asset acquisition/resolution progress khi an toàn;
- `G-UI39-11`: save proposal decision form draft nếu cần;
- `G-UI39-12`: schema migration/expiry;
- `G-UI39-13`: clear per project/user/logout;
- `G-UI39-14`: avoid tokens/URLs/secrets/path leakage;
- `G-UI39-15`: storage quota/failure UX.

### Bootstrap algorithm

```text
1. Parse route/deep-link.
2. Load recovery metadata.
3. Fetch authoritative workspace snapshot.
4. Compare project/revision/sequence.
5. If same base: restore draft and replay after last sequence.
6. If server advanced: mark draft stale and open compare/recovery.
7. If cursor gap/expired: fetch fresh snapshot.
8. Restore selection only if entity still exists/authorized.
9. Never dispatch recovered draft automatically.
```

### Bootstrap backlog

- `G-UI39-16`: implement bootstrap/reconcile state machine;
- `G-UI39-17`: route takes precedence rules;
- `G-UI39-18`: verify recovered entity IDs;
- `G-UI39-19`: replay/refetch integration;
- `G-UI39-20`: stale draft state;
- `G-UI39-21`: corrupt/unsupported snapshot clear flow;
- `G-UI39-22`: explicit offline read-only mode;
- `G-UI39-23`: manual reconnect/refetch;
- `G-UI39-24`: metrics restore success/failure/stale/corrupt.

### Test matrix

- clean first launch;
- refresh with no draft;
- refresh with valid draft;
- Desktop restart with valid draft;
- server revision advanced while app closed;
- selected scene/asset deleted;
- last sequence expired;
- corrupt recovery JSON/checksum;
- schema version old/new;
- storage unavailable/quota exceeded;
- logout/user switch;
- offline launch;
- signed URL/token not present in storage.

### Acceptance

- valid local draft không mất qua refresh/restart;
- cached canonical data không overwrite server;
- stale draft được nhận diện trước apply;
- corrupt cache fail safe;
- offline state không giả saved/synced;
- recovery data không chứa secret/token/path không cần thiết.

## 7. Kế hoạch UI40 — Concurrent Edit Conflict

### Input contract

```text
Base: revision user bắt đầu sửa
Local: base + local edit units
Remote: latest server revision
```

### Conflict classifications

```text
NO_CONFLICT
LOCAL_ONLY_CHANGE
REMOTE_ONLY_CHANGE
NON_OVERLAPPING_MERGEABLE
OVERLAPPING_REQUIRES_REVIEW
ENTITY_DELETED
ORDER_CONFLICT
UNSUPPORTED/UNKNOWN
```

### Backend/application backlog

- `G-UI40-01`: chuẩn hóa 409 stale response;
- `G-UI40-02`: expose current revision/sequence;
- `G-UI40-03`: query base/current revisions;
- `G-UI40-04`: semantic three-way comparison service;
- `G-UI40-05`: classify entity/field/order conflicts;
- `G-UI40-06`: build merge candidate only for proven-safe edits;
- `G-UI40-07`: validate merged candidate;
- `G-UI40-08`: compute impact on latest base;
- `G-UI40-09`: merge apply bằng canonical command/new revision;
- `G-UI40-10`: reject stale merge result;
- `G-UI40-11`: audit conflict/decision/result;
- `G-UI40-12`: conflict storm/concurrency tests.

### Frontend backlog

- `G-UI40-13`: transition save state to `CONFLICT` on 409;
- `G-UI40-14`: giữ nguyên local draft/edit units;
- `G-UI40-15`: fetch current revision/three-way result;
- `G-UI40-16`: summary Your revision vs Current;
- `G-UI40-17`: `View Changes` semantic diff;
- `G-UI40-18`: per-entity/field conflict choices;
- `G-UI40-19`: `Merge Into New Revision`;
- `G-UI40-20`: `Discard Local Changes` với confirmation;
- `G-UI40-21`: handle entity deleted/order conflicts;
- `G-UI40-22`: rerun validation/impact;
- `G-UI40-23`: keep draft until server acknowledgement;
- `G-UI40-24`: update recovery snapshot after resolution;
- `G-UI40-25`: accessibility/large-conflict UX.

### Auto-merge policy

Chỉ auto-compose candidate khi:

- cùng base revision được xác định;
- local và remote sửa entity/field độc lập;
- ordering/reference invariant vẫn đúng;
- validator pass;
- impact được recompute;
- user vẫn xem/confirm nếu change có production impact đáng kể.

Không auto-merge:

- cùng dialogue/action field;
- một bên xóa entity bên kia sửa;
- scene reorder chồng chéo;
- parser mapping ambiguous;
- asset binding/license/approval conflict;
- unknown dependency/impact.

### Acceptance

- stale edit không blind retry;
- local draft tồn tại đến khi user xác nhận resolve/discard;
- ambiguous overlap không auto-apply;
- merge nhắm latest revision và tạo auditable result;
- repeated conflict không tạo revision storm.

## 8. Integration với event stream

- last applied sequence persist độc lập với draft;
- event của project khác không đổi recovery state;
- event làm revision advance khi local dirty chuyển state `STALE/CONFLICT_PENDING`;
- sequence gap dừng projection và refetch;
- ack event/HTTP response dedupe theo command/event IDs;
- replay không clear dirty buffer nếu revision/command không khớp.

## 9. Test strategy

| Tầng | Nội dung |
| --- | --- |
| Unit | schema migration, checksum, reconcile, conflict classifier |
| Property | non-overlapping/overlapping semantic edits |
| Component | recovery prompt, offline, conflict dialog |
| API | stale response, merge command, latest-base check |
| Event | replay/gap/ack while dirty |
| Desktop E2E | edit → restart → recover; API restart |
| Browser E2E | refresh, offline, two-tab conflict |
| Security | cache inspection, user/project isolation |

Canonical concurrency cases:

- Frontend vs Agent proposal approval;
- Frontend vs Worker automation;
- Desktop vs Web;
- Web tab A vs tab B;
- local text edit vs remote structured edit;
- remote delete vs local modify;
- simultaneous scene reorder;
- binding/license state changed remotely.

## 10. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Cache trở thành source of truth | reconcile trước restore/apply |
| Secret/token persist | allowlisted schema + security test |
| Ack cũ clear draft mới | command/revision correlation |
| Auto-merge làm mất semantic | strict classifier + validation |
| Recovery schema drift | version/migration/expiry |
| Quota/corrupt storage | graceful failure + export/clear option nếu policy cho phép |
| Conflict lặp vô hạn | latest-base recheck + user-visible retry limit |

## 11. Stage gate và exit checklist

Gate đề xuất:

```text
VP3D_UI_RECOVERY_CONFLICT_VERIFIED
```

- [ ] Versioned recovery schema và adapters hoàn chỉnh.
- [ ] No secret/token leakage tests pass.
- [ ] Web refresh và Desktop restart recovery pass.
- [ ] Server-advanced stale draft được phát hiện.
- [ ] Cache không overwrite canonical state.
- [ ] 409 mở semantic conflict workflow.
- [ ] Non-overlap merge và overlap review tests pass.
- [ ] Discard có explicit confirmation.
- [ ] Merge tạo latest-based auditable command/revision.
- [ ] Two-tab/Desktop-vs-Web E2E pass.
- [ ] Gate `VP3D_UI_RECOVERY_CONFLICT_VERIFIED` pass.

## 12. Bàn giao

Stage H nhận recovery/concurrency fixtures và deterministic failure injection hooks.

Stage I sử dụng restart/reload/conflict checks trong golden acceptance và release readiness.
