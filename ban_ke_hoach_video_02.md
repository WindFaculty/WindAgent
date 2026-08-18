# WINDAGENT CODE VIDEO — VIDEO 02 IMPLEMENTATION PLAN

## 1. Baseline

Repository:

```text
WindFaculty/WindAgent
```

Baseline bắt buộc:

```text
0e2fa7a89c4e0c0875fab963bbe8278f4153783a
```

Không triển khai dựa trên `main` thay đổi sau baseline mà chưa review diff.

Commit baseline đã hoàn thành Phase 14–16, bao gồm Web/Desktop convergence, API V3 cutover và dead-code cleanup.

Nguồn nội dung chuẩn của Video 02 là kịch bản:

```text
VIDEO 02 — VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON
```

với milestone:

```text
Agentic Studio v0.1
Simple Agent
```

và kiến trúc bắt buộc cuối video:

```text
User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

Không đưa Tool Calling vào Video 02.

---

# 2. Mục tiêu cuối cùng

WindAgent phải có thể nhận:

```text
Video 02 script
        ↓
WindAgent
        ↓
Build tutorial repository
        ↓
Verify code
        ↓
Build deterministic recording plan
        ↓
Replay code + terminal
        ↓
Record visual scenes
        ↓
Render diagrams / title cards
        ↓
Assemble visual timeline
        ↓
QC
        ↓
video_02_visual_master.mp4
```

Audio **không thuộc scope**.

Người dùng sẽ tự lồng tiếng sau.

Do đó output cuối phải ưu tiên:

```text
VISUAL MASTER
+
TIMELINE
+
VOICE CUE SHEET
```

thay vì final YouTube master.

---

# 3. Nguyên tắc triển khai

## 3.1 Build trước — quay sau

Cấm để model vừa suy nghĩ vừa code trong lúc recorder đang chạy.

Pipeline bắt buộc:

```text
BUILD
 ↓
TEST
 ↓
VERIFY
 ↓
FREEZE
 ↓
REPLAY
 ↓
RECORD
```

Không:

```text
RECORD
 ↓
LLM coding live
 ↓
debug live
 ↓
hope it works
```

---

## 3.2 Không fake terminal

Nếu script nói:

```text
2 passed
```

nhưng runtime thực tế cho:

```text
3 passed
```

WindAgent phải trả:

```text
SCRIPT_RUNTIME_MISMATCH
```

Không được render giả:

```text
2 passed
```

---

## 3.3 Không điều khiển editor bằng tọa độ chuột

Không xây workflow phụ thuộc vào:

```text
click(x=731, y=442)
```

cho việc quay code.

Thay vào đó:

```text
CodeVideoPlan
      ↓
Code Studio Renderer
      ↓
semantic actions
```

Ví dụ:

```text
OPEN_FILE
TYPE_TEXT
SELECT_RANGE
HIGHLIGHT_SYMBOL
SCROLL_TO_SYMBOL
RUN_COMMAND
WAIT
SHOW_DIAGRAM
```

Browser subsystem hiện tại đã có action policy/session/evidence infrastructure, nhưng evidence capture chỉ lưu hash screenshot chứ chưa phải video recorder.

---

# 4. Architecture mục tiêu

```text
                        Video02Script
                             │
                             ▼
                    CodeVideoCompiler
                             │
                             ▼
                       CodeVideoPlan
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   Workspace Builder    Visual Assets      Timeline Cues
          │
          ▼
    Sandbox Executor
          │
    ┌─────┼─────┬──────┬───────┐
    ▼     ▼     ▼      ▼       ▼
 Files  Shell   Git   Pytest  Provider
    │
    └──────────┬───────────────┘
               ▼
        Golden Checkpoints
               │
               ▼
           Replay Engine
               │
       ┌───────┴─────────┐
       ▼                 ▼
 Code Renderer      Terminal Renderer
       │                 │
       └────────┬────────┘
                ▼
          Capture Engine
                │
                ▼
             Takes
                │
        ┌───────┴────────┐
        ▼                ▼
     Diagrams        Title Cards
        │                │
        └───────┬────────┘
                ▼
         Timeline Builder
                │
                ▼
             FFmpeg
                │
                ▼
     video_02_visual_master.mp4
```

---

# 5. Package layout đề xuất

Không đưa Code Video vào:

```text
tools/windagent_tools/production_engines/blender/
```

Blender hiện là production engine riêng với render/runtime/recovery/FFmpeg stack.

Tạo:

```text
workflows/
└── windagent_workflows/
    └── code_video/
        ├── __init__.py
        ├── definition.py
        ├── contracts.py
        ├── compiler.py
        ├── director.py
        ├── executor.py
        ├── replay.py
        ├── timeline.py
        └── verifier.py
