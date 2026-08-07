Đủ thông tin để khóa kiến trúc. Tôi không còn câu hỏi kỹ thuật nào bắt buộc trước khi lập roadmap.

Có một điểm cần ghi rõ ngay: mục tiêu **video 20 phút, Cycles, RTX 5060 8 GB, hoàn tất render dưới 3 giờ trên một máy** là một acceptance target khá khắt khe. 20 phút ở 24 fps tương đương 28.800 frame; ngân sách trung bình chỉ khoảng **0,375 giây/frame** nếu tính riêng render tuần tự. Vì vậy roadmap sẽ coi `≤3h` là **performance gate phải benchmark**, không mặc định tuyên bố đạt. Với Cycles, có thể cần aggressive adaptive sampling, denoise, render reuse, scene optimization, LOD và shot-level caching.

Tôi cũng đề xuất pin **Blender 4.5 LTS** làm baseline đầu tiên thay vì chạy theo phiên bản mới nhất; Blender liệt kê 4.5 là nhánh LTS và Python API có thể điều khiển animation, rendering, import/export và tự động hóa phần lớn Blender. ([Blender][1])

# Roadmap lớn: WindAgent 3D Animation Production

## Kiến trúc đích

Không xây:

```text
Director
   ↓
BlenderProvider
   ↓
Blender
```

Mà chuyển sang:

```text
                    WINDAGENT
                       │
                       ▼
              Creative / Screenplay
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
     Director Layer            Audio Pipeline
          │                   TTS / Voice / Align
          ▼                         │
    Shot / Scene Intent             │
          │                         │
          ▼                         │
  Production Intermediate           │
     Representation                 │
          │                         │
          ├──────────────┐          │
          ▼              ▼          ▼
   Asset Pipeline   Animation Pipeline
          │              │
          └──────┬───────┘
                 ▼
           Scene Compiler
                 │
                 ▼
         ProductionEnginePort
                 │
                 ▼
         BlenderEngineAdapter
                 │
                 ▼
          Blender 4.5 LTS
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
    .blend    frames     metadata
                 │
                 ▼
             Reviewer
                 │
                 ▼
          Post-production
              FFmpeg
                 │
                 ▼
             Final MP4
```

Sau này:

```text
ProductionEnginePort
        │
        ├── BlenderEngineAdapter
        │
        └── UnrealEngineAdapter
```

Và xa hơn theo lựa chọn `12C`:

```text
Blender
  └── chủ yếu Asset Authoring / Rigging / Preparation

Unreal Engine
  └── Scene / Animation / Lighting / Final Rendering
```

Điều này đặc biệt quan trọng vì domain hiện tại vẫn chứa `GenerationMode.TEXT_TO_VIDEO`, `IMAGE_TO_VIDEO`, `VIDEO_EXTENSION`... vốn được tạo ra cho generative-video pipeline.

---

# Stage A — Kiến trúc lại nền tảng

## Phase 0 — Baseline Freeze & Blender Migration Contract

Mục tiêu là đóng băng trạng thái hiện tại trước khi xóa Flow.

Thực hiện:

* ghi `baseline_sha`;
* full Python tests;
* architecture checker;
* Web/Desktop tests;
* video-production contract tests;
* snapshot schema hiện tại;
* inventory toàn bộ:

  * `tools/windagent_tools/google_flow/`;
  * `docs/video_production/flow_*`;
  * browser runtime liên quan Flow;
  * Flow-specific schemas;
  * Flow-specific tests;
  * Flow-specific evidence;
* lập dependency map xem module nào còn import Flow.

Không thay code nghiệp vụ trong phase này.

**Gate**

```text
VP3D_P0_BASELINE_FROZEN
```

PASS khi baseline sạch và toàn bộ Flow dependencies đã được inventory.

---

# Phase 1 — Canonical Production IR

Đây là phase quan trọng nhất.

