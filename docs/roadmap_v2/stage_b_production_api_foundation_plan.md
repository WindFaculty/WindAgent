# Kế hoạch Stage B — Production API Foundation

## 1. Thông tin kế hoạch

| Thuộc tính | Giá trị |
| --- | --- |
| Stage | B |
| Phạm vi | UI5–UI7 |
| Kết quả chính | Durable snapshot, canonical command và realtime replay |
| Dependency đầu vào | Stage A UI1–UI3 pass |
| Bàn giao cho | Stage C, D, F, G và H |
| Độ phức tạp tương đối | XL |

## 2. Mục tiêu

Tạo Production API V2 thật thay cho PoC/in-memory semantics. Sau Stage B:

- project/workspace snapshot được đọc từ repository/application service;
- mutation chỉ đi qua canonical command envelope;
- revision, lock và idempotency được enforce server-side;
- state mutation, domain event và idempotency response có transaction boundary rõ ràng;
- frontend khởi tạo bằng snapshot rồi tiếp tục bằng event replay;
- disconnect/reconnect không gây gap hoặc double-apply.

## 3. Baseline và quyết định tái sử dụng

Tái sử dụng:

- Production IR và video-production domain hiện có;
- Unit of Work/repository conventions trong storage;
- `SqlEventStore` và durable event primitives nếu contract phù hợp;
- SSE/WebSocket implementation trong `apps/api/windagent_api/routers/v2_events.py`;
- `last_sequence` replay semantics;
- Web event stream client skeleton và dedupe behavior.

Không tái sử dụng nguyên trạng:

- in-memory revision/idempotency của PoC;
- workspace receipt/artifact như runtime repository;
- frontend DTO viết tay không có schema validation;
- endpoint mutation rải rác theo từng field/entity.

## 4. Phạm vi

### Trong phạm vi

- production project/revision persistence;
- read-model projection;
- project/workspace query endpoints;
- canonical command endpoint;
- idempotency, optimistic concurrency và lock invariant;
- production event envelope/filter/replay;
- generated TypeScript contracts và shared clients;
- API, repository và replay integration tests.

### Ngoài phạm vi

- UI screenplay/asset hoàn chỉnh;
- parser/serializer;
- asset taxonomy mới;
- semantic merge UI;
- Video Workspace.

## 5. Kiến trúc mục tiêu

```text
HTTP Query                HTTP Command
    |                          |
    v                          v
Query Service           Command Dispatcher
    |                    | validate envelope
    |                    | check idempotency
    |                    | check revision/lock
    |                    | execute domain rule
    v                    v
Read Model            Unit of Work/Repositories
    ^                    | persist + append event
    |                    | store result
    +------ Projector <--+
              |
              v
       SSE/WebSocket replay
```

## 6. Work package nền — Persistence và application services

### Logical records

| Record | Trường tối thiểu |
| --- | --- |
| ProductionProject | id, status, active revision, created/updated |
| ProductionRevision | id, project, parent, status, hash, sequence |
| WorkspaceReadModel | project/revision projection, checkpoint |
| IdempotencyRecord | scope, key, request hash, response, status, expiry |
| ProductionEvent | event id, sequence, project, revision, type, payload |
| ProjectionCheckpoint | projector id, last sequence, updated time |

### Backlog

- `B-BASE-01`: inventory UnitOfWork, SQL repositories và event store hiện hữu;
- `B-BASE-02`: định nghĩa repository ports ở application/domain boundary;
- `B-BASE-03`: chốt revision aggregate và optimistic version field;
- `B-BASE-04`: thiết kế migration SQLite;
- `B-BASE-05`: thiết kế migration Postgres theo production lane;
- `B-BASE-06`: implement project/revision repositories;
- `B-BASE-07`: implement idempotency repository với unique scope/key;
- `B-BASE-08`: implement read-model/checkpoint repository;
- `B-BASE-09`: bảo đảm domain mutation + event append + idempotency result atomic;
- `B-BASE-10`: tạo repository fakes không thay semantics;
- `B-BASE-11`: tạo deterministic fixture factory;
- `B-BASE-12`: test process restart và concurrent writers;
- `B-BASE-13`: ghi migration/rollback/forward-only policy.

### Invariant

- revision id không tái sử dụng;
- locked revision content hash bất biến;
- sequence tăng đơn điệu;
- command thành công có đúng một durable event group;
- idempotent replay không chạy domain handler lần hai;
- projection có checkpoint độc lập với canonical state.

## 7. Kế hoạch UI5 — Production Query API

### Endpoints mục tiêu

```http
GET /api/v2/video-production/projects/{project_id}
GET /api/v2/video-production/projects/{project_id}/workspace
```

### Workspace response tối thiểu

```json
{
  "project_id": "vp_001",
  "project_status": "ACTIVE",
  "revision_id": "rev_012",
  "revision_status": "DRAFT",
  "screenplay": {},
  "asset_summary": {},
  "pipeline_summary": {},
  "current_sequence": 490
}
```

### Backend backlog

