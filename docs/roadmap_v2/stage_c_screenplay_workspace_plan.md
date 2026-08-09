# Kế hoạch Stage C — Screenplay Workspace

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | C |
| Phạm vi | UI8–UI18 |
| Kết quả chính | Script Workspace production-ready |
| Dependency đầu vào | Stage A và Stage B/UI5–UI7 pass |
| Có thể chạy song song | Stage D |
| Bàn giao cho | Stage E, F, G, H và I |
| Độ phức tạp tương đối | XXL |

## 2. Mục tiêu

Xây Script Workspace dùng chung cho Desktop/Web, trong đó:

- screenplay có một structured model canonical ở backend;
- user có thể sửa bằng structured editor hoặc text editor;
- chuyển mode giữ semantic và stable IDs;
- draft edit không tạo revision theo từng keystroke;
- locked revision bất biến và edit phải tạo draft kế tiếp;
- revision comparison là semantic diff;
- thay đổi có downstream impact trước khi commit;
- AI chỉ tạo proposal;
- blocking validation chặn lock.

## 3. Baseline và capability tái sử dụng

Tái sử dụng:

- `CreativeBrief`, `StoryConcept`, screenplay/scene/dialogue identifiers và status trong production domain;
- ordered scene/dialogue structures trong Production IR;
- revision/idempotency/command/event foundation của Stage B;
- invalidation concepts hiện có;
- proposal lifecycle `PENDING/APPROVED/REJECTED` nếu semantics tương thích;
- shared shell, route, state và platform boundaries của Stage A.

Cần xây mới hoặc mở rộng:

- `ScreenplayWorkspaceView`;
- structured editor và text grammar/parser/serializer;
- local edit buffer;
- semantic diff/impact;
- screenplay-specific proposal UI;
- comprehensive validation/lock gate.

## 4. Phạm vi

### Trong phạm vi

- screenplay read model;
- shared layout;
- structured/text editors;
- parser/serializer/round-trip;
- local draft state và save lifecycle;
- immutable revision workflow;
- semantic diff và production impact;
- AI screenplay proposal;
- validation và lock.

### Ngoài phạm vi

- full asset library;
- asset generation implementation;
- universal proposal cho license/asset approval;
- generic conflict merge UX của Stage G;
- Video Workspace.

## 5. Luồng dữ liệu mục tiêu

```text
ScreenplayWorkspaceView
          |
          v
Structured canonical client model
    |                   |
    v                   v
StructuredEditor   ScreenplaySerializer
                         |
                         v
                    TextEditor
                         |
                         v
                  ScreenplayParser
                         |
                         v
                 Candidate model
                         |
                 validate + diff
                         |
                         v
                   edit command
                         |
                         v
                 backend canonical state
```

## 6. Kế hoạch UI8 — Screenplay Read Model

### Contract mục tiêu

```text
ScreenplayWorkspaceView
├── screenplay
├── scenes[] ordered
├── dialogue[] ordered
├── characters[]
├── locations[]
├── validation
├── estimatedDuration
├── revision
└── downstreamBindings
```

### Backlog

- `C-UI8-01`: inventory screenplay structures và migration state hiện có;
- `C-UI8-02`: chốt DTO không lộ internal domain/storage fields;
- `C-UI8-03`: tạo query projector theo project/revision;
- `C-UI8-04`: giữ stable ID và explicit ordering;
- `C-UI8-05`: join character/location/binding summaries ở server;
- `C-UI8-06`: thêm validation/duration summary;
- `C-UI8-07`: thêm query route hoặc workspace projection field;
- `C-UI8-08`: generate TS types/runtime decoder;
- `C-UI8-09`: normalize client state theo entity id;
- `C-UI8-10`: selectors cho story tree/editor/inspector;
- `C-UI8-11`: incremental projection cho screenplay events;
- `C-UI8-12`: test empty, legacy, invalid và large screenplay;
- `C-UI8-13`: benchmark tránh N+1.