Phải loại khỏi domain các khái niệm kiểu:

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
FRAMES_TO_VIDEO
VIDEO_EXTENSION
VIDEO_TO_VIDEO
```

Hiện `GenerationModeDecider` đang dựa trực tiếp vào các mode này.

Thay bằng các khái niệm mô tả **ý định điện ảnh**, không mô tả provider.

Ví dụ:

```python
ShotExecutionIntent
SceneDescription
CharacterInstance
PropInstance
EnvironmentInstance
CameraTrack
AnimationTrack
FacialTrack
DialogueTrack
LightRig
SimulationTrack
RenderProfile
```

Shot không còn nói:

```text
IMAGE_TO_VIDEO
```

mà nói:

```text
characters:
  - character_001

action:
  walk_to: desk_01

camera:
  shot_type: MEDIUM
  movement: DOLLY_IN

duration: 4.2

dialogue:
  track: dialogue_023
```

Engine tự quyết định cách thực hiện.

### Canonical formats

Theo lựa chọn của bạn:

```text
JSON/Pydantic    → metadata / production IR
glTF             → asset interchange ưu tiên
FBX              → skeletal/animation compatibility
USD              → hướng dài hạn Blender ↔ Unreal
.blend           → derived editable artifact
```

`.blend` tuyệt đối không phải source of truth.

**Gate**

```text
VP3D_P1_ENGINE_NEUTRAL_IR_VERIFIED
```

---

# Phase 2 — Hard Removal Google Flow

Bạn chọn xóa ngay nên phase này thực hiện retirement thực sự.

Xóa:

```text
tools/windagent_tools/google_flow/
```

và toàn bộ:

```text
flow_navigation
flow_video
flow_images
flow_human_control
browser runtime chỉ phục vụ Flow
Flow candidate downloader
Flow project manager
Flow submit guard
Flow UI mapping
```

Các contract có giá trị chung như:

* idempotency;
* cancellation;
* retry;
* artifact hash;
* candidate provenance;
* fail-closed validation;

không được xóa ý tưởng, mà chuyển vào engine-neutral runtime.

Flow hiện có những guarantee này nên chúng phải được bảo tồn dưới abstraction mới.

Sau phase này:

```bash
rg "google_flow"
rg "FlowVideo"
rg "FlowImage"
rg "flow_video"
```

phải không còn runtime dependency.

**Gate**

```text
VP3D_P2_GOOGLE_FLOW_REMOVED
```

---

# Stage B — Blender Runtime

## Phase 3 — Blender Runtime Foundation

Baseline:

```text
OS      Windows
GPU     NVIDIA RTX 5060 Laptop 8 GB
RAM     32 GB
CPU     Intel Core i7-14650HX
Engine  Blender 4.5 LTS
Render  Cycles
```

WindAgent không bundle Blender ở giai đoạn đầu.

Xây:

```text
BlenderInstallationDetector
BlenderVersionValidator
BlenderCapabilityProbe
BlenderGpuProbe
BlenderJobLauncher
BlenderProcessSupervisor
BlenderExecutionReceipt
```

Execution:

```text
WindAgent Worker
    ↓
blender.exe --background project.blend --python execute_job.py
```

Cần capture:

```text
PID
exit_code
stdout
stderr
Blender version
GPU backend
VRAM estimate
start/end
job hash
scene hash
output hashes
```

### Add-on security

```text
addon allowlist
      ↓
signed/version-pinned manifest
      ↓
Blender runtime
```

Agent tuyệt đối không tự cài add-on mới.

Add-on ngoài allowlist:

```text
REQUIRES_HUMAN_APPROVAL
```

**Gate**

```text
VP3D_P3_BLENDER_RUNTIME_VERIFIED
```

---

# Phase 4 — Blender Deterministic Scene Smoke Test

Chưa dùng AI.

Tạo scene bằng Python:

```text
cube
ground
camera
3 lights
simple material
animation
```

Render Cycles → image sequence → FFmpeg MP4.

Test:

```text
create scene
save .blend
reopen .blend
render
cancel
resume
retry
hash outputs
```

Blender manual cũng khuyến nghị render animation thành image sequence vì có thể resume từ frame cuối thay vì mất toàn bộ video khi job bị gián đoạn. ([Blender Documentation][2])

Không render thẳng MP4 từ Blender trong production.

Canonical path:

```text
Blender
  ↓
