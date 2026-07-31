# Kế hoạch 05 — Phase 17–20: Orchestration, Cost và Review

## 1. Mục đích

Kế hoạch này ghép pre-production, Director và Flow provider thành workflow durable; bổ sung content-addressed artifact/invalidation, kiểm soát cost/quota và review candidate nhiều tầng. Kết quả là một production run có thể pause, resume, recover và fail closed mà không submit trùng hoặc che giấu lỗi chất lượng.

Tài liệu kế thừa [`road_map.md`](../../../road_map.md) và [Kế hoạch 04](04_phase_12_16_flow_browser_provider.md).

## 2. Kết quả cần đạt

```text
versioned project inputs
       ↓
durable production workflow
       ↓
content-addressed artifacts + invalidation graph
       ↓
approved budget + quota ledger
       ↓
candidate review + approval
       ↓
READY_FOR_AUDIO_AND_FINAL_VIDEO
```

Các gate:

```text
VP17_DURABLE_WORKFLOW_VERIFIED
VP18_ARTIFACT_INVALIDATION_VERIFIED
VP19_COST_AND_QUOTA_CONTROL_VERIFIED
VP20_GENERATION_REVIEW_VERIFIED
```

## 3. Điều kiện bắt đầu

- `VP7`, `VP11` và `VP16` đã pass.
- Provider contract có durable job state, reconciliation và human-action events.
- `GenerationRequest` có stable request hash.
- Candidate artifacts có content hash và technical validation metadata.
- WindAgent hiện có workflow engine, scheduler, recovery và storage/outbox primitives; phase này phải mở rộng chúng, không tạo orchestration authority song song.

## 4. Vị trí kiến trúc

Các module hiện hữu cần được tái sử dụng:

```text
orchestration/windagent_orchestration/
├── workflow_engine/
├── scheduler/
├── recovery/
├── retry/
├── state_machine/
└── dispatcher/

storage/windagent_storage/
├── outbox/
├── unit_of_work/
├── repositories/
└── services/
```

Module video production mới dự kiến:

```text
workflows/windagent_workflows/video_production/
orchestration/windagent_orchestration/production/
storage/windagent_storage/video_production/
observability/windagent_observability/media_generation/
intelligence/windagent_intelligence/video/reviewers/
verification/windagent_verification/media/
```

Không tạo database/task queue riêng theo VideoClaw hoặc Flow.

## 5. Branch và evidence

```text
feat/video-production-phase17-workflow
feat/video-production-phase18-artifacts
feat/video-production-phase19-cost
feat/video-production-phase20-review
```

Mỗi phase cần migration receipt nếu schema storage đổi, replay/recovery receipt nếu event/workflow đổi và architecture report chứng minh authority vẫn thuộc WindAgent.

---

# Phase 17 — Durable production workflow

## 6. Mục tiêu

Triển khai workflow end-to-end có checkpoint, approval, lease, retry, cancellation, human pause và recovery trên primitives canonical.

## 7. Workflow definition

```text
CREATE_PROJECT
→ GENERATE_CONCEPTS
→ SELECT_CONCEPT
→ GENERATE_SCREENPLAY
→ LOCK_SCREENPLAY
→ BUILD_CHARACTER_AND_LOCATION_BIBLES
→ APPROVE_REFERENCES
→ CREATE_CINEMATIC_PLAN
→ LOCK_SHOT_PLAN
→ ESTIMATE_COST
→ RENDER_ASSETS
→ RENDER_SHOTS
→ REVIEW_CANDIDATES
→ POST_PRODUCTION
→ FINAL_VERIFICATION
→ PUBLISH
```

Mỗi step định nghĩa:

```text
step_id/version
input revision/hash
preconditions
operation
expected events
checkpoint
retry class/budget
compensation or recovery
approval requirement
output artifact types
```

## 8. Workstream

### 8.1 State machine

Workflow/run state tối thiểu:

```text
CREATED
RUNNING
WAITING_APPROVAL
WAITING_HUMAN_ACTION
WAITING_PROVIDER
PAUSED
RECOVERING
COMPLETED
FAILED
CANCELLED
ARCHIVED
```

- Transition dùng command/event canonical.
- Duplicate event idempotent.
- Terminal state không nhận write mới ngoài audit/archival.
- Stale worker write bị lease/version check từ chối.

### 8.2 Approval gates

```text
CONCEPT_APPROVAL
SCREENPLAY_APPROVAL
CHARACTER_APPROVAL
LOCATION_APPROVAL
SHOT_PLAN_APPROVAL
COST_APPROVAL
FINAL_CUT_APPROVAL
```

