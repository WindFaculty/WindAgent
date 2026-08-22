# Kế hoạch P1 — WindAgent Production Readiness & Visual Pre-Production

**Điều kiện bắt đầu:** `WINDAGENT_P0_FEATURE_COMPLETE`
**Baseline dự kiến:** commit kết thúc P0, không cố định tiếp tục trực tiếp trên `cfa7ffb...`.

Gate cuối P1:

```text
WINDAGENT_P1_PRODUCTION_PACKAGE_READY
```

Mục tiêu P1 không phải render video. P1 phải biến:

```text
LOCKED SCREENPLAY
```

thành:

```text
LOCKED SCREENPLAY
      ↓
CHARACTER CANON
      ↓
WORLD CANON
      ↓
ASSET REQUIREMENTS
      ↓
APPROVED / PINNED ASSETS
      ↓
STORYBOARD
      ↓
SHOT PLAN
      ↓
PRODUCTION PACKAGE
      ↓
PRODUCTION_PACKAGE_READY
```

Sau P1, Blender/Unreal/TTS/Animation/Render mới có đầu vào đủ chặt để triển khai ở P2.

---

# 1. Phạm vi P1

| Workstream | Mục tiêu                             |
| ---------- | ------------------------------------ |
| **P1.0**   | Truth repair + authority convergence |
| **P1.1**   | Character Canon                      |
| **P1.2**   | World Canon                          |
| **P1.3**   | Asset Requirement & Asset Registry   |
| **P1.4**   | Storyboard Authority                 |
| **P1.5**   | Shot Planning                        |
| **P1.6**   | Production Package & Readiness       |
| **P1.7**   | Frontend Pre-Production Workflow     |
| **P1.8**   | Functional E2E Acceptance            |

Không thuộc P1:

```text
TTS production
voice synthesis pipeline
lip sync
rig generation
animation execution
Blender scene generation
Unreal scene generation
rendering
video compositing
final MP4
YouTube publishing
```

Các API AUDIO / ANIMATION / RENDER / VIDEO hiện có không được tính là hoàn thành P1 nếu chúng chưa có executor thực.

---

# 2. Tình trạng hiện tại cần tận dụng

Repo đã có khá nhiều nền cho P1.

Characters đã có durable CRUD, psychology, visual profile, voice profile, relationship graph và optimistic concurrency.

World đã có World Bible, Locations, Factions và Lore trên durable V3 resource authority.

Assets đã có revision, provenance, approval/rejection và dependency chain.

Storyboard đã có storyboard, scenes và generation-job resources.

Production đã có plan, shots và stage-job contract.

Frontend cũng đã có riêng feature packages cho Characters, World, Assets, Storyboard và Production thay vì phải dựng lại từ đầu.

Nhưng có một số phần phải sửa trước khi dùng làm production authority.

---

# PHASE P1.0 — PRE-PRODUCTION TRUTH REPAIR

## Mục tiêu

Đưa toàn bộ Characters / World / Assets / Storyboard / Production về nguyên tắc:

```text
NO SYNTHETIC AUTHORITY
NO FAKE REVISION
NO GET-SIDE EFFECT
NO FAKE QUEUED JOB
NO UNVERIFIED ASSET CLAIM
```

Đây là phase bắt buộc.

---

## P1.0.1 Sửa Storyboard sync

Hiện `sync_storyboard_from_screenplay()` đang tự tạo:

```python
source_screenplay_revision_id = f"rev-{episode_id}-lock"
```

thay vì đọc actual locked screenplay.

Phải đổi thành:

```text
Episode
   ↓
Studio Lock Authority
   ↓
LockedScreenplayReceipt
   ↓
actual revision_id
actual content_hash
actual artifact_id
   ↓
Storyboard
```

Nếu Episode chưa có locked screenplay:

```text
409 SCREENPLAY_NOT_LOCKED
```

Không tạo storyboard.

---

## P1.0.2 Sửa Scene ownership

Hiện create scene có thể tạo:

```text
storyboard_id = ""
episode_id = ""
```

và đánh `scene_number` dựa trên tổng scene toàn hệ thống.

Phải bắt buộc:

```text
scene
 ├─ episode_id
 ├─ storyboard_id
 ├─ source_screenplay_revision_id
 └─ scene_number local to storyboard
```

Không tồn tại orphan scene.

---

## P1.0.3 Sửa Production GET side effect

Hiện GET production plan có thể tự tạo:

```text
screenplay_revision_id = rev-{episode_id}-lock
storyboard_revision_id = sb-{episode_id}
```

GET phải chỉ GET.

Nếu chưa có plan:

```http
404 PRODUCTION_PLAN_NOT_CREATED
```

hoặc:

```json
{
  "status": "NOT_INITIALIZED"
}
```

nhưng không được tạo database state.

---

## P1.0.4 Sửa World GET side effect

World API hiện GET một World Bible chưa tồn tại thì tự tạo `Untitled World`.

Phải tách:

```text
GET world
POST/initialize world
```

hoặc world được tạo explicit trong quá trình Canon Sync.

Read request không được mutate domain.

---

## P1.0.5 Production stage jobs phải truthful

Hiện:

```text
POST AUDIO
POST ANIMATION
POST RENDER
POST VIDEO
```

chỉ tạo record:

```text
state = QUEUED
```

chứ chưa chứng minh có worker executor thực.

Trong P1:

```text
executor unavailable
      ↓
CAPABILITY_UNAVAILABLE
```

Không được trả:

```text
QUEUED
```

nếu không có consumer.

P2 mới enable các endpoint này.

---

## Gate

```text
P1_0_PREPRODUCTION_TRUTH_REPAIRED
```

---

# PHASE P1.1 — CHARACTER CANON

## Mục tiêu

Character không chỉ là CRUD resource.

P1 phải tạo **canonical production character** có thể tái sử dụng xuyên các Episode.

Current Character resource đã có identity, psychology, visual profile, voice profile và relationships.

P1 mở rộng semantics thay vì tạo duplicate Character model khác.

---

## P1.1.1 Character source

Ưu tiên lấy từ structured artifacts P0:

```text
Selected Idea
    ↓
Story Bible
    ↓
Locked Screenplay
    ↓
Character Canon Sync
```

Không gọi LLM lại nếu dữ liệu structured hiện tại đã đủ.

LLM chỉ dùng để:

```text
extract missing structured fields
normalize
resolve incomplete description
```

---

## P1.1.2 Canonical Character Profile

Tối thiểu:

```text
identity
 ├─ name
 ├─ aliases
 ├─ story_role
 └─ biography

personality
 ├─ traits
 ├─ flaw
 ├─ motivation
 ├─ goal
 └─ fears

visual
 ├─ physical_description
 ├─ body_type
 ├─ age_appearance
 ├─ hair
 ├─ clothing
 ├─ colors
 ├─ distinguishing_features
 └─ style_notes

voice
 ├─ voice_style
 ├─ age_range
 ├─ speaking_style
 ├─ sample_lines
 └─ optional voice_model_id

continuity
 ├─ immutable_features
 ├─ wardrobe_rules
 ├─ allowed_variations
 └─ forbidden_variations

relationships[]
```

---

## P1.1.3 Source lineage

Mỗi character version cần:

```text
source_series_id
source_story_bible_artifact_id
source_screenplay_revision_id
source_hash
```

Không để một Character thay đổi mà không biết nó xuất phát từ đâu.

---

## P1.1.4 Canon Sync

Không overwrite manual edit.

Flow:

```text
New Locked Screenplay
       ↓
Extract proposed character changes
       ↓
Compare against Canon
       ↓
NO CHANGE
ADD CHARACTER
UPDATE PROPOSED
CONFLICT
       ↓
Human/Policy decision
       ↓
Character Revision
```

---

## P1.1.5 Version pinning

Episode không tham chiếu:

```text
character_id only
```

mà production package phải pin:

```text
character_id
character_version
content_hash
```

Ví dụ:

```text
Khoa
Character v4
sha256:...
```

Episode đang production sẽ không bị thay đổi khi Character v5 được tạo cho Episode sau.

---

## P1.1.6 Character readiness

Tối thiểu production-ready cần:

```text
name
story role
visual identity
continuity constraints
```

Voice chưa bắt buộc cho P1.

Status:

```text
DRAFT
REVIEW_REQUIRED
APPROVED
PRODUCTION_READY
```

### Gate

```text
P1_1_CHARACTER_CANON_LIVE
```

---

# PHASE P1.2 — WORLD CANON

Current World domain đã có:

```text
World Bible
Locations
Factions
Lore
```

P1 phải biến nó thành production canon.

---

## P1.2.1 World Bible

Canonical:

```text
world_name
setting_summary
core_theme
timeline_era

physical_rules
technology_rules
magic_rules
social_rules

visual_style
environment_style

continuity_constraints
```

---

## P1.2.2 Location

Location production profile:

```text
location_id
name
type

description
atmosphere

interior / exterior
day / night compatibility

architecture
lighting_character
color_palette

important_props[]
reusable_set
continuity_notes
```

Không nhất thiết generate 3D asset ở P1.

---

## P1.2.3 Faction / Lore

Giữ lại nhưng production pipeline chỉ consume khi relevant.

Không bắt tất cả Episode phải có:

```text
faction
lore
history
```

nếu screenplay không sử dụng.

---

## P1.2.4 World sync

Tương tự Character:

```text
P0 Story Bible
+
Locked Screenplay
       ↓
Canon diff
       ↓
new location?
world rule conflict?
lore update?
       ↓
revision
```

---

## P1.2.5 Continuity checker

Trước storyboard:

```text
Screenplay scene
      ↓
Location references
      ↓
World Canon
```

Phát hiện:

```text
UNKNOWN_LOCATION
WORLD_RULE_CONFLICT
TIMELINE_CONFLICT
LOCATION_CONTINUITY_CONFLICT
```

Không tự sửa silently.

### Gate

```text
P1_2_WORLD_CANON_LIVE
```

---

# PHASE P1.3 — ASSET REQUIREMENTS & ASSET REGISTRY

Asset Router hiện có provenance và revision architecture khá phù hợp.

P1 phải tách hai khái niệm:

```text
Asset Requirement
```

và:

```text
Asset
```

---

## P1.3.1 Asset Requirements extraction

Từ locked screenplay + canon:

```text
Character
Location
Prop
Environment
Reference image
Music requirement
SFX requirement
```

Ví dụ:

```text
Requirement:
PROP_SWORD_001

type: PROP
scene usage: [3, 7, 8]
description: ...
mandatory: true
```

---

## P1.3.2 Asset lifecycle

```text
REQUIRED
   ↓
SOURCING / GENERATING / UPLOADING
   ↓
DRAFT
   ↓
REVIEW
   ↓
APPROVED
   ↓
PINNED
```

Failure path:

```text
REJECTED
SUPERSEDED
UNAVAILABLE
```

---

## P1.3.3 Asset source

P1 hỗ trợ:

```text
UPLOAD
IMPORT
REFERENCE
GENERATED
```

Không bắt buộc asset generation model.

Có thể upload reference image thủ công và P1 vẫn PASS.

---

## P1.3.4 Provenance

Giữ các trường hiện có:

```text
source
generator
model
prompt
reference_ids
job_id
parent_revision
```

nhưng sửa `content_hash`.

Hiện content hash được tạo từ:

```text
asset_id + prompt + timestamp
```

chứ không phải content thực.

P1 yêu cầu:

```text
SHA-256(actual asset bytes)
```

hoặc checksum immutable do storage provider xác nhận.

Format:

```text
64-char SHA-256
```

Nếu không xác minh được content:

```text
HASH_UNVERIFIED
```

và không được `PINNED`.

---

## P1.3.5 Asset dependency

Ví dụ:

```text
Character Reference v3
        ↓
3D Character Model
        ↓
Rig
        ↓
Animation
```

P1 chỉ cần dependency graph đúng.

Các node 3D chưa cần tồn tại.

---

## P1.3.6 Approval

Approval pin:

```text
asset_id
revision_id
content_hash
approved_by
approved_at
```

Không approve “latest”.

Approve một revision cụ thể.

### Gate