PNG/EXR frames
  ↓
FFmpeg
  ↓
MP4
```

**Gate**

```text
VP3D_P4_DETERMINISTIC_RENDER_PASSED
```

---

# Stage C — Asset Production

## Phase 5 — Universal Asset Gateway

Agent được phép:

1. tìm asset ngoài Internet;
2. gọi Mesh API;
3. gọi Mesh MCP;
4. gọi future 3D generation APIs;
5. dùng asset library local.

Không để Director trực tiếp làm các việc này.

Xây:

```text
AssetResolverPort
    │
    ├── LocalAssetAdapter
    ├── InternetAssetAdapter
    ├── MeshApiAdapter
    ├── MeshMcpAdapter
    └── FutureGeneratorAdapter
```

Canonical request:

```python
AssetRequirement(
    type="CHARACTER",
    description="...",
    style="3d_cartoon",
    topology_requirements=...,
    rig_required=True,
    texture_resolution=...,
)
```

---

# Phase 6 — Asset Trust & Provenance

Asset Internet bắt buộc có:

```text
source_url
provider
author
license
license_state
download timestamp
SHA256
original format
converted format
```

Asset AI:

```text
provider
model
prompt hash
seed nếu có
generation request hash
```

Asset không xác định license:

```text
QUARANTINED
```

không được dùng vào final production.

Domain hiện đã có `AssetSourceType` và `LicenseState`, nên có thể mở rộng thay vì tạo subsystem khác.

---

# Phase 7 — Asset Normalization

Mọi asset phải qua:

```text
ingest
 ↓
virus/security validation
 ↓
format validation
 ↓
unit normalization
 ↓
axis normalization
 ↓
mesh validation
 ↓
material normalization
 ↓
texture normalization
 ↓
poly budget validation
 ↓
LOD generation
 ↓
preview render
 ↓
approval/cache
```

Chuẩn nội bộ:

```text
1 unit = 1 meter
Z-up canonical metadata
PBR materials
texture hash immutable
```

Kiểm tra:

* non-manifold;
* missing texture;
* broken UV;
* excessive polycount;
* unsupported shader;
* excessive VRAM;
* missing normals;
* broken skeleton.

**Gate**

```text
VP3D_P7_ASSET_NORMALIZATION_VERIFIED
```

---

# Stage D — Character System

## Phase 8 — Character Master Asset

Do bạn chọn `4C`, hệ thống hỗ trợ cả nhân vật cố định lẫn sinh mới.

Mỗi character:

```text
CharacterMaster
├── canonical mesh
├── skeleton
├── facial rig
├── materials
├── textures
├── proportions
├── voice_profile_id
├── animation_profile
├── style fingerprint
└── approved versions
```

Một nhân vật dùng xuyên nhiều episode phải dùng cùng `CharacterMasterId`.

Không regenerate nhân vật mỗi shot.

Điều này giải quyết continuity ở cấp 3D tốt hơn rất nhiều so với Flow.

---

# Phase 9 — Rigging & Retargeting

Tạo:

```text
SkeletonProfile
RigProfile
RetargetProfile
AnimationCompatibilityProfile
```

Pipeline:

```text
generated/imported character
        ↓
skeleton detection
        ↓
rig validation
        ↓
retarget normalization
        ↓
animation test suite
```

Test tối thiểu:

```text
idle
walk
run
sit
stand
turn
point
grab
talk
facial neutral
```

**Gate**

```text
VP3D_P9_CHARACTER_RIG_VERIFIED
```

---

# Stage E — Audio chạy song song

## Phase 10 — Concurrent Audio Production

Kiến trúc hiện tại rất phù hợp vì TTS đã được tách qua `TtsProviderPort`, cùng voice casting và forced alignment.

Sau khi screenplay lock:

```text
                    Screenplay LOCKED
                           │
             ┌─────────────┴────────────┐
             ▼                          ▼
        Audio Pipeline              3D Pipeline
             │                          │
       dialogue prep                 assets
             │                       scenes
       voice casting               animation
             │
            TTS
             │
     forced alignment