### Acceptance

- initial view không cần frontend tự join 20 endpoints;
- scene/dialogue order deterministic;
- explicit revision và current sequence;
- stale/malformed projection có error rõ;
- same snapshot fixture dựng cùng state ở Desktop/Web.

## 7. Kế hoạch UI9 — Script Workspace Layout

### Layout

```text
Project / Revision / Lock / Validation / Save
-------------------------------------------------
Story Tree | Editor                    | Inspector
-------------------------------------------------
AI / Diff / Warnings / Impact / Timeline
```

### Backlog

- `C-UI9-01`: tạo `ScreenplayWorkspace` composition;
- `C-UI9-02`: tạo revision/lock/save header;
- `C-UI9-03`: tạo `SceneTree`;
- `C-UI9-04`: tạo editor host có mode switch;
- `C-UI9-05`: tạo `SceneInspector`;
- `C-UI9-06`: tạo bottom panel host;
- `C-UI9-07`: resize/collapse panes;
- `C-UI9-08`: route giữ selected scene/mode;
- `C-UI9-09`: keyboard navigation/focus management;
- `C-UI9-10`: responsive narrow layout;
- `C-UI9-11`: loading/empty/offline/forbidden/corrupt states;
- `C-UI9-12`: accessibility tests.

### Acceptance

- scene selection đồng bộ tree/editor/inspector/route;
- mode switch không mất dirty buffer;
- focus và keyboard usable;
- cùng layout component chạy trong hai consumer.

## 8. Kế hoạch UI10 — Structured Screenplay Editor

### Backlog theo capability

Screenplay:

- `C-UI10-01`: edit title/logline/metadata;
- `C-UI10-02`: validate required/length fields;
- `C-UI10-03`: track dirty edit unit.

Scene:

- `C-UI10-04`: edit title/location/time/action/characters;
- `C-UI10-05`: add/delete/duplicate scene;
- `C-UI10-06`: split/merge scene;
- `C-UI10-07`: move up/down và drag reorder;
- `C-UI10-08`: stable temporary IDs cho entity mới;
- `C-UI10-09`: selection/focus sau mutation.

Dialogue:

- `C-UI10-10`: add/delete dialogue;
- `C-UI10-11`: character/text/delivery edit;
- `C-UI10-12`: reorder dialogue;
- `C-UI10-13`: unknown character diagnostic;
- `C-UI10-14`: invalid reference diagnostic.

Editing behavior:

- `C-UI10-15`: local undo/redo;
- `C-UI10-16`: gom keystrokes thành edit units;
- `C-UI10-17`: client validation cho immediate feedback;
- `C-UI10-18`: server validation vẫn authoritative;
- `C-UI10-19`: virtualization/performance budget cho large script;
- `C-UI10-20`: component/command-payload tests.

### Acceptance

- tất cả scene actions giữ order/IDs đúng;
- không command từng keystroke;
- undo/redo không vượt server acknowledgement boundary sai;
- invalid local state không silently commit;
- large fixture đạt performance budget được chốt ở UI0/UI8.

## 9. Kế hoạch UI11 — Text Screenplay Editor

### Grammar tối thiểu

- scene heading;
- action paragraph;
- character cue;
- dialogue;
- delivery/parenthetical nếu domain hỗ trợ;
- metadata có representation deterministic;
- whitespace/comment policy rõ ràng.

### Backlog

- `C-UI11-01`: viết grammar/spec và examples;
- `C-UI11-02`: implement deterministic serializer;
- `C-UI11-03`: implement parser thành candidate structured model;
- `C-UI11-04`: trả diagnostics code/range/severity/confidence;
- `C-UI11-05`: thiết kế ID sidecar/anchor mapping;
- `C-UI11-06`: giữ mapping qua edit nhỏ;
- `C-UI11-07`: đánh dấu `PARSE_REQUIRES_REVIEW` khi ambiguous;
- `C-UI11-08`: syntax/diagnostic UI theo dòng;
- `C-UI11-09`: candidate preview và semantic diff;
- `C-UI11-10`: Apply chỉ khi validation/review pass;
- `C-UI11-11`: không persist raw text như canonical source;
- `C-UI11-12`: test Unicode, CRLF/LF, malformed block, duplicate heading;
- `C-UI11-13`: parser input size/time limits.