Approval trỏ đúng revision/hash. Khi target đổi, approval cũ trở thành stale và không được tái sử dụng.

### 8.3 Checkpoint và outbox

- Domain state, checkpoint và outgoing event được commit atomically qua unit-of-work/outbox.
- Checkpoint ghi current step, attempt, input/output hashes, lease và pending external operation.
- External provider result ingestion idempotent theo generation/event ID.
- Không publish event thành công trước khi state/artifact commit.

### 8.4 Scheduler

- Tôn trọng shot DAG, approval, candidate/retry limit và provider concurrency.
- Release 0.1 giới hạn Flow concurrency bằng 1.
- Independent work không có external-credit cost có thể song song nếu safe.
- Scheduler không chọn candidate hoặc tự approve.

### 8.5 Recovery

Thiết kế recovery cho:

- worker chết trước/sau checkpoint;
- browser đóng sau submit;
- download fail;
- Flow project mapping mất context;
- một shot/sequence fail;
- prompt/reference revision;
- human action;
- user cancel/archive.

Recovery luôn inspect durable state/provider trước khi retry. Không dùng “file exists” làm quyết định duy nhất.

### 8.6 Cancellation

- Cancel dừng schedule mới.
- Active provider operation chuyển sang cancel/reconcile theo capability thật.
- Không khẳng định external job đã dừng nếu không có evidence.
- Artifact đã hoàn tất vẫn giữ provenance nhưng không tự publish.
- Cancel reason/actor/timestamp được audit.

## 9. Kiểm thử

- Happy path bằng fake providers.
- Pause/resume ở mọi approval gate.
- Worker crash ở trước/sau external submit.
- Duplicate event/result.
- Lease expiry và stale write.
- Human-action pause/resume.
- Cancel/archive.
- Single-shot failure không làm mất successful siblings.
- Database restart và outbox replay.

## 10. Gate

`VP17_DURABLE_WORKFLOW_VERIFIED` chỉ pass khi workflow khôi phục được từ durable state, approvals đúng revision, duplicate/stale write không gây side effect và failure matrix không tạo duplicate submit.

---

# Phase 18 — Content-addressed artifact storage và invalidation

## 11. Mục tiêu

Thay quyết định cache kiểu `file exists` bằng content identity, dependency graph và atomic artifact lifecycle.

## 12. Artifact model

Artifact record tối thiểu:

```text
artifact_id
artifact_type
content_sha256
byte_size
media_type
storage_locator
producer
project_id / revision_id
input_hashes
request_hash
prompt/compiler/model versions
generation parameters
created_at
validation_status
approval_status
superseded_by
```

Storage locator không được là public authority; content hash + metadata record mới là identity.

## 13. Artifact key

```text
SHA256(
    canonical_input
    + prompt_version
    + reference_hashes
    + model
    + generation_mode
    + generation_parameters
)
```

Canonicalization/version phải được pin. Thay algorithm tạo key version mới, không reinterpret key cũ.

## 14. Workstream

### 14.1 Atomic publish

```text
write temporary
→ hash/size/decode validation
→ metadata transaction
→ atomic promote
→ publish ArtifactAvailable event
```

Crash ở bất kỳ điểm nào không để artifact record `VALID` trỏ file thiếu hoặc file published thiếu record.

### 14.2 Dependency graph

Edge biểu diễn artifact A được tạo từ input B:

```text
artifact_id
depends_on_artifact_id or domain_revision_hash
dependency_type
reason
```

Hỗ trợ truy vấn inbound/outbound để invalidation có phạm vi tối thiểu.

### 14.3 Invalidation rules

Tối thiểu:

```text
screenplay revision
→ cinematic plan
→ shot plan
→ prompt/request
→ frames/references generated for shot
→ clips
→ final cut

character reference
→ only bound/dependent shots and downstream cuts

BGM
→ audio mix and final cut, not visual clips
```

Invalidation không xóa artifact; chuyển trạng thái `STALE`/`SUPERSEDED`, giữ audit và cho garbage collection theo retention policy sau.

### 14.4 Reuse

Reuse chỉ khi:

- artifact key/version khớp;
- file hash/validation còn hợp lệ;
- approval phù hợp project/revision;
- không bị stale/revoked;
- policy cho phép cross-run/cross-project reuse.

## 15. Kiểm thử

- Same canonical input reuse.
- Reference/prompt/model/parameter change tạo key khác.
- Character change chỉ invalid dependent shots.
- BGM change giữ video clip.
- Crash trong atomic publish.
- File tamper/hash mismatch.
- Concurrent publish cùng key.
- Invalidation graph cycle/unknown node.