```

Hai nhánh chạy song song.

### Voice identity

Mỗi nhân vật:

```text
CharacterMasterId
      ↓
VoiceProfileId
      ↓
TTS provider/model
      ↓
voice parameters
```

Mục tiêu:

```text
same character
    =
same voice
```

TTS open-source được đưa vào bằng adapter:

```text
TtsProviderPort
 ├── LocalTtsAdapter_A
 ├── LocalTtsAdapter_B
 └── APIAdapter
```

Không hard-code engine TTS.

---

# Stage F — Scene Construction

## Phase 11 — Scene Compiler

Input:

```text
Production IR
+
approved assets
+
Director plan
+
Shot graph
+
continuity ledger
```

Output:

```text
BlenderScenePlan
```

Compiler chịu trách nhiệm:

```text
collections
objects
characters
props
world
camera
lighting
animations
materials
frame ranges
render configuration
```

Sau đó adapter biến:

```text
BlenderScenePlan
      ↓
bpy commands
      ↓
.blend
```

Không cho LLM trực tiếp viết arbitrary Blender Python và chạy.

Agent tạo **typed plan**.

Trusted compiler mới viết `bpy`.

Đây là ranh giới an toàn rất quan trọng.

---

# Phase 12 — Environment & Set Dressing

Agent có thể:

* chọn environment asset;
* tạo environment mới;
* scatter props;
* sử dụng procedural Geometry Nodes;
* đặt character;
* kiểm tra collision;
* bố trí scene.

Xây:

```text
EnvironmentBuilder
SetDressingPlanner
PropPlacementPlanner
SpatialConstraintValidator
```

Ví dụ:

```text
table không xuyên tường
character không xuyên sàn
chair đúng chiều
camera không nằm trong mesh
```

---

# Stage G — Cinematography

## Phase 13 — Blender Camera Compiler

Giữ lại phần Director/Shot Planner hiện có.

Domain đang có:

```text
ShotType
CameraMovement
CameraAngle
CameraSide
TransitionType
```

nên phần này tái sử dụng được tốt.

Compiler chuyển:

```text
DOLLY
PAN
TILT
TRACK
CRANE
STATIC
```

thành Blender camera rigs.

Thêm:

```text
lens
sensor
DOF
focus target
camera path
look-at constraint
safe framing
```

Automatic validation:

```text
180-degree rule
head room
look room
subject visibility
occlusion
camera collision
```

---

# Phase 14 — Lighting System

Phim hoạt hình 3D nên dùng lighting preset thay vì agent tự tạo mọi thứ từ đầu.

Ví dụ:

```text
CARTOON_DAY
CARTOON_NIGHT
INTERIOR_SOFT
MAGIC_FOREST
SUNSET
DRAMATIC
COMEDY_BRIGHT
```

Director chọn intention:

```text
mood = HAPPY
time = MORNING
style = CHILDREN_3D
```

Lighting compiler chọn rig.

Sau này Unreal có thể map cùng intent sang Lumen lighting.

---

# Stage H — Animation

## Phase 15 — Animation Layer V1: Library + Mocap

Dù bạn chọn D, không nên triển khai cả 3 hướng cùng lúc ngay phase đầu.

Thứ tự triển khai:

```text
Animation Library
       ↓
Mocap Retargeting
       ↓
Procedural
       ↓
AI Motion Generation
```

Các clip cơ bản:

```text
idle
walk
run
jump
sit
stand
talk
laugh
cry
point
wave
pick-up
put-down
```

Director chỉ phát:

```text
AnimationIntent(
    actor="char_01",
    action="walk",
    destination="chair_03",
    emotion="happy"
)
```

---

# Phase 16 — Procedural Animation

Sau khi library ổn định:

```text
look-at
head tracking
eye tracking
hand IK
foot IK
walk path
object grabbing
sitting alignment
turning
idle variation
```

Blender procedural layer tự tạo transition.

---

# Phase 17 — AI Motion Adapter

Sau đó mới thêm:

```text
TextToMotionPort
VideoToMotionPort
MotionGenerationPort
```

AI output không bao giờ được đưa thẳng vào scene.

Phải qua:

```text
motion
 ↓
