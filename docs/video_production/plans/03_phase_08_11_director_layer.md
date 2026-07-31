# Kế hoạch 03 — Phase 8–11: Director Layer

## 1. Mục đích

Kế hoạch này xây dựng lớp đạo diễn độc lập với provider, chuyển `VideoProductionPackage v1` thành cinematic plan, shot dependency graph, continuity ledger và các generation request đã compile. Director quyết định cách kể và cách quay; Director không submit Flow, không tự sửa screenplay đã khóa và không nắm project/revision authority.

Tài liệu kế thừa [`road_map.md`](../../../road_map.md), [Kế hoạch 01](01_phase_00_03_protocol_governance.md) và [Kế hoạch 02](02_phase_04_07_videoclaw_preproduction_kernel.md).

## 2. Kết quả cần đạt

```text
VideoProductionPackage v1
        ↓
CinematicPlan
        ↓
ShotDependencyGraph + ContinuityLedger
        ↓
ReferenceBindingPlan
        ↓
versioned GenerationRequest
        ↓
READY_FOR_FLOW_BROWSER_PROVIDER
```

Các gate:

```text
VP8_DIRECTOR_FOUNDATION_VERIFIED
VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED
VP10_CONTINUITY_LEDGER_VERIFIED
VP11_FLOW_REQUEST_COMPILER_VERIFIED
```

## 3. Điều kiện bắt đầu

- `VP3_CANONICAL_PROTOCOL_VERIFIED`, `VP6_PREPRODUCTION_KERNEL_CANONICAL` và `VP7_ASSET_PIPELINE_VERIFIED` đã pass.
- Có package fixture đại diện cho short cartoon, two-character dialogue và multi-scene drama.
- Screenplay/entity/style/reference có stable ID, revision và content hash.
- Clean-room requirements Phase 2 đã freeze.
- Provider port tồn tại nhưng chưa cần Flow implementation.

## 4. Nguyên tắc kiến trúc

- `intelligence/windagent_intelligence/video/` chứa planner/compiler/reviewer logic.
- Domain object, ports và invariants nằm trong `core`.
- Workflow gọi Director; Director không gọi workflow ngược lại.
- Provider-specific capability được biểu diễn bằng generic generation mode/capability, không bằng selector/UI text.
- Mọi output Director là versioned, serializable, hashable và truy được về package revision.
- LLM chỉ đề xuất structured plan; deterministic validator quyết định plan có hợp lệ hay không.

## 5. Package mục tiêu

```text
intelligence/windagent_intelligence/video/
├── director/
├── shot_planner/
├── continuity/
├── reference_selector/
└── prompt_compiler/
```

Không tạo orchestration engine mới trong `intelligence`.

## 6. Branch và evidence

```text
feat/video-production-phase8-director
feat/video-production-phase9-shot-graph
feat/video-production-phase10-continuity
feat/video-production-phase11-prompt-compiler
```

Mỗi phase có phase report, contract/test receipt, architecture report và derived verdict tại `artifacts/video_production/phase_XX/`.

---

# Phase 8 — Director Layer foundation

## 7. Mục tiêu

Tạo `VideoDirectorService` biến screenplay và production constraints thành `CinematicPlan` provider-agnostic, có thể validate và review độc lập trước rendering.

## 8. Contract đầu vào/đầu ra

```python
class VideoDirectorService:
    async def create_cinematic_plan(
        self,
        package: VideoProductionPackage,
    ) -> CinematicPlan:
        ...
```

Input tối thiểu:

- package/revision ID và content hash;
- screenplay đã lock hoặc explicit unlocked state;
- entity/style bibles;
- approved reference metadata;
- target duration, aspect ratio và release constraints.

Output tối thiểu:

- scene objective và beat order;
- planned shots với stable IDs;
- shot size, camera angle/movement và duration;
- dialogue/narration binding;
- required character/location/prop references;
- generation mode intent;
- directorial issue/proposal;
- plan version/hash và source revision.

## 9. Workstream

### 9.1 Cinematic analysis

Với mỗi scene:

1. Xác định narrative goal và required story facts.
2. Tách thành beat nhưng không đổi screenplay fact.
3. Phân bổ thời lượng scene và shot.
4. Chọn coverage tối thiểu để kể đủ hành động/lời thoại.
5. Ghi style/camera constraint và required asset.
6. Phát issue nếu duration hoặc generation constraints không khả thi.

### 9.2 Duration budget

- Tổng shot duration nằm trong production constraint.
- Dialogue duration phải phù hợp shot hoặc phát issue.
- Không silently cắt dialogue.
- Transition/handle duration được tính rõ, không ẩn.
- Rounding rule và frame-rate assumption được version.