## 16. Gate

`VP18_ARTIFACT_INVALIDATION_VERIFIED` chỉ pass khi reuse dựa trên full key, invalidation đúng phạm vi, artifact publish atomic và history không bị xóa/sửa.

---

# Phase 19 — Cost, credits và quota management

## 17. Mục tiêu

Ngăn submit/retry/candidate explosion vượt ngân sách; mọi production run phải có estimate, approval và ledger đủ để reconcile.

## 18. Thành phần

```text
CreditEstimator
GenerationBudgetPolicy
QuotaLedger
RetryBudget
DailyLimit
MonthlyLimit
ProviderCircuitBreaker
```

Giá/credit cụ thể là provider configuration có thời điểm hiệu lực và provenance; không hard-code số liệu dễ thay đổi vào domain invariant.

## 19. Workstream

### 19.1 Cost catalog

Mỗi entry:

```text
provider
model
operation/mode
duration/resolution tier
candidate semantics
estimated credit rule
effective_at
source/observed
confidence
```

Unknown/missing rule tạo estimate `UNKNOWN` và chặn submit.

### 19.2 Estimate

Estimate theo:

- shot/mode/model/duration;
- number of candidates;
- image/reference generations;
- expected retry reserve;
- post-production nếu có external cost;
- contingency.

Output:

```json
{
  "estimated_credits": 280,
  "maximum_credits": 400,
  "candidate_count": 2,
  "retry_reserve": 80,
  "requires_approval": true
}
```

Estimate gắn plan/request hashes. Khi shot plan hoặc cost catalog thay, approval cũ stale.

### 19.3 Quota ledger

Append-only entries:

```text
ESTIMATED
RESERVED
SUBMITTED
OBSERVED_DEBIT
RELEASED
ADJUSTED
UNKNOWN
```

Adjustment cần reason/source. Không overwrite observed debit.

### 19.4 Budget policy

- Không submit nếu credit state/estimate unknown.
- Reserve trước submit; reconcile sau observed result.
- Retry chỉ khi còn retry budget.
- Candidate count bounded.
- Quality/high-cost mode cần explicit approval.
- Daily/monthly/project/run limits áp dụng trước provider call.
- PoC không submit nhiều generation song song.

### 19.5 Circuit breaker

Mở circuit khi:

- insufficient credits;
- repeated provider/account errors;
- observed cost lệch estimate vượt policy;
- UI không cho xác định config/cost;
- account challenge lặp lại.

Circuit breaker reset bằng time/policy hoặc human review, không tự reset liên tục.

## 20. Kiểm thử

- Unknown cost/credit state.
- Exact boundary và vượt project/daily/monthly limit.
- Candidate/retry reserve.
- Estimate stale khi plan/catalog đổi.
- Duplicate result không double-debit.
- Crash sau reserve/submission và ledger reconciliation.
- Insufficient credits mở circuit.
- Human approval đúng estimate hash.

## 21. Gate

`VP19_COST_AND_QUOTA_CONTROL_VERIFIED` chỉ pass khi mọi submit path đi qua reserve/approval policy, unknown fail closed, retry bounded và ledger không double count qua replay.

---

# Phase 20 — Candidate review và quality gates

## 22. Mục tiêu

Đánh giá candidate bằng kiểm tra deterministic, VLM, cross-shot comparison và human review; chọn/reject có giải thích, không nén mọi vấn đề vào một score.

## 23. Review dimensions

```text
technical_validity
prompt_compliance
identity_consistency
location_consistency
prop_consistency
continuity
motion_quality
camera_compliance
dialogue_alignment
visual_artifacts
safety
```

Mỗi dimension có:

- metric/check version;
- score hoặc categorical result;
- confidence;
- evidence;
- threshold;
- blocking rule;
- reviewer type.

## 24. Reviewer hierarchy

```text
ffprobe / deterministic checks
        ↓
single-candidate VLM scoring
        ↓
cross-shot/reference comparison
        ↓
human review khi blocking hoặc confidence thấp
```

Không chạy VLM nếu file không decode hoặc thiếu video stream.

## 25. Workstream

### 25.1 Deterministic validation

- Hash/file/media/decoder validity.
- Duration, resolution, frame rate và stream.
- Black/truncated ending và sample-frame decode.
- Required candidate metadata/provenance.
- Safety file checks.

### 25.2 VLM review