skeleton remap
 ↓
joint-limit validation
 ↓
foot sliding detection
 ↓
collision detection
 ↓
retarget
```

**Gate**

```text
VP3D_P17_AI_MOTION_VERIFIED
```

---

# Stage I — Facial Animation

## Phase 18 — Lip-sync / Facial Pipeline

Audio đã tồn tại trước animation final nên:

```text
TTS
 ↓
forced alignment
 ↓
phoneme timing
 ↓
viseme sequence
 ↓
emotion curve
 ↓
facial rig
```

Input:

```text
word timestamps
phonemes
emotion
speaker
```

Output:

```text
FacialAnimationTrack
```

Ngoài miệng:

```text
blink
eyebrow
eyes
head motion
emotion
```

Điều này sẽ làm nhân vật bớt cảm giác robot đáng kể.

---

# Stage J — Rendering

## Phase 19 — Cycles Production Renderer

Bạn chọn Cycles làm default.

Profiles:

```text
PREVIEW
FINAL
FINAL_HIGH
```

Nhưng:

```text
FINAL default = Cycles
```

Không tự chuyển sang Eevee nếu không được user cho phép.

RTX 5060:

```text
Cycles
 ↓
OptiX/CUDA capability probe
 ↓
GPU rendering
```

Các tối ưu bắt buộc:

* adaptive sampling;
* denoise;
* persistent data khi có lợi;
* texture budget;
* geometry budget;
* BVH optimization;
* instancing;
* asset reuse;
* motion blur budget;
* light bounce budget;
* transparent bounce budget;
* LOD.

---

# Phase 20 — VRAM Budget Manager

8 GB VRAM là constraint quan trọng.

Tạo:

```text
SceneResourceEstimator
VramBudgetPolicy
TextureBudgetPolicy
GeometryBudgetPolicy
```

Ví dụ:

```text
SAFE         < 6.0 GB estimated
WARNING      6.0–7.0 GB
BLOCK        > 7.0 GB
```

Không cố sử dụng đủ 8 GB vì Windows, Blender và driver còn chiếm VRAM.

Khi quá budget:

```text
lower texture resolution
use LOD
instance meshes
remove hidden geometry
split shot
```

không crash rồi retry mù.

---

# Phase 21 — Fault-tolerant Render Jobs

Render theo:

```text
episode
  ↓
scene
  ↓
shot
  ↓
frame chunk
```

Ví dụ:

```text
shot_001/
   frames/
      000001.png
      ...
```

Job crash ở frame 121:

```text
resume frame 122
```

Không render lại frame 1.

Receipt từng chunk:

```text
scene_hash
shot_hash
frame_start
frame_end
render_config_hash
asset_hashes
Blender version
GPU
duration
output hashes
```

---

# Stage K — Quality Review

## Phase 22 — 3D Technical Reviewer

Reviewer hiện tại đang review media output; giữ lại nhưng thêm reviewer 3D trước render.

### Pre-render review

Kiểm tra:

```text
missing object
missing texture
broken rig
camera collision
character collision
light missing
wrong frame range
audio timing mismatch
VRAM overflow
```

### Post-render review

Kiểm tra:

```text
black frames
broken frames
flicker
character identity
lip sync
occlusion
continuity
lighting consistency
motion quality
```

---

# Phase 23 — Intelligent Retry

Không phải lỗi nào cũng rerender toàn scene.

Ví dụ:

```text
lip-sync issue
→ regenerate facial track only

camera issue
→ camera compile again

missing texture
→ asset fix

bad motion
→ regenerate animation

render noise
→ rerender affected frames
```

Tạo:

```text
FailureClassifier
RepairPlanner
InvalidationPlanner
```

---

# Stage L — Post-production

## Phase 24 — FFmpeg Assembly

Phần hiện tại giữ gần như nguyên vẹn vì đã có:

```text
InputNormalizer
AssemblyPlanner
FfmpegRunner
MediaVerifier
ReproducibilityAuditor
```

Pipeline:

```text
rendered image sequence
        +
dialogue
        +
music
        +
SFX
        ↓