### 9.3 Script revision protocol

Director không mutate screenplay. Khi phát hiện vấn đề:

```text
DirectorialIssue
→ ScriptRevisionProposal
→ human/workflow approval
→ new screenplay revision
→ regenerate cinematic plan
```

Proposal chứa target scene/line, reason, suggested change, impact và source plan hash. Proposal bị reject không làm thay đổi package.

### 9.4 Structured planning

- Planner output qua schema, không parse text tự do nếu có thể.
- Unknown entity/reference ID làm validation fail.
- Planner không được sinh character chính hoặc location mới nếu không tạo proposal.
- Prompt/planner version được ghi trong plan.
- Model timeout/invalid output tạo typed failure, không publish partial plan.

## 10. Kiểm thử

- One-scene và multi-scene happy path.
- Dialogue vượt duration tạo issue, không bị cắt.
- Locked screenplay không mutate.
- Unknown character/reference bị reject.
- Tổng duration và thứ tự shot deterministic sau validation.
- Same fixture + deterministic model fake tạo same plan hash.
- Provider implementation không được gọi.

## 11. Deliverables và gate

```text
docs/video_production/director/
├── cinematic_plan_contract.md
├── duration_budget_policy.md
└── script_revision_protocol.md

artifacts/video_production/phase_08/
├── cinematic_plan_fixtures/
├── director_contract_receipt.json
├── screenplay_immutability_receipt.json
├── duration_validation_receipt.json
└── phase_verdict.json
```

`VP8_DIRECTOR_FOUNDATION_VERIFIED` chỉ pass khi ba package fixture tạo được plan hợp lệ, locked screenplay không thể bị đổi và mọi directorial issue đi qua proposal.

---

# Phase 9 — Shot Dependency Graph và camera planning

## 12. Mục tiêu

Biểu diễn quan hệ giữa shot thành DAG có semantics, chọn camera/generation mode có giải thích và tạo scheduling constraints độc lập với Flow.

## 13. Domain và dependency

```text
ShotDependencyGraph
├── temporal_dependency
├── visual_reference_dependency
├── continuity_dependency
├── transition_dependency
├── dialogue_dependency
└── asset_dependency
```

Mỗi edge có:

```text
dependency_id
predecessor_shot_id
successor_shot_id
dependency_type
required_artifact_type
reason
blocking
```

Graph validation:

- node/edge IDs duy nhất;
- predecessor/successor tồn tại;
- không self-edge;
- blocking subgraph không cycle;
- scene/sequence boundary hợp lệ;
- topological order tái tạo được.

## 14. Workstream

### 14.1 Shot specification

Mỗi shot ghi:

- scene/sequence/ordinal;
- narrative purpose;
- shot type;
- subjects và action;
- camera position, angle, movement và lens intent nếu cần;
- composition và screen direction;
- duration/frame rate/aspect ratio intent;
- dialogue/narration range;
- required inputs và expected outputs;
- generation mode decision;
- retry/alternative mode policy.

Shot type dùng catalog roadmap:

```text
ESTABLISHING, MASTER, MEDIUM, CLOSE_UP, EXTREME_CLOSE_UP,
OVER_SHOULDER, POV, INSERT, REACTION, TRANSITION
```

### 14.2 Camera planning rules

- Establish geography trước coverage khi scene cần spatial continuity.
- Screen direction và 180-degree rule được ghi thành constraint.
- Movement phải có mục đích và phù hợp duration.
- Reaction/insert không được làm mất story fact hoặc dialogue alignment.
- Camera decision có `reason_code`, không chỉ prose.

### 14.3 Generation mode decision

Decision matrix tối thiểu:

| Điều kiện | Mode ưu tiên |
|---|---|
| Không có reference bắt buộc, shot độc lập | `TEXT_TO_VIDEO` |
| Identity/location reference bắt buộc | `IMAGE_TO_VIDEO` hoặc `INGREDIENTS_TO_VIDEO` |
| Cần đầu/cuối xác định | `FRAMES_TO_VIDEO` |
| Tiếp nối motion/scene | `VIDEO_EXTENSION` |
| Cần biến đổi clip đã có | `VIDEO_TO_VIDEO` |

Mode phải nằm trong capability set của provider được chọn ở runtime; Director chỉ ghi preferred mode và acceptable fallback, không gọi provider.

### 14.4 Scheduling metadata

- Independent shot được đánh dấu có thể chạy song song.
- Tail-frame dependency chờ predecessor artifact đã approve.
- Transition chờ hai endpoint.
- Sequence retry boundary rõ ràng.
- Concurrency hint không vượt production constraint nhưng orchestration có quyền quyết định cuối.