```text
P1_3_ASSET_AUTHORITY_LIVE
```

---

# PHASE P1.4 — STORYBOARD AUTHORITY

Đây là trọng tâm lớn nhất của P1.

## Canonical flow

```text
Locked Screenplay
      ↓
Scene Parser
      ↓
Storyboard Revision
      ↓
Scene Records
      ↓
Character / World resolution
      ↓
Asset requirements
      ↓
Storyboard Review
```

---

## P1.4.1 Screenplay parsing

Ưu tiên deterministic parser từ structured screenplay.

Không gọi LLM chỉ để tìm scene nếu screenplay đã là structured artifact.

Mỗi scene phải pin:

```text
screenplay_revision_id
screenplay_scene_id
screenplay_scene_hash
```

---

## P1.4.2 Scene schema

Target:

```text
scene_id
storyboard_id
episode_id

scene_number
title

source_screenplay_revision_id
source_screenplay_scene_id

location_id
character_refs[]
required_asset_refs[]

script_text
visual_summary
action_summary

dialogue_refs[]
estimated_duration

time_of_day
mood

status
version
```

---

## P1.4.3 Storyboard revision

Không chỉ:

```text
Storyboard
```

mà:

```text
StoryboardRevision
```

để support:

```text
v1
 ↓
manual changes
 ↓
v2
```

Production Package pin một revision cụ thể.

---

## P1.4.4 Sync semantics

First sync:

```text
Locked screenplay
     ↓
Storyboard v1
```

Screenplay unchanged + sync:

```text
IDEMPOTENT
```

Screenplay revision changed:

```text
old storyboard remains immutable
          ↓
new storyboard revision/branch
```

Không overwrite storyboard đang được production package sử dụng.

---

## P1.4.5 Concept image generation

Không bắt buộc để P1 PASS.

Nếu image generation provider có thật:

```text
Scene
 ↓
Durable task
 ↓
Provider
 ↓
Asset
 ↓
Asset revision
 ↓
Scene concept_asset_ref
```

Nếu không có:

```text
IMAGE_GENERATION_UNAVAILABLE
```

UI disable button.

Không tạo job `QUEUED` vĩnh viễn.

---

## P1.4.6 Manual storyboard operation

Cho phép:

```text
edit visual summary
change location
change character assignment
adjust estimated duration
split scene
```

Nhưng:

```text
original screenplay lineage
```

phải còn nguyên.

### Gate

```text
P1_4_STORYBOARD_AUTHORITY_LIVE
```

---

# PHASE P1.5 — SHOT PLANNING

Storyboard Scene chưa đủ để Blender/Unreal chạy.

P1 cần:

```text
Scene
   ↓
Shots
```

---

## P1.5.1 Shot generation

Có thể sử dụng rule mới từ P0:

```text
studio.preproduction.shotplan.generate
```

Nhưng output bắt buộc structured.

---

## P1.5.2 Shot model

Target:

```text
shot_id
scene_id
episode_id

shot_number
duration

shot_size
framing
camera_angle

lens
camera_movement

subject_character_refs[]
location_ref
asset_refs[]

action
dialogue_ref
audio_cue

lighting_intent
composition_notes

continuity_from
continuity_to

status
version
```

Current production resource đã có:

```text
camera_movement
focal_length
duration_seconds
scene_id
```

nên mở rộng nó thay vì tạo một Shot aggregate trùng lặp.

---

## P1.5.3 Duration validation

Phải kiểm tra:

```text
Σ shot.duration
≈
scene.duration
```

và:

```text
Σ scene.duration
≈
target episode duration
```

Có tolerance nhưng không bỏ qua mismatch lớn.

---

## P1.5.4 Continuity

Check liên tiếp:

```text
character
wardrobe
location
prop
screen direction
time of day
```

P1 chỉ cần structural continuity validation.

Computer vision review để P2/P3.

---

## P1.5.5 Manual editing

UI hỗ trợ:

```text
Add shot
Delete draft shot
Reorder
Split
Merge
Change lens
Change camera
Change duration
```

Pinned shot plan không được mutate.

Muốn sửa:

```text
derive ShotPlan revision
```

### Gate