```

Tool layer:

```text
tools/
└── windagent_tools/
    └── code_video/
        ├── __init__.py
        ├── workspace/
        │   ├── sandbox.py
        │   ├── checkpoints.py
        │   └── repository_builder.py
        │
        ├── renderer/
        │   ├── code_renderer.py
        │   ├── terminal_renderer.py
        │   ├── diagram_renderer.py
        │   └── title_renderer.py
        │
        ├── capture/
        │   ├── base.py
        │   ├── browser_capture.py
        │   └── receipts.py
        │
        └── media/
            ├── assembler.py
            └── verifier.py
```

Frontend renderer:

```text
frontend/
└── packages/
    └── code-video-ui/
        ├── src/
        │   ├── CodeStudio.tsx
        │   ├── CodeEditor.tsx
        │   ├── Terminal.tsx
        │   ├── FileTree.tsx
        │   ├── DiagramStage.tsx
        │   ├── Overlay.tsx
        │   └── ReplayController.ts
        └── tests/
```

Hiện frontend đã được tổ chức theo package như `story-ui`, `production-ui`, `studio-*`, nên tạo package renderer riêng phù hợp với cách chia module hiện tại.

---

# PHASE 0 — FREEZE BASELINE & VIDEO 02 SOURCE

## Mục tiêu

Khóa toàn bộ input trước khi viết code.

## Thực hiện

Tạo branch:

```text
feature/code-video-video02
```

từ:

```text
0e2fa7a89c4e0c0875fab963bbe8278f4153783a
```

Tạo:

```text
artifacts/code_video/video_02/
```

Cấu trúc:

```text
video_02/
├── source/
│   ├── script.md
│   ├── script.sha256
│   └── baseline.json
│
├── plans/
├── checkpoints/
├── takes/
├── graphics/
├── timeline/
├── reports/
└── final/
```

`baseline.json`:

```json
{
  "video_id": "video-02",
  "baseline_sha": "0e2fa7a89c4e0c0875fab963bbe8278f4153783a",
  "audio_scope": "EXCLUDED",
  "target_duration_seconds": 975,
  "tutorial_project": "agentic-studio",
  "milestone": "v0.1"
}
```

16:15 =:

```text
975 seconds
```

---

## Gate

```text
CV02_P0_BASELINE_FROZEN
```

PASS khi:

* baseline SHA đúng;
* script hash cố định;
* duration 975 giây;
* audio marked `EXCLUDED`;
* Tool Calling marked `OUT_OF_SCOPE`;
* repository WindAgent sạch trước implementation.

---

# PHASE 1 — CODE VIDEO CONTRACT & IR

## Mục tiêu

Định nghĩa representation trung gian cho video.

Không để renderer đọc trực tiếp Markdown script.

---

## Core objects

### CodeVideoPlan

```text
CodeVideoPlan
├── video_id
├── schema_version
├── duration
├── resolution
├── fps
├── scenes[]
├── source_hash
└── output_policy
```

### Scene

```text
Scene
├── scene_id
├── start
├── end
├── visual_mode
├── actions[]
├── expected_state
└── annotations[]
```

### Action

Các action tối thiểu:

```text
OPEN_WORKSPACE
OPEN_FILE
CREATE_FILE
TYPE_TEXT
REPLACE_TEXT
SELECT_RANGE
HIGHLIGHT
SCROLL
ZOOM
RUN_TERMINAL
WAIT
SHOW_OUTPUT
SHOW_DIAGRAM
SHOW_TITLE
SHOW_CHECKLIST
SHOW_ARCHITECTURE
SWITCH_LAYOUT
RESET_VIEW
```

---

## Quy tắc

Action phải semantic.

Ví dụ tốt:

```yaml
action: highlight
symbol: Message
```

Không:

```yaml
x: 712
y: 418
width: 330
height: 52
```

---

## Timeline precision

Mọi scene dùng integer milliseconds:

```text
start_ms
duration_ms
```

Không dùng float seconds làm authority.

---

## Audio

Schema vẫn có thể dự phòng:

```text
voice_cue_id
```

nhưng không chứa:

```text
audio_path
tts_model
voice_id
```

ở Video 02.

---

## Tests

* schema roundtrip;
* duplicate scene ID;
* overlapping scene policy;
* action validation;
* invalid duration;
* action ngoài scene bounds;
* unknown action;
* missing source hash.

---

## Gate

```text
CV02_P1_PLAN_CONTRACT_VERIFIED
```

---

# PHASE 2 — ISOLATED TUTORIAL WORKSPACE

## Mục tiêu

WindAgent phải build project trong workspace riêng.

Không tạo `agentic-studio` bên trong source tree WindAgent.

---

## Workspace

Ví dụ:

```text
.tmp/
└── code_video/
    └── video_02/
        └── agentic-studio/