### Acceptance

- text luôn được parse thành candidate trước save;
- parser không đoán khi confidence thấp;
- diagnostic liên kết được tới dòng/entity;
- stable entities giữ ID nếu semantic không đổi.

## 10. Kế hoạch UI12 — Hybrid Round-trip Contract

### Semantic equivalence

Hai model được coi tương đương khi giữ:

- screenplay metadata có nghĩa;
- scene IDs và order;
- scene headings/location/time/action;
- character references;
- dialogue IDs/text/delivery/order;
- supported metadata;
- downstream identity references.

Formatting thuần túy có thể khác nếu serializer deterministic.

### Backlog

- `C-UI12-01`: implement semantic canonicalizer/comparator;
- `C-UI12-02`: tạo golden corpus từ screenplay fixtures;
- `C-UI12-03`: structured → text → structured tests;
- `C-UI12-04`: text → structured → text tests;
- `C-UI12-05`: property-based generated screenplay tests;
- `C-UI12-06`: multiple mode-switch stability tests;
- `C-UI12-07`: ID stability tests;
- `C-UI12-08`: optional/unknown metadata preservation tests;
- `C-UI12-09`: parser version trong draft state;
- `C-UI12-10`: corpus regression report ở CI.

### Acceptance

- `semantic(A) == semantic(B)` cho golden corpus;
- IDs/order không drift qua nhiều round-trip;
- unsupported content có diagnostic, không bị silently drop;
- round-trip regression chặn merge/release.

## 11. Kế hoạch UI13 — Screenplay Draft Editing

### Local state machine

```text
SERVER
  → LOCAL_MODIFIED
  → SAVING
  → SAVED
  ↘ CONFLICT / FAILED
```

### Backlog

- `C-UI13-01`: lưu base revision/base sequence;
- `C-UI13-02`: lưu ordered edit units;
- `C-UI13-03`: derive dirty state;
- `C-UI13-04`: explicit save và save status;
- `C-UI13-05`: debounce parse/validation, không tạo revision;
- `C-UI13-06`: optimistic update chỉ khi rollback deterministic;
- `C-UI13-07`: navigation/project switch guard;
- `C-UI13-08`: persist recovery snapshot qua Stage G interface;
- `C-UI13-09`: clear draft sau acknowledged state đúng revision;
- `C-UI13-10`: timeout/duplicate response/double-click tests;
- `C-UI13-11`: close/reload tests;
- `C-UI13-12`: telemetry dirty duration/save failures.

### Acceptance

- typing không tạo revision/command storm;
- unsaved work được nhận diện rõ;
- save timeout không làm mất edit units;
- ack của revision cũ không clear draft mới.

## 12. Kế hoạch UI14 — Immutable LOCKED Revision

### Workflow

```text
rev_012 LOCKED
→ user requests edit
→ CREATE_REVISION(parent=rev_012)
→ rev_013 DRAFT
→ apply edit to rev_013
```

### Backlog

- `C-UI14-01`: server invariant chặn mọi mutation vào locked revision;
- `C-UI14-02`: `CREATE_REVISION` command;
- `C-UI14-03`: idempotent draft creation;
- `C-UI14-04`: copy/reference canonical screenplay đúng policy;
- `C-UI14-05`: lineage query;
- `C-UI14-06`: read-only locked UI;
- `C-UI14-07`: edit action mở create-draft confirmation;
- `C-UI14-08`: hiển thị derived-from revision;
- `C-UI14-09`: ancestor content/hash invariant tests;
- `C-UI14-10`: concurrent create draft tests;
- `C-UI14-11`: actor/reason audit.

