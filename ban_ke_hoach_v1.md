Từ 7 lựa chọn bạn vừa chốt, kiến trúc nên được xây theo hướng **AI điều phối một buổi quay đã được chuẩn bị trước**, không phải AI tự do viết code trong lúc quay.

Có một điểm cần chuẩn hóa trước: Google hiện có **Gemini 3 Flash** với model ID `gemini-3-flash-preview`, nhưng model này **không hỗ trợ Live API**. Model Live tương ứng hiện tại là **Gemini 3.1 Flash Live Preview**, ID `gemini-3.1-flash-live-preview`; nó hỗ trợ video input, text output và function calling. Vì vậy UI có thể hiển thị tên role là **“Gemini 3 Flash Live”**, nhưng routing production nên lấy model thực tế từ catalog của Provider và hiện tại resolve thành `gemini-3.1-flash-live-preview`. ([Google AI for Developers][1])

## 1. Kiến trúc mục tiêu

```text
EPISODES
   │
   ├── Script / Scenes / Demo flow
   │
   └── Recording Preparation
           │
           ├── Narration script
           ├── Prepared source code
           ├── Commands
           ├── Browser actions
           ├── Tool actions
           ├── Expected screen states
           └── Recovery instructions
                    │
                    ▼
          FROZEN LIVE EXECUTION PLAN
                    │
            hash + version + approval
                    │
                    ▼
              LIVE RECORD
                    │
        ┌───────────┴────────────┐
        │                        │
        ▼                        ▼
 GEMINI LIVE DIRECTOR       RECORDING ENGINE
        │                        │
 screen frames                   │
 current cue                     │
 tool results                    │
        │                        │
        ▼                        ▼
 Constrained Tool Gate     Windows Graphics Capture
        │                        │
        ├─ Code Playback         ▼
        ├─ Browser          D3D11 Frame Pipeline
        ├─ Terminal              │
        ├─ Tool Runner           ▼
        ├─ Scene Control       NVENC
        └─ Recording Ctrl        │
                                 ▼
                          FFmpeg / libav
                                 │
                                 ▼
                         MKV Segments
                                 │
                                 ▼
                       recording timeline
                                 │
                                 ▼
                      POST PRODUCTION
                                 │
                           TTS model khác
```

Điểm cốt lõi là:

> **Gemini không sáng tạo hành động mới trong lúc quay. Gemini quan sát màn hình, xác định trạng thái hiện tại và chọn hành động tiếp theo trong tập hành động đã được chuẩn bị và đóng băng trước khi quay.**

Đây là khác biệt quan trọng giữa một “computer-use agent tự do” và **production recording agent**.

Repo hiện tại rất phù hợp để chuyển theo hướng này. `LiveRecordPage` đã được tách thành page + panels nhưng `useLiveRecord.ts` hiện vẫn là mock state với scene, timer, bitrate, recording giả lập.   Tauri hiện cũng mới chủ yếu cung cấp system metrics/NVML chứ chưa có recording engine native.

---

# 2. Nguyên tắc kiến trúc bắt buộc

Tôi đề nghị đóng băng 6 nguyên tắc này ngay từ đầu.

### A. Episode là source of truth

Không để Live Record tự chứa kịch bản riêng.

Luồng phải là:

```text
Episode
→ Recording Preparation
→ LiveExecutionPlan revision
→ RecordingTake
```

Nếu Episode thay đổi sau khi plan đã được freeze:

```text
episode_revision != execution_plan.episode_revision
        ↓
RECORDING_PLAN_STALE
        ↓
không cho Start Recording
```

---

### B. Model chuẩn bị và model quay là hai role khác nhau

Model chuẩn bị trước:

```text
RECORDING_PREPARER
```

Gemini Live trong lúc quay:

```text
LIVE_DIRECTOR
```

Sau này TTS:

```text
NARRATION_TTS
```

Tất cả resolve qua **Provider + Model Routing** hiện có.

Frontend Providers đã có các primitive cho credential rotation, test connection, model sync, model testing và routing rules nên không cần tạo hệ thống API key riêng cho Live Record.

---

### C. Gemini không được gửi source code tùy ý

Không expose tool kiểu:

```text
write_file(path, content)
```

cho Gemini Live.

Thay bằng:

```text
execute_prepared_action(action_id)
```

Ví dụ:

```json
{
  "action_id": "code_017",
  "type": "CODE_PLAYBACK",
  "target_file": "src/agent.py",
  "payload_ref": "artifact://code/code_017",
  "before_hash": "...",
  "after_hash": "...",
  "typing_mode": "TYPE",
  "chars_per_second": 22
}
```

Gemini chỉ được nói:

```text
execute_prepared_action("code_017")
```

Không được truyền code vào function call.

Đây sẽ là lớp bảo vệ quan trọng nhất.

---

### D. Recording engine không phụ thuộc Gemini

Ngay cả Gemini mất kết nối:

```text
Gemini disconnect
       │
       ├── Tool execution → STOP
       ├── Scene advancement → STOP
       │
       └── Recorder → vẫn còn sống
```

Recording process không được nằm chung lifecycle với AI session.

---

### E. Recording 60 FPS ≠ gửi Gemini 60 FPS

Capture:

```text
1920x1080 @ 60 FPS
```

Recording pipeline giữ đủ 60 FPS.

Gemini observation nên chỉ:

```text
event-driven
hoặc
1–2 FPS
```

và có thể downscale:

```text
1280×720 JPEG/WebP
```

Đây là hai pipeline riêng:

```text
WGC
 │
 ├── Recording path → 60 FPS → NVENC
 │
 └── AI observation → sampler → 1–2 FPS → Gemini
```

---

### F. Audio để lại extension point nhưng chưa kích hoạt

Production engine có thể chuẩn bị abstraction cho:

```text
WASAPI
```

nhưng milestone đầu:

```text
capture_audio = false
```

Không nên dành Phase đầu để hoàn thiện audio pipeline khi audio sẽ được TTS tạo sau.

---

# 3. Phase 0 — Freeze baseline và contracts

## Mục tiêu

Biến Live Record hiện tại từ “mock UI cần sửa” thành một subsystem có boundary rõ.

### Việc cần làm

Xác định bốn subsystem:

```text
Live Recording Domain
Live Director
Native Recording Engine
Recording UI
```

Không nhét toàn bộ logic vào:

```text
useLiveRecord.ts
```

hoặc:

```text
src-tauri/src/lib.rs
```

`src-tauri/src/lib.rs` hiện đã chứa metrics/NVML; recording native không nên tiếp tục mở rộng file này thành god-file.

### Gate

```text
LIVE_RECORD_P0_ARCHITECTURE_FROZEN
```

Phải có:

* domain contract;
* state machine;
* IPC contract;
* Gemini tool contract;
* recording engine contract;
* security boundary.

---

# 4. Phase 1 — Recording Domain

Tạo domain model cho toàn bộ quá trình.

## Entity chính

```text
LiveExecutionPlan
RecordingScene
RecordingCue
PreparedAction
ExpectedVisualState

LiveRecordSession
RecordingTake
RecordingSegment
RecordingEvent
DirectorSession
```

### LiveExecutionPlan

Nên chứa tối thiểu:

```text
id
episode_id
episode_revision_id

preparation_revision
plan_hash

status
created_at
frozen_at

director_role
recording_profile

scenes[]
actions[]

source_workspace_hash
```

Status:

```text
DRAFT
PREPARED
VALIDATED
FROZEN
STALE
INVALID
```

Sau `FROZEN`, tuyệt đối không mutate.

---

# 5. Phase 2 — Episode → Recording Preparation Package

Đây là phần quan trọng nhất trước Gemini Live.

Trong Episode Workspace thêm:

```text
Prepare Recording
```

Model `RECORDING_PREPARER` đọc:

```text
screenplay
scene
demo objective
source code hiện tại
desired final code
browser workflow
commands
```

và tạo:

```text
Recording Preparation Package
```

## Một scene nên trở thành

```yaml
scene:
  id: scene-03
  title: Build Agent Core

  narration:
    source: episode_script

  actions:
    - action_id: code-001
      type: open_file

    - action_id: code-002
      type: code_playback

    - action_id: terminal-001
      type: run_command

    - action_id: verify-001
      type: visual_verify

    - action_id: browser-001
      type: browser_navigation

  expected_result:
    test: PASS
```

---

# 6. Prepared Source Code Bundle

Model chuẩn bị code trước cần xuất **exact payload**, không chỉ instruction.

Ví dụ:

```text
PreparedCodeBundle
 ├── step-001
 │    ├── file
 │    ├── before_hash
 │    ├── final_content
 │    ├── after_hash
 │    └── typing_profile
 │
 ├── step-002
 └── ...
```