```text
P1_5_SHOT_PLAN_LIVE
```

---

# PHASE P1.6 — PRODUCTION PACKAGE

Đây là output chính của P1.

Không lấy current `ProductionPlan` và gọi nó “ready” chỉ vì record tồn tại.

---

## P1.6.1 ProductionPackage

Canonical package:

```text
ProductionPackage
│
├── episode
│
├── locked_screenplay
│   ├── revision_id
│   ├── artifact_id
│   └── content_hash
│
├── character_canon[]
│   ├── character_id
│   ├── version
│   └── hash
│
├── world_canon
│   └── version/hash
│
├── locations[]
│
├── assets[]
│   ├── asset_id
│   ├── revision_id
│   └── content_hash
│
├── storyboard
│   ├── revision_id
│   └── hash
│
├── scenes[]
│
├── shot_plan
│   ├── revision_id
│   └── hash
│
├── constraints
│
└── production_target
```

---

## P1.6.2 Production target

P1 có thể lưu:

```text
BLENDER
UNREAL
GENERIC_3D
```

nhưng **không execute engine**.

Ví dụ:

```text
production_target = BLENDER
```

chỉ có nghĩa:

> package sẽ được P2 Blender adapter consume.

---

## P1.6.3 Preflight validator

Trước package ready:

```text
screenplay locked?
characters resolved?
world references valid?
locations resolved?
storyboard complete?
shots cover scenes?
required assets resolved?
all mandatory assets approved?
all pinned hashes valid?
duration valid?
orphan resource?
```

Output:

```text
READY
BLOCKED
```

và:

```text
blocking_findings[]
warnings[]
```

---

## P1.6.4 Không overload Episode state

P0 có thể đã dùng:

```text
READY_FOR_PRODUCTION
```

cho story completion.

P1 nên có authority riêng:

```text
story_status = READY_FOR_PRODUCTION
preproduction_status = PACKAGE_READY
```

Không cố nhồi tất cả vào một Episode enum.

---

## P1.6.5 Immutable handoff

Sau:

```text
Finalize Production Package
```

manifest phải content-addressed:

```text
package_id
package_hash
created_at
```

Sau đó dependency version mới không được làm package cũ thay đổi.

Ví dụ:

```text
Character v4 → v5
```

package đang pin v4 vẫn hợp lệ.

---

## P1.6.6 Invalidation

Nếu locked screenplay bị derive thành revision mới:

```text
screenplay rev 10
      ↓
ProductionPackage A
```

vẫn immutable.

New screenplay:

```text
rev 11
```

phải tạo:

```text
ProductionPackage B
```

không sửa Package A.

### Gate

```text
P1_6_PRODUCTION_PACKAGE_READY
```

---

# PHASE P1.7 — FRONTEND PRE-PRODUCTION WORKFLOW

Không redesign frontend framework.

Reuse các feature package đã tồn tại.

---

## Navigation

Target workflow:

```text
STORY
  Studio
  Episodes

PRE-PRODUCTION
  Characters
  World
  Assets
  Storyboard
  Production
```

---

## Character UI

```text
Character Library
Character Detail
Relationships
Visual Profile
Continuity
Version History
Approval
```

---

## World UI

```text
World Bible
Locations
Factions
Lore
Continuity warnings
```

---

## Asset UI

```text
Required
Missing
Draft
Review
Approved
Pinned
```

Asset detail:

```text
Preview
Provenance
Revision history
Dependencies
Approval
```

---

## Storyboard UI

Main composition:

```text
Scene list
      |
      | selected
      ↓
Scene Detail
├── script
├── visual summary
├── characters
├── location
├── required assets
└── concept reference
```

---

## Shot Planner

```text
Scene 01

Shot 01
Wide / 24mm / Static / 4s

Shot 02
Medium / 50mm / Dolly / 3s

Shot 03
Close Up / 85mm / Static / 2s
```

Drag/drop chỉ thay order qua server command; không frontend-only persistence.

---

## Production page

Trong P1 không nên có các nút giả:

```text
Render
Animate
Generate Video
```

Nếu executor chưa có.

Target:

```text
Production Readiness

Screenplay       ✓
Characters       ✓
World            ✓
Storyboard       ✓
Shot Plan        ✓
Assets           14/16
Mandatory Assets 12/12

[Finalize Production Package]
```

Sau finalize:

```text
PRODUCTION PACKAGE READY

Package:
pkg_xxx

Target:
Blender

[View Manifest]
```

### Gate

```text
P1_7_PREPRODUCTION_UI_LIVE
```

---

# PHASE P1.8 — FUNCTIONAL E2E ACCEPTANCE

P1 test từ **P0 locked screenplay**, không tạo fake fixture ở giữa pipeline.

---

## Scenario A — Happy path

```text
Locked Screenplay
      ↓
Character Sync
      ↓
World Sync
      ↓
Asset Requirements
      ↓
Upload/Approve required references
      ↓
Storyboard
      ↓
Shot Plan
      ↓
Preflight
      ↓
Finalize
      ↓
PRODUCTION_PACKAGE_READY
```

---

## Scenario B — Missing mandatory asset

```text
Required sword asset missing
      ↓
Preflight
      ↓
BLOCKED
```

Không được finalize.

---

## Scenario C — Character version changes

```text
Character v2
      ↓
Package A pins v2
      ↓
Character edited → v3
```

Expected:

```text
Package A still pins v2
new package may select v3
```

---

## Scenario D — New screenplay revision

```text
Screenplay v5
      ↓
Storyboard A
      ↓
Production Package A

derive screenplay v6
```

Expected:

```text
A unchanged
new storyboard required
new production package required
```

---

## Scenario E — Wrong lineage

Inject:

```text
Storyboard says screenplay rev-X
Package says screenplay rev-Y
```

Expected:

```text
PREPRODUCTION_LINEAGE_MISMATCH
```

---

## Scenario F — Restart

During preparation:

```text
restart API
restart Worker
close Desktop
reopen
```

Expected:

```text
all canonical data restored
no duplicate characters
no duplicate assets
no duplicate storyboard
```

---

## Scenario G — Unsupported renderer

Call:

```text
POST .../render/submit
```

without configured production executor.

Expected:

```text
CAPABILITY_UNAVAILABLE
```

not:

```text
QUEUED
```

Đây đặc biệt quan trọng vì implementation hiện tại chỉ tạo queued record.

---

# 3. Routing roles mới trong P1

Tận dụng P0 Model Router.

Chỉ thêm role thực sự cần LLM:

```text
studio.preproduction.character.extract

studio.preproduction.world.extract

studio.preproduction.assets.extract

studio.preproduction.storyboard.enrich

studio.preproduction.shotplan.generate

studio.preproduction.continuity.review
```

Không bắt buộc một model riêng cho mỗi role.

Có thể:

```text
storyboard.enrich
shotplan.generate
```

cùng resolve về một model.

---

# 4. Nguyên tắc: deterministic trước, LLM sau

Đây nên là quy tắc cứng của P1.

Ví dụ:

```text
Screenplay Scene List
```

đã structured:

→ deterministic projection.

Không gọi LLM.

```text
Character name
location
dialogue
scene ordering
artifact hashes
lineage
```

đều phải deterministic.

LLM chỉ làm:

```text
visual interpretation
shot suggestions
creative enrichment
continuity reasoning
missing description enrichment
```

Không cho LLM quyết định database identity hoặc hash.

---

# 5. Test matrix P1

| Layer                            | Gate |
| -------------------------------- | ---- |
| Character CRUD/versioning        | PASS |
| Character canon sync             | PASS |
| Character lineage                | PASS |
| World CRUD/versioning            | PASS |
| World canon sync                 | PASS |
| World continuity                 | PASS |
| Asset requirements               | PASS |
| Asset actual hash                | PASS |
| Asset revision                   | PASS |
| Asset approval/pinning           | PASS |
| Storyboard screenplay lineage    | PASS |
| Scene ownership                  | PASS |
| Storyboard revision              | PASS |
| Storyboard idempotent sync       | PASS |
| Shot generation schema           | PASS |
| Shot ordering                    | PASS |
| Duration validation              | PASS |
| Production preflight             | PASS |
| Immutable package                | PASS |
| Invalidation/version pinning     | PASS |
| Unsupported executor fail-closed | PASS |
| Frontend feature tests           | PASS |
| Desktop typecheck                | PASS |
| Desktop build                    | PASS |
| SQLite P1 integration            | PASS |
| PostgreSQL P1 vertical slice     | PASS |