```

---

## Tận dụng tool hiện tại

WindAgent hiện export sẵn:

```text
PathSandbox
ReadFileTool
WriteFileTool
SafeShellRunner
ExecShellTool
GitTool
CodeSearchTool
ASTSymbolExtractorTool
LSPTool
TestRunnerTool
```

Safe shell đã có:

* timeout;
* command deny policy;
* workspace checks;
* secret masking;
* stdout/stderr redaction.

Không viết shell executor thứ hai.

---

## Tutorial repository

WindAgent phải có builder deterministic tạo:

```text
agentic-studio/
├── src/
│   ├── __init__.py
│   └── agent.py
├── tests/
│   └── test_agent.py
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

đúng Definition of Done của kịch bản.

---

## Security gate

Trước mọi recording:

```text
git grep
secret scanner
.env check
terminal output scan
```

Cấm xuất hiện:

```text
AIza...
sk-...
gsk_...
nvapi-...
Bearer ...
```

---

## Gate

```text
CV02_P2_SANDBOX_READY
```

---

# PHASE 3 — BUILD GOLDEN TUTORIAL

## Mục tiêu

Hoàn thành toàn bộ code Video 02 trước khi quay frame đầu tiên.

---

## Step 3.1 — Repository initialization

Thực thi thật:

```bash
mkdir agentic-studio
cd agentic-studio
git init
```

---

## Step 3.2 — Message

Checkpoint:

```text
cp_01_message
```

Code đúng nội dung tutorial.

Verify:

```text
import works
Role validation works
Message immutable
```

---

## Step 3.3 — AgentConfig

Checkpoint:

```text
cp_02_config
```

Verify:

```text
name
system_prompt
model
temperature
```

---

## Step 3.4 — LLMClient

Checkpoint:

```text
cp_03_llm_protocol
```

Verify Agent core không import SDK provider.

---

## Step 3.5 — FakeLLMClient

Checkpoint:

```text
cp_04_fake_llm
```

Fake phải deterministic.

Không network.

---

## Step 3.6 — Agent

Checkpoint:

```text
cp_05_agent
```

Verify:

```text
user_input
→ system Message
→ user Message
→ LLMClient.generate()
→ answer
```

---

## Step 3.7 — Tests

Build đúng tests của tutorial.

Target:

```text
2 passed
```

Nếu thực tế không phải 2:

```text
BLOCK
SCRIPT_RUNTIME_MISMATCH
```

---

## Step 3.8 — Real provider

Tạo infrastructure adapter.

Không để SDK provider leak vào Agent core.

API key từ environment.

---

## Quan trọng

**API thật chỉ dùng trong preflight.**

Kết quả demo sau khi pass được freeze thành:

```text
provider_demo_receipt.json
provider_demo_output.txt
```

Khi quay final take:

```text
NO LIVE PROVIDER DEPENDENCY
```

Việc này ngăn:

* network failure;
* quota;
* model output khác;
* latency;
* response dài bất thường.

---

## Step 3.9 — Git milestone

Trong tutorial repo:

```bash
git add .
git commit -m "feat: build simple agent core"
git tag video-02
git tag v0.1
```

Không tạo các tag trên repository WindAgent.

---

## Golden final checkpoint

```text
cp_09_v0_1
```

---

## Gate

```text
CV02_P3_GOLDEN_TUTORIAL_VERIFIED
```

PASS khi toàn bộ DoD của script đều PASS.

---

# PHASE 4 — SCRIPT → VIDEO PLAN COMPILER

## Mục tiêu

Chuyển timeline 16:15 thành machine-readable plan.

---

# Scene map bắt buộc

```text
S01  00:00–00:25  Cold Open
S02  00:25–00:50  Hook
S03  00:50–01:25  Video 01 Recap
S04  01:25–02:10  Architecture v0.1
S05  02:10–02:45  Create Repository
S06  02:45–03:40  Message
S07  03:40–04:35  AgentConfig
S08  04:35–06:00  LLMClient
S09  06:00–06:50  Fake LLM
S10  06:50–08:25  Agent
S11  08:25–09:00  Is This An Agent?
S12  09:00–10:15  Real Provider
S13  10:15–11:05  API Key
S14  11:05–12:00  First Run
S15  12:00–13:20  Tests
S16  13:20–14:10  Not Yet
S17  14:10–15:00  Architecture Review
S18  15:00–15:35  Git Milestone
S19  15:35–16:15  Video 03 Teaser
```

---

## Output

```text
plans/video_02_plan.yaml
plans/video_02_plan.json
plans/video_02_cue_sheet.csv
```

---

## Cue sheet

Ví dụ:

```csv
start,end,scene,voice_reference
00:00,00:25,S01,COLD_OPEN
00:25,00:50,S02,HOOK
...
```

File này dành cho lúc lồng tiếng sau.

---

## Gate

Tổng duration tuyệt đối:

```text
00:16:15.000
```

Không:

```text
16:14.2
16:16.8
```

---

# PHASE 5 — CODE STUDIO RENDERER

## Mục tiêu

Tạo môi trường quay code riêng.

Không cần VS Code thật trong Video 02.

---

## Layout