Như vậy lúc quay Gemini không viết:

> “Hãy tạo class Agent ...”

mà chỉ quyết định:

```text
step-002 đã đến lúc chạy
```

Sau đó executor viết chính xác nội dung đã chuẩn bị.

---

# 7. Phase 3 — Tool Manifest

Đây là lớp biến “full agent” thành “controlled full agent”.

Gemini Live được nhận function declaration kiểu:

```text
advance_cue(cue_id)

execute_prepared_action(action_id)

verify_visual_state(state_id)

pause_recording()

resume_recording()

create_marker(marker_type)

retry_action(action_id)

request_operator(reason)
```

### Tuyệt đối không expose trực tiếp

```text
shell(command)
write_file(content)
open_url(url)
click(x, y)
powershell(script)
```

Thay vào đó:

```text
run_prepared_command("cmd-003")

open_prepared_url("browser-007")

perform_browser_action("browser-action-014")
```

Mọi argument thật nằm trong immutable plan.

---

# 8. Phase 4 — Google Live Provider

Google provider hiện tại dùng:

```text
generateContent
streamGenerateContent
```

qua HTTP.

Không nên sửa adapter đó thành Live adapter.

Tạo transport riêng:

```text
providers/
└── windagent_providers/
    └── google/
        ├── adapter.py
        └── live/
            ├── contracts.py
            ├── token_service.py
            ├── capability.py
            └── session.py
```

Conceptually:

```text
GoogleGeminiProviderAdapter
    → generateContent

GoogleGeminiLiveProvider
    → Live API
```

---

# 9. Model capability detection

Model routing cần biết:

```text
live_api
video_input
text_output
function_calling
```

Role:

```text
LIVE_DIRECTOR
```

chỉ được resolve model đáp ứng cả 4 capability.

Không hard-code:

```text
provider == google
```

trong Live Record UI.

UI chỉ yêu cầu:

```text
role = LIVE_DIRECTOR
```

Router quyết định provider/model.

---

# 10. Phase 5 — Ephemeral token bootstrap

Đây là architecture tôi khuyến nghị.

```text
Desktop
   │
   │ Start Live Director
   ▼
WindAgent API
   │
   ├── Resolve LIVE_DIRECTOR
   ├── Google provider?
   ├── credential configured?
   ├── live capability?
   └── issue ephemeral token
           │
           ▼
        Desktop
           │
           ▼
Google Live API
```

Google khuyến nghị ephemeral token cho client kết nối trực tiếp Live API; token ngắn hạn giúp không phải đưa API key lâu dài xuống desktop/browser và giảm thêm một network proxy hop. ([Google AI for Developers][2])

API key thật vẫn nằm trong:

```text
Providers
```

---

## Endpoint đề xuất

```text
POST /api/v3/live-record/sessions/bootstrap
```

Request:

```json
{
  "episode_id": "...",
  "execution_plan_id": "..."
}
```

Response:

```json
{
  "session_id": "...",
  "provider_id": "...",
  "model_id": "gemini-3.1-flash-live-preview",
  "token": "...",
  "expires_at": "...",
  "execution_plan_hash": "..."
}
```

Token:

* không persist;
* không log;
* không trả lại qua GET;
* one-session use;
* constrain vào exact model/config.

---

# 11. Phase 6 — Gemini Live Director Client

Tôi khuyến nghị Live WebSocket client nằm phía **desktop TypeScript**, không nằm trong Python API.

Lý do:

```text
Desktop → Gemini
```

ngắn hơn:

```text
Desktop → WindAgent API → Gemini
```

và Google cũng thiết kế ephemeral token cho kiểu kết nối trực tiếp này. ([Google AI for Developers][2])

Component mới:

```text
frontend/app/src/features/live-record/live-director/
```

gồm:

```text
LiveDirectorClient
LiveDirectorSession
FrameSampler
ToolCallDispatcher
CueContextBuilder
SessionResumptionManager
```

---

# 12. Context Gemini nhận

Không dump toàn bộ Episode mỗi frame.

Session start:

```text
system instruction
+
frozen plan summary
+
allowed tools
+
current scene
```

Sau đó mỗi cycle:

```text
Current cue
Current expected state
Latest screen frame
Last tool result
Elapsed scene time
```

Gemini làm:

```text
Observe
  ↓
Compare with expected state
  ↓
Select approved action
  ↓
Execute
  ↓
Observe
```