- `B-UI5-01`: tạo project detail query service;
- `B-UI5-02`: tạo workspace projector/view model;
- `B-UI5-03`: resolve active hoặc explicit revision có kiểm tra permission;
- `B-UI5-04`: đọc snapshot và sequence trong consistency boundary;
- `B-UI5-05`: trả projection status nếu projector lag;
- `B-UI5-06`: hỗ trợ empty project và project chưa có screenplay;
- `B-UI5-07`: chuẩn hóa RFC 7807 error responses;
- `B-UI5-08`: không serialize filesystem path, secret hoặc raw prompt;
- `B-UI5-09`: thêm ETag/conditional request nếu payload vượt budget;
- `B-UI5-10`: generate OpenAPI/JSON Schema;
- `B-UI5-11`: benchmark N+1 và large project projection.

### Frontend backlog

- `B-UI5-12`: generate/update `production-contracts` types;
- `B-UI5-13`: thêm runtime decoder cho untrusted JSON;
- `B-UI5-14`: implement `projectClient`;
- `B-UI5-15`: map response vào shared project store;
- `B-UI5-16`: implement loading, empty, stale, forbidden và unavailable states;
- `B-UI5-17`: cancel stale request khi project switch;
- `B-UI5-18`: test response field addition/removal/enum mismatch.

### Acceptance

- project/workspace lấy từ durable repository;
- response có current sequence chính xác;
- không yêu cầu frontend gọi hàng chục endpoint để dựng initial view;
- project không tồn tại/không có quyền có error contract ổn định;
- schema fixture decode được trong TypeScript;
- restart backend không thay đổi snapshot semantics.

## 8. Kế hoạch UI6 — Canonical Command API

### Endpoint mục tiêu

```http
POST /api/v2/video-production/commands
X-Idempotency-Key: <key>
```

Có thể dùng scoped path `/projects/{project_id}/commands`, nhưng chỉ chọn một canonical route và không nhân đôi behavior.

### Envelope

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

### Backend backlog

- `B-UI6-01`: định nghĩa discriminated command envelope;
- `B-UI6-02`: tạo command registry/dispatcher;
- `B-UI6-03`: validate command type/payload/size;
- `B-UI6-04`: validate actor permission và policy;
- `B-UI6-05`: require non-empty idempotency key;
- `B-UI6-06`: hash canonical request và phát hiện key reuse mismatch;
- `B-UI6-07`: check project và target revision;
- `B-UI6-08`: check locked revision invariant;
- `B-UI6-09`: execute domain handler trong Unit of Work;
- `B-UI6-10`: persist event + response atomically;
- `B-UI6-11`: trả updated revision/current sequence/delta;
- `B-UI6-12`: audit actor `HUMAN`, `AGENT`, `SYSTEM` và reason;
- `B-UI6-13`: chuẩn hóa conflict/error mapping;
- `B-UI6-14`: rate limit và correlation id;
- `B-UI6-15`: test concurrent command cùng revision.

### Conflict response

```json
{
  "status": 409,
  "code": "REJECTED_STALE",
  "target_revision_id": "rev_012",
  "current_revision_id": "rev_013",
  "current_sequence": 497,
  "correlation_id": "corr_..."
}
```

### Frontend backlog

- `B-UI6-16`: implement `commandClient`;
- `B-UI6-17`: sinh idempotency key theo một user intent;
- `B-UI6-18`: giữ nguyên key khi retry transport-safe;
- `B-UI6-19`: không retry 409 hoặc domain rejection;
- `B-UI6-20`: tạo lifecycle `IDLE/SUBMITTING/ACKNOWLEDGED/CONFLICT/FAILED`;
- `B-UI6-21`: map response delta/event acknowledgement;
- `B-UI6-22`: expose typed command hooks/actions;
- `B-UI6-23`: architecture test cấm mutation fetch trực tiếp trong component.

### Idempotency cases bắt buộc

| Trường hợp | Kết quả |
| --- | --- |
| cùng key + cùng payload | trả cùng response, không chạy lại |
| cùng key + payload khác | conflict/rejection |
| retry sau timeout | có thể nhận original result |
| process restart | record vẫn tồn tại |
| hai request đồng thời cùng key | một execution |
| key expired theo policy | behavior được tài liệu hóa |

### Acceptance

- stale command không mutate;
- locked command không mutate;
- idempotent replay không double event;
- thành công trả revision/sequence mới;
- failure có stable problem code;
- database restart không mất idempotency semantics.

## 9. Kế hoạch UI7 — Real-time Production Synchronization

### Protocol mục tiêu

```text
GET workspace snapshot at sequence N
→ connect stream(last_sequence=N, project_id=P)
→ apply N+1...M idempotently
→ disconnect
→ reconnect(last_sequence=M)
→ replay M+1...K
→ continue live
```

### Event envelope

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

### Backend backlog