```text
┌──────────────────────────────────────────────────────┐
│ agentic-studio                         VIDEO 02      │
├──────────────┬───────────────────────────────────────┤
│ FILE TREE    │ src/agent.py                          │
│              │                                       │
│ src          │ @dataclass(frozen=True)               │
│ tests        │ class Message:                        │
│ README       │     ...                               │
│              │                                       │
├──────────────┴───────────────────────────────────────┤
│ TERMINAL                                             │
│ PS ...\agentic-studio> pytest                       │
└──────────────────────────────────────────────────────┘
```

---

## Thành phần

### FileTree

Hiện:

```text
src
tests
.env.example
.gitignore
pyproject.toml
README.md
```

### Editor

Yêu cầu:

* Python syntax highlight;
* cursor;
* line numbers;
* selection;
* smooth scroll;
* controlled typing;
* focus mode;
* zoom region.

### Terminal

Yêu cầu:

* deterministic command playback;
* stdout/stderr;
* prompt;
* clear;
* scroll;
* command emphasis.

---

## Recording-safe UI

Tắt:

```text
notifications
autocomplete popups
Git decorations không cần thiết
minimap
breadcrumbs dư thừa
OS notification
clock
personal username
machine hostname
```

---

## Gate

```text
CV02_P5_CODE_STUDIO_RENDERER_VERIFIED
```

---

# PHASE 6 — DETERMINISTIC REPLAY ENGINE

## Mục tiêu

Tái hiện quá trình coding từ checkpoints đã được verify.

---

## Nguyên tắc

Replay engine không hỏi model:

> viết gì tiếp theo?

Nó đã có exact patch.

---

## Example

```yaml
- action: OPEN_FILE
  path: src/agent.py

- action: TYPE_TEXT
  source: fragments/message.py
  chars_per_second: 18

- action: WAIT
  duration_ms: 800

- action: HIGHLIGHT
  symbol: Message
  duration_ms: 1800
```

---

## Typing

Cho phép:

```text
instant
fast
normal
slow
```

Nhưng timeline authority vẫn tính bằng milliseconds.

---

## Terminal

Ví dụ:

```yaml
- action: RUN_TERMINAL
  command: pytest

  expected:
    exit_code: 0
    contains:
      - "2 passed"
```

Command chạy trong preflight.

Final replay có thể dùng verified receipt để đảm bảo kết quả giống golden run.

---

## Recovery

Nếu renderer crash:

```text
resume_from:
    scene_id
    action_id
```

Không quay lại toàn bộ 16 phút.

---

## Gate

Chạy cùng plan hai lần phải tạo:

```text
same action sequence hash
same checkpoint hash
same expected terminal output
```

---

# PHASE 7 — CAPTURE ENGINE

## Mục tiêu

Biến replay thành video take.

---

## V1 target

Ưu tiên capture riêng Code Studio.

Không phụ thuộc OBS cho acceptance đầu tiên.

OBS có thể trở thành adapter sau.

---

## Interface

```python
class CapturePort(Protocol):
    start(...)
    mark(...)
    stop(...)
    inspect(...)
```

---

## Capture receipt

Mỗi take:

```json
{
  "take_id": "S10_T01",
  "scene_id": "S10",
  "start_ms": 410000,
  "duration_ms": 95000,
  "resolution": "2560x1440",
  "fps": 30,
  "frame_count": 2850,
  "output_hash": "...",
  "status": "VERIFIED"
}
```

---

## Đề xuất master

Quay ở:

```text
2560×1440
30 fps
```

sau đó có thể export:

```text
1920×1080
```

1440p giúp chữ code giữ độ nét tốt hơn qua YouTube transcoding.

Đây là recommendation của roadmap, không phải yêu cầu từ script.

---

## Audio

Capture engine:

```text
audio = disabled
```

Output không phụ thuộc microphone/system audio.

---

## Gate

```text
CV02_P7_CAPTURE_VERIFIED
```

---

# PHASE 8 — DIAGRAMS, TITLE CARDS & B-ROLL

Phase này có thể chạy song song với Phase 5–7 sau khi Phase 4 freeze.

---

## 8.1 Phân loại Visual Assets (`REQUIRED` / `OPTIONAL` / `DERIVED`)

Toàn bộ asset thị giác trong Video 02 được phân nhóm rành mạch:

### Nhóm A: REQUIRED (Bắt buộc theo authority của Script)

1. **Diagrams**:
   - `DIAG_01_FINAL_ARCH`: `User → Agent → LLM → Answer` (S01 Cold Open, S04 Architecture v0.1).
   - `DIAG_02_COMPONENT_FLOW`: `AgentConfig → Agent → LLMClient → Provider` (S04, S08, S12).
   - `DIAG_03_TODAY_VS_NEXT`: `TODAY (User → Agent → LLM → Answer)` vs `NEXT (User → Agent → LLM → Tool)` (S19 Outro/Teaser).
   - `DIAG_04_LLMCLIENT_ABSTRACTION`: `Agent → LLMClient → [Provider A, Provider B, Local Model, Test Fake]` (S08 LLMClient Protocol).
   - `DIAG_05A_COGNITIVE_LOOP`: `Observe → Decide → Act → Observe` (S11 Concept Recap — canonical loop).
   - `DIAG_05B_MISSING_CAPABILITIES`: `Is This An Agent? — Scope Gap` (S11 Deep Dive — làm mờ các nhánh loop chưa có ở v0.1).
   - `DIAG_06_DOMAIN_VS_INFRA`: Clean Architecture Isolation (`DOMAIN: Agent, Message, AgentConfig, LLMClient` vs `INFRASTRUCTURE: Provider SDK, HTTP, API Key, Response Mapping`) (S12, S17).