FFmpeg assembly
        ↓
subtitle
        ↓
final verification
        ↓
MP4
```

---

# Stage M — End-to-End

## Phase 25 — 30–60 Second Golden Scene

Không test ngay 20 phút.

Golden test đầu tiên:

```text
2 characters
1 environment
dialogue
walk animation
interaction
camera movement
lighting
lip-sync
Cycles render
audio
FFmpeg
```

Acceptance:

```text
Script
 ↓
Assets
 ↓
Scene
 ↓
Animation
 ↓
Audio
 ↓
Render
 ↓
Review
 ↓
Final video
```

không thao tác Blender thủ công.

**Gate**

```text
VP3D_P25_GOLDEN_SCENE_E2E_PASSED
```

---

# Phase 26 — 2–3 Minute Episode

Tăng lên:

```text
3+ scenes
5+ shots
2–4 characters
multiple environments
```

Test:

* asset reuse;
* continuity;
* cache;
* restart;
* failed render;
* partial rerender;
* TTS concurrency.

---

# Phase 27 — 5-Minute Production Acceptance

Đây là milestone đầu tiên thực tế.

Target:

```text
1080p
24fps
Cycles
RTX 5060 8GB
32GB RAM
single machine
```

Đo:

```text
preproduction time
asset generation time
scene compilation
animation time
render time
post-production
total wall clock
GPU utilization
peak VRAM
```

---

# Phase 28 — Performance Optimization

Chỉ tối ưu dựa trên profiling.

Không tối ưu cảm tính.

Cần artifact:

```text
performance_profile.json
gpu_profile.json
scene_complexity.json
asset_cache_report.json
render_time_by_shot.json
```

Tìm:

```text
slowest shots
largest assets
largest textures
largest BVH
highest sample counts
most expensive lights
```

---

# Phase 29 — 10-Minute Episode Acceptance

Target thứ hai.

Yêu cầu:

```text
asset-ready
≤ 3h preferred
```

Nếu >3h:

```text
PERFORMANCE_GATE_FAILED
```

không fake PASS.

---

# Phase 30 — 20-Minute Episode Acceptance

Đây mới là production target cuối.

20 phút × 24fps:

```text
28,800 frames
```

Để ≤3 giờ:

```text
10,800 seconds / 28,800
≈ 0.375 s/frame
```

Vì vậy Cycles ở target này có nguy cơ là blocker.

Roadmap nên đặt gate:

```text
VP3D_P30_20MIN_THROUGHPUT_TARGET
```

Verdict có thể:

```text
PASS
DEGRADED
BLOCKED_BY_RENDER_THROUGHPUT
```

Nếu Cycles không đạt, hệ thống **không tự đổi Eevee** vì bạn đã chọn Cycles mặc định. Khi đó mới đưa ra benchmark để bạn quyết định:

* chấp nhận lâu hơn;
* giảm fps;
* giảm resolution;
* giảm Cycles quality;
* cho phép hybrid Eevee/Cycles;
* nâng GPU;
* hoặc chuyển sớm sang Unreal.

---

# Stage N — Workspace / Human Editing

## Phase 31 — Blender Manual Override

Đúng theo đề xuất trước:

```text
Production IR = source of truth
.blend = editable derived artifact
```

Người dùng có thể mở `.blend`.

Manual changes phải được ghi:

```text
ManualOverrideManifest
```

Ví dụ:

```text
camera manually modified
light manually modified
character manually repositioned
```

WindAgent không được regenerate đè lên override mà không cảnh báo.

---

# Phase 32 — Asset Library & Episode Reuse

Đây là phase cực quan trọng nếu làm series hoạt hình.

Library:

```text
characters/
environments/
props/
animations/
voices/
materials/
lighting/
camera_rigs/
facial_profiles/
```

Episode sau ưu tiên:

```text
REUSE
```

thay vì generation.

Đây cũng là yếu tố chính để giữ target `<3h`.

---

# Stage O — Production Hardening

## Phase 33 — Security & Add-on Governance

Allowlist:

```yaml
blender_addons:
  - id
  - version
  - sha256
  - source
  - permissions
  - approved_at