### Acceptance

- không code path nào mutate `LOCKED`;
- edit locked luôn nhắm draft mới;
- lineage rõ và query được;
- hash của locked ancestor không đổi qua toàn bộ negative suite.

## 13. Kế hoạch UI15 — Revision Comparison

### Backlog

- `C-UI15-01`: semantic diff domain/application service;
- `C-UI15-02`: compare two revisions có permission check;
- `C-UI15-03`: screenplay metadata diff;
- `C-UI15-04`: scene add/delete/move/modify;
- `C-UI15-05`: action/dialogue diff;
- `C-UI15-06`: character/location/binding diff;
- `C-UI15-07`: deterministic grouping/order;
- `C-UI15-08`: compare API contract;
- `C-UI15-09`: `ScreenplayDiff` UI;
- `C-UI15-10`: filters/deep-links;
- `C-UI15-11`: simultaneous move+edit tests;
- `C-UI15-12`: large diff performance tests.

### Acceptance

- diff theo entity/semantic, không chỉ text line;
- moved scene không bị mô tả sai thành delete+add nếu ID giữ nguyên;
- UI điều hướng được tới entity thay đổi;
- output deterministic cho cùng inputs.

## 14. Kế hoạch UI16 — Production Impact Analyzer

### Output mục tiêu

```text
ScreenplayChangeImpact
├── changedScenes
├── changedDialogue
├── changedCharacters
├── changedLocations
├── affectedShots
├── affectedAudio
├── affectedAnimation
├── affectedAssets
├── affectedRenders
└── invalidationIntent
```

### Backlog

- `C-UI16-01`: inventory dependency/invalidation data hiện có;
- `C-UI16-02`: map semantic diff sang invalidation intent;
- `C-UI16-03`: traverse shot/audio/animation/asset/render dependencies;
- `C-UI16-04`: phân loại exact/conservative/unknown;
- `C-UI16-05`: impact dry-run query;
- `C-UI16-06`: bind impact result với base revision/sequence;
- `C-UI16-07`: impact summary UI;
- `C-UI16-08`: drill-down links;
- `C-UI16-09`: confirmation cho high-cost/destructive impact;
- `C-UI16-10`: stale impact phải recompute;
- `C-UI16-11`: no-missed-downstream tests;
- `C-UI16-12`: unknown dependency fail-conservative.

### Acceptance

- user thấy impact trước commit;
- impact không được tái sử dụng sau khi target revision thay đổi;
- unknown không bị hiển thị là zero;
- high-impact change có explicit confirmation.

## 15. Kế hoạch UI17 — AI-assisted Screenplay Editing

### Flow

```text
selection + instruction
→ AI candidate
→ structured validation
→ semantic diff
→ impact
→ human APPROVE/REJECT
→ canonical command
```

### Backlog

- `C-UI17-01`: `ScriptRevisionProposal` contract;
- `C-UI17-02`: bounded selection/context builder;
- `C-UI17-03`: actions Rewrite/Shorten/Expand/Tone/Dialogue/Continuity/Scene/Episode;
- `C-UI17-04`: AI output adapter thành structured candidate;
- `C-UI17-05`: reject malformed/unsupported candidate;
- `C-UI17-06`: domain validation;
- `C-UI17-07`: semantic diff + impact;
- `C-UI17-08`: proposal preview UI;
- `C-UI17-09`: approve/reject actions;
- `C-UI17-10`: approve dispatch canonical command;
- `C-UI17-11`: stale target chuyển requires-review;
- `C-UI17-12`: audit model/agent/actor theo privacy policy;
- `C-UI17-13`: prompt injection/adversarial tests;
- `C-UI17-14`: test AI không gọi direct mutation path.

### Acceptance