2. **Title Cards**:
   - `CARD_S02_HOOK`: `VIDEO 02` — `AI AGENT ĐẦU TIÊN BẰNG PYTHON` (S02 Hook).
   - `CARD_S18_MILESTONE`: `Agentic Studio` — `v0.1 — Simple Agent` (S18 Git Milestone).
   - `CARD_S19_TEASER`: `VIDEO 03` — `TOOL CALLING HOẠT ĐỘNG BÊN TRONG NHƯ THẾ NÀO?` (S19 Next Episode).

3. **Scope Checklist (S16 — Not Yet)**:
   - `CHECKLIST_S16_NOT_YET`: Đúng 7 mục chưa có trong kịch bản (không thêm checklist v0.1 vào required):
     ```text
     Tool Calling       ✕
     Agent Loop         ✕
     Memory             ✕
     RAG                ✕
     Planning           ✕
     Multi-Agent        ✕
     Orchestration      ✕
     ```

4. **B-Roll Overlays & Callouts**:
   - `OVR_S06_MESSAGE_DATACLASS`: `@dataclass(frozen=True)`, `role`, `content` (S06).
   - `OVR_S07_CONFIG_FIELDS`: `name`, `system_prompt`, `model`, `temperature` (S07).
   - `OVR_S08_LLMCLIENT_PROTOCOL`: `class LLMClient(Protocol):` (S08).
   - `OVR_S09_UNIT_TEST_VS_API`: `Unit Test ≠ Real API` (S09).
   - `OVR_S10_EXECUTION_FLOW`: `"Hello" → Agent.run() → [system, user] → LLMClient.generate() → "Answer"` (S10).
   - `OVR_S13_API_KEY_SECURITY`: `api_key = "sk-..." ✕` (Placeholder Only — S13).
   - `OVR_S19_LLM_NOT_EXECUTOR`: `LLM ≠ Function Executor` (S19).

### Nhóm B: OPTIONAL (Bổ trợ ngữ cảnh, không bắt buộc cho pass gate)
- `DIAG_07_RECAP`: `Prompt Engineering → Chaining → Agent Architecture` (S03 Video 01 Recap — optional context).
- `OVR_S01_COLD_OPEN_SPLIT`: Split overlay hỗ trợ phân cảnh mở đầu.

### Nhóm C: DERIVED (Sinh tự động từ master)
- Các biến thể downscale 1080p, preview thumbnail, raster frame snapshot từ canonical 1440p master.

---

## 8.2 Chuẩn Visual, Safe Area & Typography (Master 1440p)

Hệ thống sử dụng `CodeVideoVisualTheme` làm nguồn chân lý duy nhất cho toàn bộ graphics:

1. **Master Canvas Resolution**: `2560×1440 px` (16:9).
2. **Safe-Area Insets (Pixel & Percentage)**:
   - **Action-Safe Inset**: `5%` (`dx = 128px`, `dy = 72px`) → Bound: `2304×1296 px`.
   - **Title-Safe Inset**: `10%` (`dx = 256px`, `dy = 144px`) → Bound: `2048×1152 px`.
   - Mọi nội dung text và visual quan trọng phải nằm tuyệt đối bên trong Title-Safe area. Không cho phép tràn (clipping).
3. **Typography Minimum Pixel Sizes** (Bỏ đơn vị pt):
   - `hero_title_font_px`: `56px – 72px` (Title cards & main headers).
   - `section_heading_font_px`: `>= 40px`.
   - `table_item_font_px`: `>= 32px`.
   - `minimum_body_font_px`: `>= 24px` (Đảm bảo sắc nét khi transcode downstream).
4. **Color & Contrast Standards**:
   - Dark theme tối ưu studio (`#0d1117` background, `#161b22` card surface, `#30363d` border).
   - Đạt chuẩn WCAG AA (Contrast ratio >= 4.5:1 đối với văn bản thông thường, >= 3:1 đối với tiêu đề lớn).

---

## 8.3 `GraphicsCatalog` & Timeline Authority