```

Nếu agent tìm được add-on mới:

```text
DISCOVER
   ↓
QUARANTINE
   ↓
REQUEST USER APPROVAL
```

Chỉ sau approval mới sử dụng.

---

# Phase 34 — Reproducibility

Một production job phải lưu:

```text
WindAgent SHA
Blender version
Python script hashes
asset hashes
animation hashes
voice model
TTS version
render settings
random seeds
FFmpeg version
```

Từ đó có thể tái tạo một shot.

---

# Phase 35 — Full Flow Purge Certification

Dù Flow đã bị xóa từ Phase 2, phase này chứng minh không còn residue.

Check:

```text
Google Flow imports = 0
browser Flow runtime = 0
Flow schemas = 0
Flow config = 0
Flow tests = 0
Flow docs runtime references = 0
Flow credentials = 0
```

Historical evidence có thể giữ trong archive.

**Gate**

```text
GOOGLE_FLOW_FULLY_RETIRED
```

---

# Stage P — Chuẩn bị Unreal

## Phase 36 — Engine-neutral Export Layer

Trước khi chạm Unreal, kiểm tra mọi thứ có thể export:

```text
SceneDescription
CharacterInstance
CameraTrack
AnimationTrack
FacialTrack
LightRig
RenderIntent
```

Blender không được leak vào domain như:

```python
bpy.Object
bpy.Scene
bpy.Material
```

Các loại đó chỉ tồn tại trong:

```text
BlenderEngineAdapter
```

---

# Phase 37 — USD/glTF Interchange

Canonical:

```text
WindAgent IR
   ↓
USD / glTF / FBX
   ↓
Blender
```

và:

```text
WindAgent IR
   ↓
USD / glTF / FBX
   ↓
Unreal
```

Asset library không phải migrate lại khi Unreal xuất hiện.

---

# Stage Q — Unreal Engine

## Phase 38 — Unreal Adapter PoC

Chưa thay Blender.

Một scene đã tạo bởi WindAgent:

```text
WindAgent IR
      ↓
UnrealEngineAdapter
      ↓
Unreal project
      ↓
camera
animation
lighting
render
```

So sánh với Blender.

Tài liệu Epic hiện đang phục vụ bộ Unreal Engine 5.8, nhưng khi bắt đầu phase này nên pin một phiên bản cụ thể thay vì chạy theo latest. ([Epic Games Developers][3])

---

# Phase 39 — Blender → Unreal Asset Pipeline

Theo lựa chọn `12C`:

Blender chuyển dần thành:

```text
model creation
asset cleanup
UV
rig
animation preparation
```

Unreal đảm nhiệm:

```text
scene
lighting
camera
render
```

---

# Phase 40 — Unreal Production Renderer

Khi Unreal đạt parity:

```text
ProductionEnginePort
        │
        ├── BlenderEngineAdapter
        └── UnrealEngineAdapter ← default render
```

Sau đó mới cân nhắc:

```text
Blender scene rendering → deprecated
```

nhưng Blender vẫn tồn tại cho asset authoring.

---

# Thứ tự dependency thực tế

Không nên triển khai 40 phase hoàn toàn tuần tự.

Critical path:

```text
P0
 ↓
P1
 ↓
P2
 ↓
P3
 ↓
P4
 ↓
P5 ─ P7
 ↓
P8 ─ P9
 ↓
P11
 ↓
P13
 ↓
P15
 ↓
P18
 ↓
P19 ─ P21
 ↓
P22
 ↓
P24
 ↓
P25
```

Trong khi đó sau screenplay lock:

```text
              ┌─ Asset Generation
              │
Screenplay ───┼─ TTS / Alignment
              │
              ├─ Environment
              │
              └─ Animation preparation
```

chạy song song.

Đây là cách giảm wall-clock time hiệu quả nhất.

---

# Kiến trúc package tôi đề xuất

```text
core/
└── domain/
    └── video_production/
        ├── production_ir/
        ├── scene/
        ├── animation/
        ├── asset/
        ├── render/
        └── engine/