Đúng nghĩa một agent loop nhưng bị giới hạn bởi plan.

---

# 13. Phase 7 — Code Playback Engine

Đây là subsystem riêng.

Ví dụ một prepared action:

```text
CODE_PLAYBACK
```

Engine:

```text
1. Verify active app = VS Code
2. Verify expected file
3. Verify before_hash
4. Position cursor
5. Type prepared payload
6. Save
7. Read file
8. Verify after_hash
9. Return success/failure
```

Gemini chỉ nhận:

```json
{
  "action_id": "code-017",
  "status": "SUCCESS"
}
```

Không cần nhìn nội dung source code được generate.

---

## Hai playback mode

Nên hỗ trợ:

```text
TYPE
PASTE
```

`TYPE`:

```text
15–40 chars/s
```

phù hợp quay tutorial.

`PASTE`:

dùng đoạn dài không cần diễn typing.

Có thể thêm:

```text
pause_after_line
pause_after_block
highlight_range
scroll_to_anchor
```

để footage nhìn tự nhiên.

---

# 14. Browser và Tool Executor

Browser subsystem hiện đã tồn tại trong repo, vì vậy Live Record nên sử dụng lại execution layer thay vì tạo browser automation riêng.

Recording plan chỉ lưu:

```text
browser-action-001
browser-action-002
...
```

Ví dụ:

```yaml
browser-action-002:
  operation: CLICK
  target:
    semantic_text: "API Keys"
  expected_after:
    url_contains: "/apikey"
```

Gemini:

```text
run_prepared_browser_action("browser-action-002")
```

Sau đó screenshot tiếp theo dùng để verify.

---

# 15. Phase 8 — Native Production Recording Engine

Đây là phần lớn nhất của project.

Tôi đề nghị **không implement recording engine trực tiếp trong Tauri `lib.rs`**.

Hiện Tauri Rust mới khá nhỏ và dependency chỉ gồm Tauri, serde, sysinfo, NVML...

Tạo native crate riêng:

```text
apps/desktop/native/
└── recording-engine/
    ├── Cargo.toml
    └── src/
        ├── main.rs
        ├── capture/
        ├── encoder/
        ├── muxer/
        ├── segment/
        ├── preview/
        ├── telemetry/
        └── ipc/
```

Tauri trở thành:

```text
control plane
```

Recording engine:

```text
data plane
```

---

# 16. Capture pipeline

```text
Windows Graphics Capture
          │
          ▼
       D3D11
          │
          ├─────────────► Preview Sampler
          │                   │
          │                   ▼
          │               Gemini frames
          │
          ▼
       NVENC
          │
          ▼
     H.264 / HEVC
          │
          ▼
     libavformat
          │
          ▼
         MKV
```

Quan trọng:

> Không đưa raw 1080p60 frames qua React/Tauri IPC.

Tauri chỉ nhận:

```text
preview frames
metrics
events
```

Encoding chạy hoàn toàn native.

---

# 17. MKV segmented recording

Tôi chọn MKV thay vì MP4 trong lúc record.

Ví dụ:

```text
take_0001/
 ├── segment_0001.mkv
 ├── segment_0002.mkv
 ├── segment_0003.mkv
 ├── timeline.jsonl
 └── manifest.json
```

Segment mặc định:

```text
5 hoặc 10 phút
```

Ưu điểm:

* crash recovery tốt hơn;
* không mất toàn bộ recording nếu process chết;
* dễ cắt take;
* dễ remux sau cùng.

Kết thúc:

```text
MKV segments
   ↓
validate
   ↓
concat/remux
   ↓
final.mkv / final.mp4
```

---

# 18. WASAPI

Chuẩn bị architecture:

```text
AudioCapturePort
```

implementation sau:

```text
WasapiCapture
```

Nhưng P0/P1:

```text
audio_enabled = false
```

Không block feature Live Record vì audio.

---

# 19. Phase 9 — Tauri IPC

Thay vì hàng trăm command, dùng API nhỏ.

Ví dụ:

```text
recorder_prepare
recorder_start
recorder_pause
recorder_resume
recorder_stop
recorder_get_status
recorder_create_marker
```

Event:

```text
recorder://status
recorder://segment
recorder://preview
recorder://warning
recorder://error
```

Frontend không được thao tác NVENC/libav trực tiếp.

---

# 20. Phase 10 — Refactor Live Record UI

