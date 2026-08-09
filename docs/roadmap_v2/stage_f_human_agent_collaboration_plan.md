# Kế hoạch Stage F — Human + Agent Collaboration

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | F |
| Phạm vi | UI37–UI38 |
| Kết quả chính | Unified proposal/approval và production activity timeline |
| Dependency đầu vào | Stage B command/event; Stage C/D/E sensitive operations |
| Có thể phối hợp | Stage E và Stage G |
| Bàn giao cho | Stage H và I |
| Độ phức tạp tương đối | M |

## 2. Mục tiêu

Tạo Human Production Control Layer cho các thay đổi do agent đề xuất. Sau Stage F:

- AI/agent không trực tiếp mutate screenplay, asset binding, license hoặc asset approval;
- mọi thay đổi nhạy cảm đi qua proposal → preview → impact → human/policy approval;
- proposal gắn target revision và affected entities;
- stale proposal không auto-apply;
- approval tạo canonical command có audit;
- Script và Assets dùng chung timeline production dễ hiểu;
- timeline không phải raw debug log và replay không duplicate.

## 3. Phạm vi

### Trong phạm vi

- unified proposal aggregate/contract;
- proposal create/list/detail/approve/reject;
- permission và policy boundary;
- diff/impact composition;
- human-readable activity projection;
- realtime timeline UI;
- adversarial tests chống bypass.

### Ngoài phạm vi

- AI model/provider implementation;
- generic chat UI;
- automatic policy engine mới ngoài capability hiện hữu;
- direct mutation cho sensitive state;
- production debug/log viewer.

## 4. Sensitive operation policy

Các operation sau mặc định yêu cầu proposal nếu actor là agent:

```text
SCREENPLAY_CHANGE
ASSET_BINDING_CHANGE
LICENSE_CHANGE
ASSET_APPROVAL_CHANGE
```

Các bước bắt buộc:

```text
Agent intent
→ Proposal persisted
→ Domain validation
→ Semantic diff
→ Impact analysis
→ Human/policy decision
→ Canonical command
→ Domain event
→ Timeline projection
```

Không có route/tool đặc biệt cho agent bypass canonical command dispatcher.

## 5. Proposal model mục tiêu

```text
ProductionChangeProposal
├── proposalId, proposalType
├── projectId, targetRevisionId, baseSequence
├── affectedEntities[]
├── candidate/diff/impact
├── createdByAgent, createdAt
├── status
├── decisionBy, decisionAt, decisionReason
├── resultingCommandId/revisionId
└── version/hash
```

Status đề xuất:

```text
PENDING
REQUIRES_REVIEW
APPROVED
REJECTED
SUPERSEDED
EXPIRED
APPLY_FAILED
```

Nếu phải giữ enum hiện hữu `PENDING/APPROVED/REJECTED`, các trạng thái bổ sung có thể là reason/substatus nhưng semantics phải được tài liệu hóa.

## 6. Kế hoạch UI37 — Unified Change Proposal

### Domain/application backlog

- `F-UI37-01`: inventory proposal lifecycle hiện có;
- `F-UI37-02`: chốt universal proposal aggregate;
- `F-UI37-03`: discriminated candidate payload per proposal type;
- `F-UI37-04`: immutable proposal content/hash sau submit;
- `F-UI37-05`: actor/permission/policy checks;
- `F-UI37-06`: validate target revision/base sequence;
- `F-UI37-07`: domain validation adapter;
- `F-UI37-08`: diff adapter cho screenplay/binding/license/approval;
- `F-UI37-09`: impact adapter;
- `F-UI37-10`: create/list/detail query/command handlers;
- `F-UI37-11`: approve handler tạo canonical command;
- `F-UI37-12`: reject handler lưu reason, không mutate target;
- `F-UI37-13`: stale detection → requires review;
- `F-UI37-14`: expire/supersede policy;
- `F-UI37-15`: apply failure semantics;
- `F-UI37-16`: proposal/decision/domain events;
- `F-UI37-17`: audit correlation proposal→command→revision;
- `F-UI37-18`: idempotency/concurrency tests.

### Frontend backlog

- `F-UI37-19`: proposal inbox/list/filter;
- `F-UI37-20`: proposal detail header/actor/target;
- `F-UI37-21`: reuse semantic diff UI;
- `F-UI37-22`: reuse impact UI;
- `F-UI37-23`: validation/eligibility issues;
- `F-UI37-24`: approve confirmation;
- `F-UI37-25`: reject reason dialog;
- `F-UI37-26`: stale/requires-review UX;
- `F-UI37-27`: apply progress/failure UX;
- `F-UI37-28`: deep-link tới affected entities;
- `F-UI37-29`: realtime status update;
- `F-UI37-30`: accessibility/permission states.

### Security/adversarial backlog

- `F-UI37-31`: agent direct sensitive command bị từ chối nếu thiếu approved proposal context;
- `F-UI37-32`: proposal không được tự approve bởi creator nếu policy cấm;
- `F-UI37-33`: tampered candidate/hash bị từ chối;
- `F-UI37-34`: stale proposal không auto-rebase;
- `F-UI37-35`: prompt content không được diễn giải thành permission;
- `F-UI37-36`: cross-project proposal access bị chặn;
- `F-UI37-37`: duplicate approve không double-apply.