## 15. Kiểm thử

- Cycle, missing node, duplicate ID và invalid cross-scene dependency.
- Topological order ổn định.
- Tail-frame/transition dependency tạo đúng required artifact.
- Shot độc lập được nhận diện.
- Generation mode decision table.
- Camera side và screen direction constraints.
- Serialize/round-trip graph.

## 16. Deliverables và gate

```text
docs/video_production/director/
├── shot_specification.md
├── shot_dependency_graph.md
├── camera_planning_rules.md
└── generation_mode_decision.md

artifacts/video_production/phase_09/
├── graph_fixture_matrix.json
├── dag_validation_receipt.json
├── camera_rule_receipt.json
├── generation_mode_receipt.json
└── phase_verdict.json
```

`VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED` chỉ pass khi graph luôn validate trước publish, cycle fail closed và mọi shot có generation mode cùng dependency cần thiết.

---

# Phase 10 — Continuity Ledger

## 17. Mục tiêu

Theo dõi trạng thái hình ảnh/điện ảnh xuyên shot và biến continuity thành constraint có thể compile, review và invalidate.

## 18. Mô hình ledger

Ledger không chỉ lưu snapshot cuối. Mỗi shot có:

```text
incoming_state
required_state
allowed_changes
planned_changes
outgoing_state
continuity_assertions
```

State tối thiểu:

- character identity, age appearance, hair, clothing, injury, emotion;
- frame position, eyeline và screen direction;
- prop possession/location/state;
- location, lighting, weather, time và scene geography;
- door/vehicle/room state;
- camera side và 180-degree rule.

Mỗi field quan trọng có source:

```text
SCREENPLAY_FACT
BIBLE_FACT
APPROVED_REFERENCE
DIRECTOR_DECISION
PREDECESSOR_OUTPUT
HUMAN_OVERRIDE
```

## 19. Workstream

### 19.1 Initial state

- Khởi tạo từ screenplay/entity/style bibles và approved references.
- Không tự đoán field bắt buộc còn thiếu; tạo continuity issue.
- Immutable fact và changeable state được phân biệt.

### 19.2 State transition

- Shot action có thể tạo planned change.
- Change ngoài `allowed_changes` là blocking defect.
- Outgoing state của predecessor trở thành input cho dependent shot.
- Parallel shot không được tạo conflicting canonical outgoing state mà không có merge rule.

### 19.3 Diff và review

Tạo machine-readable diff:

```text
field
before
expected
observed
source
severity
blocking
```

Human override cần actor, reason, target revision và timestamp. Override không sửa retroactive evidence.

### 19.4 Invalidation intent

Ledger ghi dependency đủ để Phase 18 xác định:

- reference identity thay đổi ảnh hưởng shot nào;
- wardrobe/prop change bắt đầu từ shot nào;
- camera side change ảnh hưởng sequence nào;
- approved override làm prompt/frame/clip nào stale.

## 20. Kiểm thử

- Prop đổi tay không có action → blocking.
- Wardrobe change được screenplay cho phép → pass.
- Identity/reference hash không khớp → blocking.
- 180-degree violation được phát hiện.
- Parallel branches tạo conflict → issue.
- Human override có audit record.
- Multi-scene state reset/continuation đúng policy.

## 21. Deliverables và gate

```text
docs/video_production/director/
├── continuity_ledger.md
├── continuity_rule_catalog.md
└── continuity_override_policy.md

artifacts/video_production/phase_10/
├── continuity_fixture_matrix.json
├── transition_test_receipt.json
├── blocking_defect_receipt.json
├── invalidation_dependency_receipt.json
└── phase_verdict.json
```

`VP10_CONTINUITY_LEDGER_VERIFIED` chỉ pass khi required continuity state được trace qua graph, invalid transition bị chặn và override được audit.

---

# Phase 11 — Reference Binding và Prompt Compiler

## 22. Mục tiêu

Biến mỗi `ShotSpecification` thành `GenerationRequest` provider-safe, có reference binding rõ ràng, prompt version/hash và không cho nội dung web/model tự do đi thẳng vào browser.

## 23. Pipeline

```text
ShotSpecification
    ↓
ReferenceBindingPlanner
    ↓
FlowGenerationSpecification
    ↓
PromptCompiler
    ↓
GenerationRequest
```

`FlowGenerationSpecification` là request semantics cho Flow capability, không chứa selector hoặc DOM state.

## 24. Workstream

### 24.1 Reference binding

Mỗi binding có:

```text
binding_id
shot_id
asset_id
asset_hash
role
required/optional
source_revision
crop/usage intent
approval_state
```