- `B-UI7-01`: inventory exact SSE/WS routes và auth behavior hiện có;
- `B-UI7-02`: chốt production event namespace/envelope;
- `B-UI7-03`: thêm project/revision/aggregate metadata;
- `B-UI7-04`: filter subscription theo authorized project;
- `B-UI7-05`: replay từ exclusive `last_sequence`;
- `B-UI7-06`: xử lý cursor quá cũ bằng explicit resync response;
- `B-UI7-07`: heartbeat/terminal/error semantics;
- `B-UI7-08`: backpressure và bounded batch;
- `B-UI7-09`: test permission không leak cross-project event;
- `B-UI7-10`: metrics connection, replay size, lag và gaps.

### Shared frontend backlog

- `B-UI7-11`: chuyển/bọc Web event skeleton thành shared client;
- `B-UI7-12`: hỗ trợ SSE primary và WS khi capability cần;
- `B-UI7-13`: state machine `CONNECTED/RECONNECTING/REPLAYING/STALE/OFFLINE`;
- `B-UI7-14`: bounded dedupe cache theo event id/sequence;
- `B-UI7-15`: projection idempotent;
- `B-UI7-16`: phát hiện duplicate, out-of-order và gap;
- `B-UI7-17`: gap dừng apply và refetch snapshot;
- `B-UI7-18`: reconnect backoff + jitter + cancellation;
- `B-UI7-19`: online/offline awareness;
- `B-UI7-20`: sync status indicator và manual retry;
- `B-UI7-21`: cleanup connection khi project switch/unmount;
- `B-UI7-22`: dùng cùng implementation trong Desktop/Web.

### Replay test matrix

- disconnect ngay sau snapshot;
- disconnect sau một event;
- server gửi duplicate event;
- client nhận event out of order;
- missing sequence;
- cursor quá cũ;
- access bị revoke giữa connection;
- project switch trong replay;
- backend restart;
- client restart với persisted last sequence.

### Acceptance

- state sau snapshot+replay giống fresh snapshot;
- không gap, không double-apply;
- stale/gap được hiển thị, không giả connected;
- Desktop/Web dùng cùng event projection;
- `VP3D_UI_P7_REALTIME_STATE_VERIFIED` pass.

## 10. Contract/versioning strategy

- OpenAPI/JSON Schema là nguồn generation cho TypeScript;
- frontend vẫn runtime-validate boundary JSON;
- thêm optional field là compatible;
- xóa/đổi required field là breaking;
- enum mới phải có unknown handling hoặc coordinated version;
- event payload có version khi evolution không backward-compatible;
- command type/payload được discriminated và test fixture;
- internal Python model không serialize trực tiếp nếu chứa field không an toàn.

## 11. Test strategy

| Tầng | Nội dung |
| --- | --- |
| Domain unit | revision/lock/idempotency invariants |
| Repository | SQLite/Postgres persistence, unique/concurrency |
| API integration | query, command, error mapping, auth |
| Event integration | append, stream, replay, gap/cursor |
| Frontend unit | decoder, client, projection, reconnect |
| Consumer | Desktop/Web cùng snapshot/event fixture |
| Restart | API/DB/client restart recovery |

Không dùng polling như substitute cho realtime acceptance.

## 12. Observability và security

Metrics tối thiểu:

- query latency và projection lag;
- command success/rejection/conflict;
- idempotency hit/mismatch;
- event append/stream/replay counts;
- connection/reconnect/gap;
- stale revision rate.

Security:

- project authorization ở query, command và event stream;
- input size/rate limit;
- không log raw secret/token/prompt;
- không trả internal path;
- correlation id thay cho stack trace ở client;
- audit actor/reason cho mutation.

## 13. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
| --- | --- |
| In-memory behavior lọt vào production | restart tests, repository contract tests |
| Event và state commit không atomic | Unit of Work/outbox-equivalent boundary |
| Snapshot sequence race | snapshot + sequence consistency test |
| Idempotency key collision/misuse | scoped key + request hash |
| Blind client retry | typed retry policy |
| Projection lag bị coi là fresh | checkpoint/lag field |
| Cross-project event leak | authorization + filter tests |
| Schema drift | generated contracts + CI diff |

## 14. Stage exit checklist

- [ ] Project/revision/idempotency/read-model persistence durable.
- [ ] Workspace snapshot endpoint hoạt động.
- [ ] Canonical command endpoint hoạt động.
- [ ] Stale và locked mutation bị từ chối.
- [ ] Idempotency pass restart/concurrency tests.
- [ ] Event envelope versioned và project-aware.
- [ ] Snapshot + replay convergence pass.
- [ ] Desktop/Web dùng shared client/projection.
- [ ] OpenAPI và TS contracts đồng bộ.
- [ ] `VP3D_UI_P7_REALTIME_STATE_VERIFIED` pass.

## 15. Bàn giao

Stage C/D nhận:

- workspace query và generated types;
- command dispatcher/client;
- revision/lock/idempotency semantics;
- event stream và projection infrastructure;
- project/revision fixture factories;
- error/conflict contracts.

Stage G nhận base sequence, reconnect state và stale response để xây recovery/merge.