Không cần full Phase-16 certification.

---

# 6. Thứ tự thực hiện

```text
P1.0 Truth Repair
        │
        ├──────────────┐
        ↓              ↓
P1.1 Characters    P1.2 World
        │              │
        └──────┬───────┘
               ↓
         P1.3 Assets
               ↓
       P1.4 Storyboard
               ↓
       P1.5 Shot Plan
               ↓
 P1.6 Production Package
               ↓
       P1.7 Frontend
               ↓
       P1.8 Real E2E
               ↓
WINDAGENT_P1_PRODUCTION_PACKAGE_READY
```

P1.1 và P1.2 có thể làm song song.

Frontend có thể triển khai song song sau khi contract của từng phase ổn định.

---

# 7. Commit strategy

Tách commit rõ:

```text
fix(p1-truth): remove synthetic preproduction authority

feat(p1-character): canonical character sync and pinning

feat(p1-world): canonical world and continuity

feat(p1-assets): asset requirements provenance and approval

feat(p1-storyboard): real screenplay-pinned storyboard

feat(p1-shots): production shot planning

feat(p1-package): immutable production handoff package

feat(p1-ui): preproduction desktop workflow

test(p1): end-to-end production readiness
```

Không trộn:

```text
Storyboard
+
Blender
+
audio
+
frontend redesign
+
certification evidence
```

trong cùng commit.

---

# 8. Definition of Done cuối P1

P1 chỉ PASS khi:

```text
[PASS] No synthetic screenplay revision
[PASS] No GET-side-effect creating domain records
[PASS] Character Canon derived from real Story artifacts
[PASS] Character versions pinnable
[PASS] World Canon durable and versioned
[PASS] World references validated
[PASS] Asset requirements extracted
[PASS] Mandatory asset completeness known
[PASS] Asset hash represents actual content
[PASS] Asset revisions immutable
[PASS] Approved assets pinned by revision/hash
[PASS] Storyboard reads actual locked screenplay
[PASS] Every scene has real episode/storyboard lineage
[PASS] Storyboard supports revisions
[PASS] Shot Plan covers every required scene
[PASS] Shot timing is internally valid
[PASS] Character/location/asset refs resolve
[PASS] Production preflight blocks invalid package
[PASS] Production Package is immutable
[PASS] Package pins all exact revisions/hashes
[PASS] Unsupported production executors fail closed
[PASS] Desktop can complete the whole P1 workflow
[PASS] PostgreSQL E2E passes
```

Final artifact:

```text
ProductionPackage
SHA256: ...
Status: READY
Target: Blender / Unreal / Generic
```

---

# 9. Trạng thái WindAgent sau P1

Sau P1, kiến trúc sản phẩm sẽ trở thành:

```text
IDEA
 ↓
STORY
 ↓
SCREENPLAY
 ↓
REVIEW / REVISION
 ↓
LOCK
 ─────────────── P0
 ↓
CHARACTER CANON
 ↓
WORLD CANON
 ↓
ASSET MANIFEST
 ↓
STORYBOARD
 ↓
SHOT PLAN
 ↓
PRODUCTION PACKAGE
 ─────────────── P1
 ↓
AUDIO
 ↓
BLENDER / UNREAL
 ↓
ANIMATION
 ↓
RENDER
 ↓
COMPOSITE
 ↓
FINAL VIDEO
 ─────────────── P2+
```

Tôi đánh giá đây là ranh giới tốt nhất cho P1. **Không nên đưa Blender rendering thật vào P1.** Nếu P1 kết thúc bằng một `ProductionPackage` immutable, có lineage đầy đủ và đủ dữ liệu để engine consume, thì P2 có thể tập trung hoàn toàn vào execution thay vì vừa render vừa phải sửa Story/Asset/Storyboard authority.