intelligence/
└── video/
    ├── director/
    ├── shot_planner/
    ├── continuity/
    ├── scene_planner/
    ├── animation_planner/
    ├── asset_planner/
    ├── lighting/
    ├── audio/
    ├── reviewers/
    └── postproduction/

tools/
└── windagent_tools/
    └── production_engines/
        ├── base/
        ├── blender/
        │   ├── runtime/
        │   ├── compiler/
        │   ├── assets/
        │   ├── rigging/
        │   ├── animation/
        │   ├── camera/
        │   ├── lighting/
        │   └── rendering/
        │
        └── unreal/          # future

providers/
└── assets/
    ├── mesh_api/
    ├── mesh_mcp/
    ├── internet/
    └── local/

workspace/
└── artifacts/
```

---

# Thay đổi lớn nhất đối với code hiện tại

Tôi chia thành ba nhóm.

**Giữ gần như nguyên vẹn:**

```text
ideation
screenplay
entity extraction
style design
Director
shot graph
continuity
audio
review concepts
post-production
workspace
artifact storage
durable workflow
```

Pre-production hiện đã được thiết kế provider-neutral, đây là lợi thế lớn.  Audio cũng đã đi qua TTS port.  Post-production đã tách FFmpeg execution riêng.

**Viết lại mạnh:**

```text
GenerationMode
PromptCompiler phần video generation
reference-binding semantics
generation job
candidate generation
asset generation workflow
```

**Xóa:**

```text
google_flow/
flow navigation
flow image
flow video
flow human-control
Flow browser provider
Flow credential/config
```

---

# Các milestone chính

| Milestone | Kết quả                                 |
| --------- | --------------------------------------- |
| M1        | Google Flow bị xóa                      |
| M2        | Engine-neutral Production IR            |
| M3        | Blender headless chạy ổn định           |
| M4        | Asset Mesh API/MCP + Internet hoạt động |
| M5        | Character + rig + reuse                 |
| M6        | Scene compiler                          |
| M7        | Animation + TTS + lip-sync              |
| M8        | Cycles deterministic renderer           |
| M9        | 30–60s E2E                              |
| M10       | 5 phút E2E                              |
| M11       | 10 phút production                      |
| M12       | 20 phút production                      |
| M13       | Unreal-ready IR                         |
| M14       | Unreal PoC                              |
| M15       | Unreal trở thành renderer chính         |

## Phán quyết kiến trúc

Với yêu cầu bạn vừa chốt, tôi sẽ coi kiến trúc chính thức là:

```text
VideoClaw-derived Preproduction concepts
            +
WindAgent Director
            +
WindAgent Production IR
            +
3D Asset Intelligence
            +
Blender Production Engine
            +
WindAgent Audio / Review / FFmpeg
```

Google Flow **không còn nằm trong kiến trúc mục tiêu**.

Blender cũng **không trở thành một provider kiểu Flow**. Nó trở thành implementation đầu tiên của `ProductionEnginePort`.

Đây là quyết định quan trọng nhất của roadmap, vì nó cho phép vài tháng sau chuyển:

```text
Blender final rendering
        ↓
Unreal final rendering
```

mà không phải viết lại screenplay, Director, shot graph, audio, asset library, character master hay production workflow.

Về mặt triển khai, tôi khuyến nghị bắt đầu chính thức từ **Phase 0 → Phase 4 trước**, chưa chạm Mesh API/MCP hay character generation. Khi deterministic Blender kernel đã chứng minh `WindAgent → .blend → Cycles frames → FFmpeg → video` hoạt động hoàn toàn tự động, lúc đó mới mở rộng lên asset/rig/animation.

[1]: https://www.blender.org/get-involved/Dashboard/?utm_source=chatgpt.com "Dashboard — Blender"
[2]: https://docs.blender.org/manual/es/latest/render/output/introduction.html?utm_source=chatgpt.com "Introducción - Blender 4.5 LTS Manual"
[3]: https://dev.epicgames.com/documentation/en-us/unreal-engine/install-unreal-engine?utm_source=chatgpt.com "Install Unreal Engine | Unreal Engine 5.8 Documentation | Epic Developer Community"