UI hiện tại về mặt hình thức đã gần với control room cần thiết, nên không cần redesign lớn.

Cần thay mock bằng real state.

## Panel preview

Hiển thị:

```text
real captured screen
+
REC
+
current cue
+
Gemini state
```

---

## Scene List

Từ:

```text
DEFAULT_SCENES
```

chuyển thành:

```text
LiveExecutionPlan.scenes
```

---

## Teleprompter

Không còn hard-code script.

Nguồn:

```text
Episode → Recording Scene narration
```

---

## Recording Status

Real telemetry:

```text
elapsed
frames captured
frames encoded
frames dropped
current segment
disk write speed
NVENC status
bitrate
```

---

# 21. Thêm Director panel

Tôi sẽ thay phần mock “Swarm” trong preview bằng trạng thái thực:

```text
LIVE DIRECTOR

Gemini 3 Flash Live
Connected

Scene 3 / 12
Cue 8 / 21

Observing screen...
Expected:
Tests should pass

Last action:
run_prepared_command(cmd-008)

Result:
PASS
```

Không cần hiển thị chain-of-thought.

Chỉ hiển thị:

```text
Observation
Decision
Action
Result
```

ở mức operational.

---

# 22. State machine tổng thể

```text
IDLE
 ↓
PREPARING
 ↓
PREFLIGHT
 ↓
READY
 ↓
RECORDING
 ├─ PAUSED
 ├─ DIRECTOR_DEGRADED
 └─ RECOVERING
 ↓
FINALIZING
 ↓
COMPLETED
```

Fail closed nếu:

```text
plan stale
workspace hash mismatch
provider unavailable
wrong model capability
record path invalid
NVENC unavailable
disk insufficient
prepared action tampered
```

---

# 23. Preflight trước khi nút Start được enable

Nút:

```text
Bắt đầu ghi
```

chỉ enable nếu:

```text
Episode revision OK
Execution plan FROZEN
Source workspace hash OK
All prepared artifacts present
LIVE_DIRECTOR route resolves
Provider credential valid
Gemini Live connectivity OK
Recorder sidecar healthy
WGC available
NVENC available
Disk space sufficient
Output path writable
```

Kết quả:

```text
READY
```

hoặc:

```text
BLOCKED
```

kèm blocker cụ thể.

---

# 24. Session recovery

Gemini Live phải có session resumption.

Google Live có support `sessionResumption`; ephemeral token mặc định cũng có giới hạn lifetime nên session dài phải được thiết kế reconnect/resume từ đầu. ([Google AI for Developers][2])

Flow:

```text
Live socket lost
     ↓
freeze tool executor
     ↓
retain current cue
     ↓
resume session
     ↓
send latest state + screenshot
     ↓
continue
```

Gemini không được replay action đã success.

Mọi action cần:

```text
execution_id
idempotency_key
```

---

# 25. Recording timeline — cực kỳ quan trọng cho TTS sau này

Mỗi event ghi vào:

```text
timeline.jsonl
```

Ví dụ:

```json
{"t":12.410,"type":"SCENE_START","scene":"scene-03"}
{"t":18.122,"type":"ACTION_START","action":"code-017"}
{"t":34.554,"type":"ACTION_SUCCESS","action":"code-017"}
{"t":35.090,"type":"NARRATION_CUE","cue":"voice-009"}
```

Sau này TTS model chỉ cần:

```text
Episode narration
+
timeline
```

để tạo:

```text
voice-001.wav
voice-002.wav
...
```

và align chính xác với video.

Đây là lý do dù chưa làm TTS, **timeline phải hoàn thiện ngay ở Live Record P1**.

---

# 26. Phase 11 — Failure policy

Ba loại lỗi.

### Recoverable

```text
Gemini network disconnect
Browser page slow
Visual verification timeout
Tool command timeout
```

→ retry/resume.

### Operator required

```text
UI changed
VS Code unexpected dialog
Website requires login
```

→ pause + yêu cầu người dùng.

### Fatal

```text
disk full
NVENC failure
capture device destroyed
plan tampered
workspace hash mismatch
```

→ stop/finalize current segment.

---

# 27. Acceptance gates

Tôi sẽ chia feature này thành các gate.