- Prompt compliance theo structured intent.
- Identity/location/prop consistency với approved references.
- Camera/action/motion quality.
- Output schema, model/prompt version và confidence.
- Model failure/invalid JSON không được coi là pass.

### 25.3 Cross-shot continuity

- So predecessor/successor theo continuity ledger.
- Kiểm tra screen direction, wardrobe, prop, lighting và location.
- Required tail/head frame relation.
- Blocking defect có reason code.

### 25.4 Verdict policy

Ví dụ:

```json
{
  "identity": 0.91,
  "continuity": 0.74,
  "motion": 0.85,
  "technical": true,
  "blocking_defects": ["prop changes hands"],
  "verdict": "REJECT"
}
```

Verdict:

```text
APPROVE
REJECT
HUMAN_REVIEW_REQUIRED
REVIEW_ERROR
```

Blocking defect luôn thắng aggregate preference. Low confidence chuyển human review. Không auto-select candidate đầu hoặc candidate có average score cao nhưng vi phạm blocking rule.

### 25.5 Candidate selection

- Rank chỉ trong số candidate không bị block.
- Selection record có algorithm/policy version và reason.
- Human selection/override có audit.
- Rejected candidate vẫn giữ evidence theo retention policy.
- Retry proposal ghi defect nào cần sửa và request field nào thay.

## 26. Kiểm thử

- Invalid media không qua deterministic gate.
- Identity cao nhưng blocking continuity defect → reject.
- VLM timeout/invalid output → review error/human.
- Low confidence → human.
- Candidate ordering không ảnh hưởng selected result.
- Cross-shot prop/wardrobe/camera mismatch.
- Human override audit.
- Policy/threshold change làm review revision mới, không sửa result cũ.

## 27. Gate

`VP20_GENERATION_REVIEW_VERIFIED` chỉ pass khi:

1. Deterministic failures không thể bị VLM/human score che.
2. Blocking defects có automated cases.
3. Low confidence/error không tạo false PASS.
4. Selection/rejection truy được về policy, model và evidence.
5. Cross-shot review dùng continuity ledger.

## 28. Integration và recovery matrix

Chạy workflow fake E2E đến candidate approval với các case:

| Case | Expected |
|---|---|
| Worker chết sau submit | Reconcile same job, no duplicate |
| Browser đóng khi generating | Pause/reattach/inspect |
| Candidate download fail | Retry download trong budget, không resubmit |
| Reference revision đổi | Dependent request/artifact/approval stale |
| Budget hết giữa sequence | Pause `WAITING_APPROVAL`, không submit tiếp |
| Candidate có blocking defect | Reject và bounded retry proposal |
| Human review pending | Workflow durable pause |
| Duplicate provider event | Idempotent ingestion và ledger |

## 29. Evidence cuối milestone

```text
artifacts/video_production/production_orchestration/
├── workflow_definition_manifest.json
├── recovery_failure_matrix.json
├── artifact_invalidation_matrix.json
├── cost_policy_manifest.json
├── quota_ledger_reconciliation.json
├── review_policy_manifest.json
├── candidate_review_fixtures/
└── milestone_verdict.md
```

## 30. Handoff sang Phase 21–24

- Approved clip set với content hash và shot mapping.
- Dialogue/narration lines gắn shot/time intent.
- Continuity/review report và known accepted limitations.
- Cost ledger/remaining budget.
- Artifact dependency graph.
- Workflow checkpoint sẵn sàng `POST_PRODUCTION`.
- Final-cut approval chưa được cấp trước khi Phase 22/24 hoàn tất.

## 31. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Tạo orchestration stack song song | Mở rộng workflow/scheduler/recovery/storage hiện hữu |
| External side effect và DB lệch nhau | Intent/checkpoint/outbox + reconciliation |
| Cache trả artifact stale | Full content key + dependency invalidation |
| Ledger double count qua replay | Append-only idempotent entries |
| Cost catalog thay đổi | Version/effective date/provenance, unknown fail closed |
| VLM tạo false PASS | Deterministic gate + blocking dimensions + human review |
| Threshold bị hạ sau test | Freeze policy version trước verdict |

## 32. Checklist đóng kế hoạch

- [ ] Workflow pause/resume/recover qua failure matrix.
- [ ] Artifact publish atomic và invalidation đúng phạm vi.
- [ ] Mọi submit có estimate/reserve/approval.
- [ ] Retry và candidate count có budget.
- [ ] Review không dùng một aggregate score để che blocker.
- [ ] `VP17` đến `VP20` đều `PASSED`.
- [ ] Approved clip set và checkpoint đã sẵn sàng cho hậu kỳ.