Mọi visual asset được quản lý tập trung trong `GraphicsCatalog` với đầy đủ liên kết timeline:
- **Binding thuộc tính**:
  ```text
  GraphicsCatalogEntry:
  ├── asset_id (chuỗi duy nhất)
  ├── classification (REQUIRED / OPTIONAL / DERIVED)
  ├── category (DIAGRAM / TITLE_CARD / CHECKLIST / OVERLAY)
  ├── scene_id (Scene sở tại từ Phase 4)
  ├── entry_ms (Thời điểm xuất hiện)
  ├── exit_ms (Thời điểm kết thúc)
  ├── duration_ms (exit_ms - entry_ms)
  ├── transition_in (CUT / FADE / SLIDE_UP / DISSOLVE / ZOOM_IN)
  ├── transition_out (CUT / FADE / DISSOLVE)
  ├── animation (NONE / PULSE / GLOW / DIM_INACTIVE / TYPEWRITER)
  ├── canvas_bounds (2560x1440, safe insets)
  ├── source_hash (SHA-256 nội dung semantic spec)
  ├── render_config_hash (SHA-256 cấu hình theme, layout, font)
  └── output_hash (SHA-256 file render thực tế)
  ```
- **Nguyên tắc Timeline Consumer**:
  - Phase 8 **CHỈ consume timeline từ Phase 4**, tuyệt đối không tự điều chỉnh duration hay timestamps của scene.
  - Mọi asset phải thỏa mãn `scene.start_ms <= entry_ms < exit_ms <= scene.end_ms`.
  - Bất kỳ sai lệch nào đều bị chặn và trả về lỗi chuẩn:
    ```text
    GRAPHIC_TIMING_CONFLICT
    ```

---

## 8.4 Tri-Hash Determinism

Mỗi asset sinh ra bắt buộc có 3 mã băm xác thực:
1. `source_hash`: Băm toàn bộ nội dung dữ liệu ngữ nghĩa đầu vào.
2. `render_config_hash`: Băm toàn bộ tham số render (theme, resolution, safe margins, font sizes, transition).
3. `output_hash`: Băm nội dung file artifact xuất ra (SVG / HTML / JSON).

---

## 8.5 Contract Testing & Gate Certification

### Testing Policy
- Test động dựa trên `GraphicsCatalog.get_required_assets()`, không hard-code số lượng asset cố định.
- Kiểm tra toàn diện:
  1. **Semantic Completeness**: 100% REQUIRED assets đầy đủ thành phần logic.
  2. **Safe Area & Zero Clipping**: Không phần tử nào vượt ranh giới an toàn.
  3. **Typography & Readability**: Mọi text element đạt `font-size >= 24px`.
  4. **Color Contrast**: Tương phản WCAG AA hợp lệ.
  5. **Timeline Bounds**: Khớp 100% với Phase 4 timeline, phát hiện kịp thời `GRAPHIC_TIMING_CONFLICT`.
  6. **Tri-Hash Stability**: Deterministic hoàn toàn qua nhiều lần chạy lặp lại.

### Gate Cuối Phase 8
```text
CV02_P8_GRAPHICS_VERIFIED
```
Chỉ **PASS** khi:
- 100% `REQUIRED` assets đạt coverage và render hợp lệ.
- Toàn bộ contract tests PASS 100%.
- Không có bất kỳ lỗi `GRAPHIC_TIMING_CONFLICT` nào.
- Toàn bộ asset và biên lai băm được lưu vào `artifacts/code_video/video_02/graphics/` và `artifacts/code_video/video_02/phase_08/`.

---

# PHASE 9 — RECORD VIDEO 02

Đây mới là phase quay thật.

Các Phase 0–8 xây hệ thống và chuẩn bị source.

---

# Pass 1 — Cold Open

Quay:

```text
python -m src.agent
```

Prompt:

```text
Giải thích recursion bằng một ví dụ đơn giản.
```

Hiện verified model response.

Sau đó:

```text
agent.run(...)
```

và:

```text
User → Agent → LLM → Answer
```

---

# Pass 2 — Repository

Quay:

```text
mkdir agentic-studio
cd agentic-studio
git init
```

Sau đó file tree xuất hiện.

---

# Pass 3 — Message

Replay code.

Highlight:

```python
@dataclass(frozen=True)
```

sau đó:

```python
role
content
```

---

# Pass 4 — AgentConfig

Replay.

Highlight lần lượt:

```text
name
system_prompt
model
temperature
```

---

# Pass 5 — LLMClient

Đây là take quan trọng.

Highlight:

```python
class LLMClient(Protocol):
```

Sau đó diagram:

```text
Agent
 ↓
LLMClient
 ├── Provider A
 ├── Provider B
 ├── Local Model
 └── Test Fake
```

---

# Pass 6 — FakeLLMClient

Replay implementation.

Overlay:

```text
Unit Test ≠ Real API
```

---

# Pass 7 — Agent

Quay constructor.

Sau đó `run()`.

Highlight:

```text
system
user
generate()
```

Kết thúc bằng:

```text
"Hello"
   ↓
Agent.run()
   ↓
[system, user]
   ↓
LLMClient.generate()
   ↓
"Answer"
```

---