- proposal creation không mutate screenplay;
- reject không mutate;
- approve vẫn chịu revision/lock/permission checks;
- stale proposal không auto-apply;
- AI content không bypass command policy.

## 16. Kế hoạch UI18 — Screenplay Validation Gate

### Validation categories

- scene order;
- missing/invalid location;
- unknown character;
- dialogue integrity;
- duration;
- continuity;
- story constraints;
- production constraints;
- required references;
- missing assets.

### Backlog

- `C-UI18-01`: chuẩn hóa validator interfaces;
- `C-UI18-02`: issue code/severity/entity/remediation contract;
- `C-UI18-03`: server validation query/command;
- `C-UI18-04`: cache report theo revision content hash;
- `C-UI18-05`: client incremental hints;
- `C-UI18-06`: validation summary/panel/filter;
- `C-UI18-07`: click-to-entity;
- `C-UI18-08`: tạo `AssetRequirement[]` từ missing references;
- `C-UI18-09`: `LOCK_REVISION` revalidate server-side;
- `C-UI18-10`: blocking count > 0 chặn lock;
- `C-UI18-11`: warning acknowledgement policy nếu cần;
- `C-UI18-12`: TOCTOU validate-vs-lock tests;
- `C-UI18-13`: stale report invalidation tests;
- `C-UI18-14`: validation evidence receipt.

### Acceptance

- UI và server dùng cùng issue semantics;
- blocking issue luôn chặn lock;
- report cũ không lock revision mới;
- missing asset requirements sẵn sàng cho Stage E;
- `VP3D_UI_SCRIPT_WORKSPACE_VERIFIED` pass.

## 17. Test strategy

| Tầng | Nội dung |
| --- | --- |
| Pure unit | parser, serializer, semantic compare/diff, reducers |
| Property/golden | round-trip, ID/order stability |
| Component | tree, editors, inspector, diff, impact, validation |
| API integration | query, edit, create revision, lock, proposal |
| Event integration | scene update/revision/validation projections |
| Consumer | Desktop/Web cùng behavioral fixtures |
| E2E | structured → text → proposal → validate → lock |

Negative suite bắt buộc:

- malformed/ambiguous text;
- duplicate order/unknown character;
- command timeout/duplicate acknowledgement;
- edit locked revision;
- stale proposal/impact/report;
- blocking validation;
- large script;
- offline during save;
- route tới deleted scene.

## 18. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Text trở thành source of truth thứ hai | parser candidate + command only |
| Parser silently drops content | diagnostics + semantic comparator |
| ID drift qua mode switch | sidecar mapping + corpus tests |
| Editor command storm | edit-unit buffer |
| Locked revision bị sửa qua path phụ | server invariant + hash tests |
| Impact bỏ sót downstream | conservative traversal + unknown state |
| AI bypass/hallucinated entity | structured validation + proposal policy |
| Large screenplay chậm | normalized state, selectors, virtualization |

## 19. Stage exit checklist

- [ ] UI8 read model hoàn chỉnh và performant.
- [ ] UI9 shared layout usable/accessibility pass.
- [ ] UI10 structured actions đầy đủ.
- [ ] UI11 parser/serializer có diagnostics.
- [ ] UI12 semantic round-trip và IDs pass.
- [ ] UI13 local draft không mất dữ liệu.
- [ ] UI14 locked revision invariant pass.
- [ ] UI15 semantic diff pass.
- [ ] UI16 impact review pass.
- [ ] UI17 AI proposal không direct mutate.
- [ ] UI18 blocking validation chặn lock.
- [ ] Desktop/Web consumer tests pass.
- [ ] `VP3D_UI_SCRIPT_WORKSPACE_VERIFIED` pass.

## 20. Bàn giao

Stage E nhận screenplay entities, `AssetRequirement[]`, downstream bindings và route IDs.

Stage F nhận proposal/diff/impact components.

Stage G nhận base revision, edit units và semantic diff để xây three-way conflict handling.