| Gate                   | Điều kiện                                   |
| ---------------------- | ------------------------------------------- |
| `LR_P0_ARCHITECTURE`   | contracts + state machine frozen            |
| `LR_P1_EPISODE_PLAN`   | Episode → frozen execution plan             |
| `LR_P2_PROVIDER_LIVE`  | Provider routing → Gemini Live              |
| `LR_P3_DIRECTOR`       | screen → Gemini → constrained function call |
| `LR_P4_CODE_PLAYBACK`  | prepared code được viết lại chính xác       |
| `LR_P5_BROWSER_TOOLS`  | browser/tool actions từ plan hoạt động      |
| `LR_P6_NATIVE_CAPTURE` | WGC capture thật                            |
| `LR_P7_NVENC`          | 1080p60 → NVENC                             |
| `LR_P8_SEGMENTED_MKV`  | MKV segmentation + recovery                 |
| `LR_P9_UI`             | toàn bộ mock telemetry được thay            |
| `LR_P10_E2E`           | Episode → quay hoàn chỉnh                   |
| `LR_P11_PRODUCTION`    | stress/recovery/performance PASS            |

---

# 28. E2E bắt buộc

Kịch bản acceptance nên có một Episode test khoảng 5–10 phút:

```text
Scene 1
Open VS Code

Scene 2
Open prepared file

Scene 3
Type prepared code

Scene 4
Run pytest

Scene 5
Observe PASS

Scene 6
Open browser

Scene 7
Navigate prepared page

Scene 8
Run prepared tool

Scene 9
Return VS Code

Scene 10
Finish recording
```

Sau run phải chứng minh:

```text
0 unapproved actions

all source hashes correct

all commands came from plan

all browser actions came from plan

recording playable

all MKV segments valid

timeline complete

Episode/plan/take lineage correct
```

---

# 29. Performance gate

Với 1080p60 nên đặt baseline:

```text
Dropped frames < 0.1%

Recording engine:
no sustained CPU saturation

NVENC:
hardware encoder confirmed

Preview:
< 200 ms perceived delay

Gemini sampling:
1–2 FPS maximum normally

MKV:
every segment independently playable

30–60 minute soak:
PASS
```

Không nên benchmark Gemini latency chung với recorder latency. Hai subsystem phải đo riêng.

---

# 30. Thứ tự triển khai tôi khuyến nghị

```text
Phase 0
Architecture freeze
     ↓
Phase 1
Domain + DB
     ↓
Phase 2
Episode → Prepared Recording Plan
     ↓
Phase 3
Constrained Tool Manifest
     ↓
Phase 4
Provider LIVE_DIRECTOR capability
     ↓
Phase 5
Ephemeral token + Gemini Live
     ↓
Phase 6
Screen → Gemini → function calling
     ↓
Phase 7
Code / Browser / Tool Playback
     ↓
Phase 8
Native WGC capture
     ↓
Phase 9
NVENC + libav + segmented MKV
     ↓
Phase 10
Live Record UI integration
     ↓
Phase 11
Recovery + E2E + soak
     ↓
PRODUCTION READY
```

## Điểm kiến trúc quan trọng nhất

Tôi sẽ **không xây Gemini thành coder trong lúc quay**.

Vai trò của Gemini Live nên là:

```text
          GEMINI LIVE
              │
       Observe Screen
              │
       Understand State
              │
    Compare With Script/Cue
              │
       Choose Next Step
              │
   ┌──────────┴──────────┐
   │                     │
Prepared Action       Wait / Retry
   │
   ▼
Deterministic Executor
```

Nhờ đó buổi quay vẫn mang cảm giác một AI agent đang tự vận hành VS Code, Browser và tools, nhưng phía dưới nó có **một execution package đã chuẩn bị, versioned, hashed và kiểm soát hoàn toàn**. Đây là cách phù hợp hơn nhiều cho production video vì tránh tình trạng Gemini bất ngờ sửa sai code, đổi flow, mở sai trang hoặc phá take đang quay.

Với repo hiện tại, tôi đánh giá phần cần làm lớn nhất không phải UI mà là **Recording Preparation Package + constrained Live Director + Rust recording sidecar**. UI Live Record hiện có thể giữ khoảng 70–80% cấu trúc visual và thay dần mock state bằng subsystem thật.

[1]: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-live-preview?utm_source=chatgpt.com "Gemini 3.1 Flash live preview  |  Gemini API  |  Google AI for Developers"
[2]: https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens?hl=vi&utm_source=chatgpt.com "Mã thông báo tạm thời  |  Gemini API  |  Google AI for Developers"