# Pass 8 — Is This An Agent?

Không cần code animation nhiều.

Dùng architecture:

```text
Observe
Decide
Act
Observe
```

và làm mờ các phần chưa tồn tại.

---

# Pass 9 — Provider

Show infrastructure boundary:

```text
DOMAIN
Agent
Message
AgentConfig
LLMClient

─────────────

INFRASTRUCTURE
Provider SDK
HTTP
API Key
Response Mapping
```

---

# Pass 10 — API Key

Hiện:

```text
.env.example
```

và:

```text
.gitignore
```

Sau đó visual:

```text
api_key = "sk-..."
          ✕
```

Dữ liệu hiển thị chỉ là placeholder.

---

# Pass 11 — First Run

Replay:

```python
agent = Agent(...)
answer = agent.run(...)
print(answer)
```

Hiện golden provider output.

---

# Pass 12 — Testing

Replay test file.

Sau đó:

```bash
pytest
```

Target:

```text
2 passed
```

Verified từ Phase 3.

---

# Pass 13 — Not Yet

Checklist các chức năng chưa có.

---

# Pass 14 — Architecture Review

Full-screen architecture.

---

# Pass 15 — Git Milestone

Replay thật trong tutorial repository:

```bash
git add .
git commit -m "feat: build simple agent core"
git tag video-02
git tag v0.1
```

Sau đó:

```text
Agentic Studio
v0.1 — Simple Agent
```

---

# Pass 16 — Outro

Bắt đầu:

```text
User
 ↓
Agent
 ↓
LLM
 ↓
?
```

Sau đó:

```text
LLM ≠ Function Executor
```

và kết thúc:

```text
VIDEO 03
TOOL CALLING
```

---

# PHASE 10 — VISUAL ASSEMBLY

## Mục tiêu

Ghép toàn bộ verified takes vào timeline.

---

## FFmpeg

Repository hiện đã có FFmpeg/ffprobe process boundary với:

* argv list;
* bounded subprocess;
* timeout;
* version probing;
* receipts;
* assembly;
* verification.

Không gọi shell string tự do cho media assembly.

Nếu generic hóa module này:

```text
tools/windagent_tools/media/ffmpeg.py
```

phải giữ compatibility wrapper:

```text
production_engines/blender/ffmpeg.py
```

để không phá Blender.

---

## Timeline

```text
00:00.000
...
16:15.000
```

Không có audio track bắt buộc.

---

## Transition policy

Ưu tiên:

```text
hard cut
short dissolve
zoom
pan
highlight
```

Không dùng transition flashy trong tutorial code.

---

## Output

```text
final/
├── video_02_visual_master_1440p.mp4
├── video_02_visual_master_1080p.mp4
├── timeline.json
├── cue_sheet.csv
└── video_manifest.json
```

---

# PHASE 11 — FINAL VISUAL QC

## 11.1 Structural QC

Kiểm tra:

```text
duration = 975000 ms
19 scenes present
all required code scenes present
all required diagrams present
```

---

## 11.2 Code correctness

Code hiển thị cuối video phải tương đương golden repository.

Hash hoặc normalized AST được dùng để kiểm tra.

Không chỉ dùng OCR video.

---

## 11.3 Terminal correctness

Các command bắt buộc:

```text
git init
pytest
python -m src.agent
git add .
git commit
git tag video-02
git tag v0.1
```

---

## 11.4 Secret QC

Scan:

```text
frames
terminal receipts
source snippets
environment output
```

Nếu phát hiện secret:

```text
FINAL_VERDICT = REJECT
```

Không blur rồi tự PASS nếu secret đã lọt vào raw public artifact.

Raw take phải bị invalidated và quay lại.

---

## 11.5 Readability

Kiểm:

```text
font minimum
line clipping
terminal clipping
contrast
zoom
scroll speed
cursor visibility
```

---

## 11.6 Timing

Cho phép scene nội bộ lệch nhẹ, nhưng final timeline phải đúng:

```text
16:15.000
```

để việc lồng tiếng sau dễ dàng.

---

## Gate cuối

```text
CV02_VISUAL_MASTER_VERIFIED
```

---

# 6. Artifact protocol cho từng Phase

Mỗi phase tạo:

```text
artifacts/code_video/video_02/phase_<NN>/
├── input_manifest.json
├── implementation_manifest.json
├── test_receipt.json
├── architecture_report.json
├── phase_report.md
└── phase_verdict.json
```

Phase capture bổ sung:

```text
capture_receipt.json
frame_report.json
media_probe.json
```

Phase final:

```text
final_video_hash.json
timeline_report.json
secret_scan.json
visual_qc.json
```

---

# 7. Test strategy

## Unit

```text
CodeVideoPlan
Timeline
Action parser
Checkpoint manager
Replay controller
Terminal expectation
Secret scanner
```

## Integration

```text
sandbox + filesystem
sandbox + shell
sandbox + git
sandbox + pytest
renderer + replay
capture + renderer
FFmpeg + ffprobe
```