### Acceptance

- create/reject không mutate target;
- approve vẫn qua command/revision/lock/permission checks;
- proposal immutable và traceable;
- stale proposal bắt buộc review/recompute;
- agent không có bypass path.

## 7. Kế hoạch UI38 — Production Activity Timeline

### Activity model

```text
ProductionActivity
├── activityId
├── projectId/revisionId
├── category
├── actor
├── title/summary
├── entityLinks[]
├── status
├── occurredAt
├── sourceEventIds[]
└── correlationId
```

Categories:

```text
SCRIPT, ASSET, BINDING, JOB, PROPOSAL, VALIDATION, SYSTEM
```

### Projection backlog

- `F-UI38-01`: define event→activity mapping registry;
- `F-UI38-02`: human-readable templates/codes;
- `F-UI38-03`: group technical events theo user intent/correlation;
- `F-UI38-04`: preserve source event links cho audit;
- `F-UI38-05`: idempotent projection/checkpoint;
- `F-UI38-06`: pagination/deterministic order;
- `F-UI38-07`: project/revision/category filters;
- `F-UI38-08`: actor display policy;
- `F-UI38-09`: sanitize prompt/log/secret/path;
- `F-UI38-10`: replay/fresh projection equivalence;
- `F-UI38-11`: activity retention policy.

### Frontend backlog

- `F-UI38-12`: shared Timeline panel/page;
- `F-UI38-13`: realtime append without duplicate/jump;
- `F-UI38-14`: filters and pagination;
- `F-UI38-15`: actor/category/status badges;
- `F-UI38-16`: entity/revision deep-links;
- `F-UI38-17`: grouped activity expansion;
- `F-UI38-18`: loading/empty/offline states;
- `F-UI38-19`: timeline in Script and Assets;
- `F-UI38-20`: accessibility and long-history performance tests.

### Acceptance

- timeline mô tả production actions, không dump raw event/debug logs;
- same events tạo same activities sau replay;
- không duplicate khi reconnect;
- actor/action/revision/entity/correlation truy vết được;
- sensitive data không xuất hiện.

## 8. Permission và audit matrix

| Action | Agent | Human reviewer | System/policy |
| --- | --- | --- | --- |
| Create proposal | Có theo permission | Có | Có theo policy |
| Edit submitted proposal | Không; supersede | Không; supersede | Không; supersede |
| Approve | Không mặc định | Có theo role | Chỉ explicit policy |
| Reject | Có thể withdraw riêng | Có theo role | Theo policy |
| Execute sensitive command | Chỉ qua approved proposal | Qua canonical command | Qua audited policy |

Mọi decision cần actor, timestamp, reason và correlation id.

## 9. Test strategy

| Tầng | Nội dung |
| --- | --- |
| Domain | proposal invariants/status transitions |
| API | create/approve/reject/stale/permission/idempotency |
| Security | bypass, tamper, cross-project, self-approval policy |
| Projection | event→activity, grouping, replay convergence |
| Component | inbox, detail, diff, impact, decision, timeline |
| E2E | AI screenplay proposal và agent asset/binding proposal |

Canonical negative tests:

- agent gọi direct update;
- approve proposal nhắm locked/stale revision;
- proposal candidate bị tamper;
- proposal creator tự approve trái policy;
- duplicate approve;
- apply command thất bại;
- timeline replay duplicate;
- event có secret/raw prompt/path.

## 10. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| Proposal trở thành command phụ | approve luôn chuyển canonical command |
| Agent bypass bằng endpoint khác | centralized sensitive-operation policy |
| Stale proposal apply sai revision | base revision/sequence + recompute |
| Timeline quá kỹ thuật | event→human activity projector |
| Timeline mất audit detail | giữ source event ids/correlation |
| Sensitive data leak | allowlisted templates/sanitization tests |
| Duplicate approve | idempotency + terminal state invariant |

## 11. Stage gate và exit checklist

Gate đề xuất:

```text
VP3D_UI_HUMAN_AGENT_COLLABORATION_VERIFIED
```

- [ ] Unified proposal model bao phủ 4 sensitive operation groups.
- [ ] Proposal immutable và versioned/superseded đúng.
- [ ] Approve/reject có permission, reason và audit.
- [ ] Approve tạo canonical command, không direct mutation.
- [ ] Stale proposal bắt buộc review.
- [ ] Agent bypass/tamper tests pass.
- [ ] Timeline projector idempotent/replay-safe.
- [ ] Script và Assets dùng cùng timeline component.
- [ ] Timeline không lộ sensitive data.
- [ ] Gate `VP3D_UI_HUMAN_AGENT_COLLABORATION_VERIFIED` pass.

## 12. Bàn giao

Stage G nhận proposal/draft states cần recovery và stale conflict handling.

Stage H nhận adversarial fixtures, proposal lifecycle và timeline replay suite.

Stage I dùng proposal/timeline làm evidence cho golden workflows.