Chỉ asset `APPROVED` và đúng revision được bind. Candidate/reference bị reject hoặc stale không được compile.

### 24.2 Prompt blocks

Compiler nhận structured fields:

```text
PROJECT STYLE
IDENTITY
LOCATION
PROPS
SHOT COMPOSITION
ACTION
CAMERA
LIGHTING
CONTINUITY
DIALOGUE/AUDIO INTENT
DURATION
NEGATIVE CONSTRAINTS
```

Thứ tự block và format được version. Empty optional block có rule rõ ràng; required block thiếu thì fail.

### 24.3 Mode-specific compiler

Có compiler/strategy riêng cho:

- text-to-video;
- image-to-video;
- frames-to-video;
- ingredients-to-video;
- video extension;
- video-to-video;
- image/reference generation dùng ở Phase 14.

Mode-specific validation bảo đảm đủ first/last frame, ingredient/reference hoặc predecessor clip.

### 24.4 Sanitization và trust boundary

- Loại path local/profile và secret.
- Không đọc instruction từ EXIF, web page, alt text hoặc asset metadata vào prompt.
- Escape/control Unicode và giới hạn length/token.
- Chỉ allow block/field đã định nghĩa.
- Log redacted prompt hoặc encrypted artifact theo policy; không log cookie/session.
- LLM không điều khiển selector, click hoặc submit.

### 24.5 Hash và reproducibility

Request hash từ:

```text
canonical shot specification
+ compiler version
+ prompt template version
+ reference hashes
+ generation mode
+ model capability constraints
+ generation parameters
```

Cùng input tạo cùng request hash. Thay reference, prompt version hoặc parameter tạo hash mới.

## 25. Kiểm thử

- Stable hash với input giống nhau.
- Hash thay khi reference/prompt version/parameter thay.
- Missing/stale/unapproved reference fail.
- Mode-specific required inputs.
- Oversized prompt và malicious metadata.
- Không rò local path/secret marker.
- Golden compiled request cho ba fixture.
- Browser/tool module không được import.

## 26. Deliverables và gate

```text
docs/video_production/director/
├── reference_binding_contract.md
├── prompt_block_contract.md
├── compiler_versioning.md
└── prompt_security_policy.md

artifacts/video_production/phase_11/
├── compiled_request_fixtures/
├── reference_binding_receipt.json
├── prompt_hash_receipt.json
├── prompt_security_receipt.json
├── mode_contract_receipt.json
└── phase_verdict.json
```

`VP11_FLOW_REQUEST_COMPILER_VERIFIED` chỉ pass khi request deterministic, references approved/hash-bound, prompt security tests pass và không có browser dependency.

## 27. Cross-phase integration test

Chạy một pipeline không dùng Flow:

```text
VideoProductionPackage fixture
→ CinematicPlan
→ ShotDependencyGraph
→ ContinuityLedger
→ ReferenceBindingPlan
→ GenerationRequest set
```

Kiểm tra:

- mọi scene/shot/entity ID truy được về source revision;
- tổng duration hợp lệ;
- graph acyclic;
- continuity constraints có trong compiled request;
- mọi reference hash hợp lệ;
- request hash duy nhất theo shot/mode;
- không có network/browser call.

## 28. Handoff sang Phase 12–16

Handoff gồm:

- provider port và capability vocabulary;
- valid/invalid `GenerationRequest` fixtures;
- request hash algorithm/version;
- reference upload order và media constraints;
- preferred/fallback generation mode;
- expected candidate count và quality intent;
- human approval requirements;
- typed failure catalog;
- không kèm selector hoặc Flow UI assumption.

## 29. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Director sửa story để vừa model | Bắt buộc `ScriptRevisionProposal` |
| LLM tạo graph cycle/ID giả | Deterministic schema và DAG validator |
| Continuity chỉ là prose | Structured state, diff và blocking rules |
| Prompt gắn chặt Flow UI | Generation semantics trong core/intelligence, selector ở tools |
| Web metadata prompt injection | Không đưa metadata không tin cậy vào compiler |
| Hash không ổn định | Canonical serialization và versioned algorithm |
| Prompt quá dài | Block priority, bounded length và explicit compile failure |

## 30. Checklist đóng kế hoạch

- [ ] Cinematic plan không mutate screenplay.
- [ ] Shot graph acyclic và có scheduling semantics.
- [ ] Continuity ledger trace được state xuyên shot.
- [ ] Approved reference được bind theo content hash.
- [ ] Prompt compiler mode-specific, versioned và deterministic.
- [ ] Không browser/provider implementation dependency.
- [ ] `VP8` đến `VP11` đều `PASSED`.
- [ ] Flow provider nhận được fixture contract hoàn chỉnh.