## Golden tests

Video 02 là golden fixture:

```text
tests/
└── code_video/
    └── fixtures/
        └── video_02/
```

---

# 8. Dependency graph

```text
Phase 0
   │
   ▼
Phase 1
   │
   ├───────────────┐
   ▼               │
Phase 2            │
   │               │
   ▼               │
Phase 3            │
   │               │
   ▼               │
Phase 4            │
   │               │
   ├──────────┬────┘
   ▼          ▼
Phase 5     Phase 8
   │
   ▼
Phase 6
   │
   ▼
Phase 7
   │
   └──────┬──── Phase 8
          ▼
        Phase 9
          │
          ▼
        Phase 10
          │
          ▼
        Phase 11
```

---

# 9. Những Phase có thể chạy song song

Sau khi Phase 4 freeze:

```text
Phase 5 — Code Studio UI
              │
              ├──── song song
              │
Phase 8 — Diagrams / title cards
```

Phase 3 build tutorial cũng có thể chuẩn bị graphics tĩnh sơ bộ, nhưng graphics chỉ được final sau Phase 4.

Capture không chạy song song với Replay Engine implementation.

---

# 10. Không làm trong Video 02

Không triển khai:

```text
TTS
voice cloning
voice alignment
background music
SFX
subtitle generation from audio
Tool Calling runtime
Memory
RAG
Planning
Multi-Agent
```

Audio là downstream manual stage.

---

# 11. Handoff để lồng tiếng sau

Final deliverable cho người dùng:

```text
video_02_visual_master_1440p.mp4
video_02_visual_master_1080p.mp4
video_02_cue_sheet.csv
video_02_timeline.json
script_with_timecodes.md
```

`cue_sheet.csv` ví dụ:

```text
00:00.000–00:25.000  Cold Open
00:25.000–00:50.000  Hook
00:50.000–01:25.000  Video 01 Recap
...
15:35.000–16:15.000  Outro
```

Nhờ vậy sau khi thu voice, chỉ cần đặt các đoạn voice đúng markers.

---

# 12. Definition of Done toàn chương trình

Chỉ được coi Video 02 hoàn thành khi:

* [x] WindAgent build được tutorial repo từ workspace trống.
* [x] `Message` tồn tại.
* [x] `AgentConfig` tồn tại.
* [x] `LLMClient` tồn tại.
* [x] `Agent` không phụ thuộc provider SDK.
* [x] Fake LLM hoạt động offline.
* [x] Unit tests pass không dùng API.
* [x] Provider implementation thật đã được integration-test.
* [x] Không secret nào xuất hiện trong source/video.
* [x] `pytest` output trong video là output verified.
* [x] Tutorial repository có commit milestone.
* [x] Tutorial repository có `video-02`.
* [x] Tutorial repository có `v0.1`.
* [x] Tool Calling không xuất hiện trong runtime Video 02.
* [x] Mọi code take sinh từ verified checkpoint.
* [x] 19 scene đúng timeline.
* [x] Các architecture diagram đúng script.
* [x] Final video dài đúng 16:15.
* [x] Final visual master không phụ thuộc audio.
* [x] 1440p master pass ffprobe.
* [x] 1080p delivery pass ffprobe.
* [x] Cue sheet được tạo.
* [x] Final artifact có SHA-256.
* [x] Có reproducibility receipt.
* [x] Gate cuối = `CV02_VISUAL_MASTER_VERIFIED`.


---

# 13. Thứ tự commit khuyến nghị

Không gom toàn bộ vào một commit.

```text
commit 1
feat(code-video): define visual production contracts

commit 2
feat(code-video): add isolated tutorial workspace

commit 3
test(code-video): add video 02 golden tutorial fixture

commit 4
feat(code-video): compile script into deterministic timeline

commit 5
feat(code-video-ui): add code studio renderer

commit 6
feat(code-video): add deterministic replay engine

commit 7
feat(code-video): add visual capture pipeline

commit 8
feat(code-video): add diagrams and visual overlays

commit 9
feat(code-video): assemble and verify visual master

commit 10
test(code-video): certify video 02 end-to-end
```

Không commit raw API secrets, `.env`, hoặc temporary recording cache.

---

# 14. Verdict mục tiêu

```text
VIDEO_02
=
SCRIPT
+
VERIFIED CODE
+
DETERMINISTIC REPLAY
+
CODE STUDIO
+
TERMINAL
+
DIAGRAMS
+
VISUAL CAPTURE
+
FFMPEG ASSEMBLY
+
VISUAL QC

AUDIO
=
MANUAL / LATER
```

Milestone cuối:

```text
CODE_VIDEO_VIDEO02_VERIFIED
```

với artifact chính:

```text
artifacts/code_video/video_02/final/
└── video_02_visual_master_1440p.mp4
```

Đây sẽ là golden E2E đầu tiên cho nhánh **Code Tutorial Production** của WindAgent.
