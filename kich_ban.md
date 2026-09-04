# WINDAGENT V2 — VIDEO PRODUCTION ACCEPTANCE TEST 01

## Chủ đề

**01 — LLM thực sự làm gì: dự đoán token, không tự hành động**

Roadmap source:

* Month 1: Agent Foundations & Harness
* Week 1: Mô hình tư duy về Agent
* Lesson 01
* Track: UNDERSTAND
* Focus: MODEL

## 1. Mục tiêu

Kiểm tra bằng một video thực tế xem WindAgent V2 hiện tại đã có khả năng đi từ:

**Topic → Episode → Research/Content → Screenplay → Storyboard → Production Plan → Recording → Media Assembly → Render → Quality → Final Video**

hay chưa.

Đây không phải test xem API có tồn tại.

Đây cũng không phải test xem unit test có pass.

Điều kiện thành công cuối cùng là:

> WindAgent nhận một chủ đề từ roadmap và tạo được một video có thể xem được từ đầu đến cuối, với toàn bộ artifact và evidence truy vết được.

---

# 2. Nguyên tắc thực hiện

## 2.1 First-pass phải chạy trên code hiện tại

Trong lần chạy đầu:

* không bổ sung feature;
* không sửa workflow chỉ để làm test pass;
* không mock recording;
* không thay video output bằng placeholder;
* không tạo thủ công artifact mà hệ thống tuyên bố có thể tự tạo;
* không bỏ qua stage bị fail.

Nếu stage nào không hoạt động:

1. ghi nhận failure;
2. thu evidence;
3. xác định nguyên nhân;
4. đánh dấu BLOCKED;
5. sau đó mới bước sang repair pass.

Mục tiêu là xác định **khả năng hiện tại**, không phải chứng minh bằng mọi giá rằng hệ thống đã hoàn thiện.

---

# 3. Acceptance target

Video thử nghiệm nên giữ phạm vi nhỏ để tập trung vào pipeline.

## Video target

**Title**

`LLM thực sự làm gì? Nó chỉ dự đoán token — không tự hành động`

**Target duration**

5–8 phút.

**Target video**

* 1920×1080
* 60 FPS nếu recording engine đã hỗ trợ production target này
* H.264/NVENC hoặc codec production hiện tại
* segmented MKV trong quá trình record nếu engine sử dụng thiết kế này
* final artifact: MP4
* audio có thể là narration/TTS hiện tại của hệ thống; nếu audio subsystem chưa hoàn thiện, phải ghi rõ đây là capability gap, không được giả lập thành PASS.

## Nội dung tối thiểu

Video phải giúp người xem hiểu được bốn ý:

1. LLM nhận context dưới dạng token.
2. LLM tính xác suất cho token tiếp theo.
3. Quá trình này lặp lại để tạo response.
4. Việc **thực hiện hành động** thuộc về harness/runtime/tool execution chứ bản thân LLM không tự click chuột, tạo file hay gọi API.

---

# 4. Story blueprint dùng cho test

Không cần video quá cầu kỳ. Tuy nhiên phải đủ cảnh để kiểm tra storyboard và production workflow.

## Scene 01 — Hook

**Mục tiêu**

Phá hiểu lầm:

> “ChatGPT tạo file, mở browser, chạy code nên LLM chắc có thể tự hành động.”

Visual:

```text
USER
  ↓
LLM
  ↓
"Create file hello.py"
```

Sau đó xuất hiện dấu hỏi:

```text
LLM → ??? → FILE SYSTEM
```

Narrative:

“Có một nhầm lẫn rất phổ biến: chúng ta thấy AI chạy code, mở trình duyệt hay tạo file rồi nghĩ rằng LLM tự thực hiện những hành động đó.”

---

## Scene 02 — Tokenization

Demo một câu đơn giản:

```text
AI agents are useful
```

hiển thị thành các token.

Mục tiêu không phải dạy tokenizer chuyên sâu mà chứng minh:

```text
Text
 ↓
Tokens
 ↓
Model
```

---

## Scene 03 — Next-token prediction

Visual chính:

```text
Input:
"The capital of France is"

             LLM
              │
              ▼

Token probability

Paris     0.91
Lyon      0.03
France    0.02
London    0.01
...
```

Sau đó chọn:

```text
Paris
```

---

## Scene 04 — Autoregressive generation

Animation:

```text
Token 1
   ↓
Token 2
   ↓
Token 3
   ↓
Token 4
   ↓
Response
```

Giải thích:

```text
P(token[n] | token[1...n-1])
```

Không cần đi sâu toán học.

---

## Scene 05 — Thí nghiệm quan trọng nhất

Yêu cầu model:

```text
Create a file named hello.txt on my desktop.
```

### Case A — Model only

Model trả về hướng dẫn hoặc text.

Desktop:

```text
hello.txt DOES NOT EXIST
```

### Case B — Model + Harness + Tool

```text
User
 ↓
Harness
 ↓
LLM
 ↓
Tool Call
 ↓
Harness validates
 ↓
Filesystem Tool
 ↓
hello.txt
```

Đây là demo cốt lõi của video.

---

## Scene 06 — LLM vs Agent

Visual:

```text
LLM
│
├─ predicts tokens
└─ produces output
```

so với:

```text
Agent
│
├─ Model
├─ Harness
├─ Tools
├─ State
└─ Environment
```

Kết luận:

> LLM tạo quyết định hoặc đề xuất hành động. Hệ thống bao quanh nó mới biến output đó thành hành động thực tế.

---

## Scene 07 — Outro

Teaser sang các bài sau:

```text
LLM
 +
Harness
 +
Tools
 +
Environment

        ↓

      AGENT
```

---

# 5. PHASE 0 — Freeze baseline

Trước khi tạo video:

Thu thập:

```text
branch
HEAD SHA
git status
Python version
Node version
PostgreSQL version
FFmpeg version
GPU
NVIDIA driver
NVENC availability
Windows version
desktop app version
```

Tạo execution ID:

```text
VIDEO_ACCEPTANCE_01_<timestamp>
```

Khuyến nghị lưu evidence tại:

```text
artifacts/
└── video_acceptance/
    └── lesson_01/
```

Không được thay đổi source code trong baseline pass.

### Gate P0

PASS khi:

* repository state xác định được;
* backend start được;
* worker start được;
* PostgreSQL healthy;
* desktop start được;
* frontend/backend kết nối được.

Nếu một service bắt buộc không start:

`BLOCKED_INFRASTRUCTURE`

---

# 6. PHASE 1 — Tạo Project và Episode thật

Tạo project:

```text
Khoa Gió AI
Season 01 — Agentic Systems
```

Tạo episode:

```text
Episode: 01

Title:
LLM thực sự làm gì: dự đoán token, không tự hành động
```

Metadata:

```text
month: 1
week: 1
lesson: 1
track: understand
focus: model
target_duration: 5-8 minutes
```

### Kiểm tra

* Project persist vào PostgreSQL.
* Episode persist.
* Reload UI vẫn còn.
* API trả đúng object.
* Không có dữ liệu demo/hardcoded.

### Gate P1

Episode phải có ID thật và database state thật.

---

# 7. PHASE 2 — Content / Script generation

Cho Studio pipeline tạo nội dung bài.

Hệ thống cần tạo tối thiểu:

```text
lesson objective
key claims
outline
scene structure
screenplay
```

## Kiểm tra factual structure

Screenplay phải phân biệt chính xác:

```text
LLM
≠
Agent
```

và:

```text
Prediction
≠
Execution
```

Không cho phép screenplay nói theo kiểu:

> LLM tự truy cập filesystem.

Hoặc:

> LLM tự chạy browser.

Ý đúng phải là:

```text
LLM generates output/tool request
          ↓
Harness interprets it
          ↓
Policy validates it
          ↓
Runtime executes tool
```

### Gate P2

PASS khi tạo được screenplay hoàn chỉnh cho toàn bộ video.

---

# 8. PHASE 3 — Review và Lock screenplay

Chạy review pipeline.

Kiểm tra tối thiểu:

### Accuracy

* token prediction được giải thích đúng;
* không đồng nhất model với agent;
* không phóng đại autonomy.

### Pedagogy

Người mới phải hiểu được:

```text
Model → generates
Harness → controls
Tool → acts
```

### Structure

Video phải có:

```text
Hook
↓
Concept
↓
Mechanism
↓
Experiment
↓
Agent comparison
↓
Conclusion
```

Sau review:

* revision nếu cần;
* approval;
* Lock screenplay.

Phải sinh `LockedScreenplayReceipt` hoặc artifact tương đương của Studio.

### Gate P3 — HARD GATE

Không được bắt đầu production nếu screenplay chưa LOCK.

---

# 9. PHASE 4 — Storyboard generation

Từ locked screenplay tạo storyboard.

Mỗi scene cần có ít nhất:

```text
scene_id
duration
visual
narration
on_screen_text
action
asset_requirement
recording_requirement
transition
```

Ví dụ:

```text
SCENE-05

duration: 50s

visual:
VS Code + Desktop

action:
Ask model to create hello.txt without tool access.

expected:
No file created.

then:
Enable filesystem tool through harness.

expected:
hello.txt created.
```

### Gate P4

Không được có:

* scene thiếu visual;
* scene thiếu narration;
* scene không biết dùng asset nào;
* scene yêu cầu recording nhưng không có recording action.

---

# 10. PHASE 5 — Production asset preparation

Production Engine chuyển storyboard thành production package.

Phân loại asset:

```text
STATIC
DIAGRAM
CODE
SCREEN_RECORD
TITLE_CARD
TRANSITION
AUDIO
```

Ví dụ:

```text
SCENE 02 → diagram/token animation
SCENE 03 → probability graphic
SCENE 04 → autoregressive animation
SCENE 05 → live screen recording
SCENE 06 → architecture diagram
```

Tạo manifest:

```text
production_manifest.json
```

hoặc artifact domain tương đương.

Mỗi asset phải có:

```text
asset_id
scene_id
type
source
status
version
checksum
```

### Gate P5

100% scene có production asset hoặc recording instruction tương ứng.

---

# 11. PHASE 6 — Recording plan

Đây là bước bắt đầu kiểm tra `Live Record`.

Tạo recording session dựa trên storyboard.

Ví dụ:

```text
SESSION-01

Take 01:
Hook presentation

Take 02:
Token demo

Take 03:
VS Code experiment

Take 04:
Harness tool execution
```

Cues phải được tạo từ screenplay/storyboard chứ không nhập thủ công lại toàn bộ.

Kiểm tra liên kết:

```text
Episode
 ↓
Locked Screenplay
 ↓
Storyboard
 ↓
Production Plan
 ↓
Recording Plan
 ↓
Session
 ↓
Take
```

### Gate P6

Không được tồn tại orphan recording session.

---

# 12. PHASE 7 — Recording preflight

Đây là HARD GATE quan trọng.

Desktop sidecar phải tự kiểm tra:

```text
WGC
D3D11
GPU
NVENC
FFmpeg/libav
capture target
output directory
disk space
resolution
FPS
```

Nếu hệ thống hỗ trợ audio:

```text
WASAPI
mic
system audio
audio format
```

Log phải trả về capability thật.

Ví dụ:

```text
WGC                PASS
D3D11              PASS
NVENC              PASS
FFmpeg             PASS
1920x1080          PASS
60 FPS             PASS
Disk               PASS
Audio              PASS/WARN
```

Không được hardcode `available=true`.

### Gate P7

Nếu WGC hoặc encoder không khả dụng:

`BLOCKED_RECORDING_ENGINE`

Không được chuyển thành PASS bằng mock.

---

# 13. PHASE 8 — Thực hiện quay thật

Start recording từ WindAgent.

Thực hiện ít nhất một take có interaction thật:

```text
Open VS Code
↓
send prompt
↓
show model-only behavior
↓
enable/use harness tool
↓
create file
↓
verify file
```

Recording engine phải:

* tạo file thật;
* cập nhật session state;
* cập nhật take state;
* ghi duration;
* ghi artifact path;
* không mất liên kết với Episode.

Test:

```text
START
 ↓
RECORDING
 ↓
PAUSE/CONTINUE nếu hỗ trợ
 ↓
STOP
 ↓
TAKE_COMPLETED
```

### Negative test nhỏ

Trong một take thử:

```text
Start
↓
Cancel
```

Hệ thống phải cleanup đúng.

### Gate P8 — HARD GATE

Phải tồn tại ít nhất một video recording artifact thực sự phát được.

---

# 14. PHASE 9 — Media ingest

Sau khi recording kết thúc:

Production phải ingest take.

Kiểm tra:

```text
recording artifact
       ↓
asset registry
       ↓
production asset
       ↓
scene
       ↓
episode
```

Không được xử lý video chỉ bằng file path bên ngoài domain state.

Kiểm tra:

* metadata;
* duration;
* resolution;
* checksum;
* source take;
* scene association.

---

# 15. PHASE 10 — Timeline / EDL assembly

Production Engine tạo timeline hoàn chỉnh.

Ví dụ:

```text
TITLE
  ↓
SCENE 01
  ↓
SCENE 02
  ↓
SCENE 03
  ↓
SCENE 04
  ↓
SCENE 05
  ↓
SCENE 06
  ↓
OUTRO
```

Timeline cần hỗ trợ ít nhất:

```text
video track
graphics track
audio/narration track
```

nếu engine hiện tại đã định nghĩa multi-track EDL.

Kiểm tra:

* scene order đúng;
* không overlap ngoài ý muốn;
* không có gap ngoài ý muốn;
* asset version chính xác;
* duration hợp lệ.

### Gate P10

Timeline phải được tạo từ domain artifacts, không phải ghép tay bên ngoài WindAgent.

---

# 16. PHASE 11 — Final render

Render final video.

Target:

```text
lesson_01_llm_token_prediction.mp4
```

Kiểm tra bằng media probe:

```text
container
codec
width
height
fps
duration
audio streams
video streams
bitrate
```

Expected:

```text
video_stream >= 1

resolution = 1920x1080
fps ≈ configured FPS
duration > 0
decode_errors = 0
```

Nếu audio là requirement đã implement:

```text
audio_stream >= 1
```

### HARD GATE P11

File cuối phải:

* tồn tại;
* size > 0;
* mở được;
* seek được;
* decode hết video;
* không corrupted.

Nếu WindAgent chỉ tạo timeline nhưng không render được:

`PARTIAL — PRODUCTION_PIPELINE_NO_FINAL_RENDER`

---

# 17. PHASE 12 — Content Quality Gate

Chạy Quality module trên final artifact và production metadata.

Đánh giá:

### Technical quality

```text
resolution
FPS
duration
missing frames
corruption
audio presence
A/V sync
```

### Content quality

```text
Accuracy
Clarity
Structure
Pacing
Visual relevance
Narration consistency
```

### Required semantic checks

Video phải truyền đạt được:

```text
LLM predicts tokens.
```

và:

```text
LLM does not directly execute external actions.
```

và:

```text
Harness/runtime turns model outputs into controlled actions.
```

---

# 18. PHASE 13 — Traceability test

Chọn ngẫu nhiên một đoạn video cuối.

Ví dụ đoạn:

```text
“LLM không tự tạo file”
```

Phải truy ngược được:

```text
Final Video
    ↓
Timeline Clip
    ↓
Production Asset
    ↓
Take
    ↓
Recording Cue
    ↓
Storyboard Scene
    ↓
Locked Screenplay
    ↓
Episode 01
    ↓
Roadmap Lesson 01
```

Nếu không trace được:

`FAIL_PROVENANCE`

Đây là tiêu chí quan trọng với kiến trúc WindAgent.

---

# 19. PHASE 14 — Recovery test

Nếu baseline đã tạo được video, chạy một failure injection nhỏ.

Trong lúc recording hoặc production:

```text
kill worker
```

sau đó restart.

Kiểm tra:

```text
state persisted?
job recovered?
duplicate artifact?
duplicate render?
take corrupted?
```

Không cần chaos test toàn hệ thống ở Video 01.

Chỉ cần chứng minh một production task không mất hoàn toàn khi worker restart.

---

# 20. PHASE 15 — Repeatability test

Chạy production Video 01 lần thứ hai từ cùng locked screenplay.

Không yêu cầu pixel-identical.

Nhưng phải đảm bảo:

```text
scene count      same
timeline order   same
required assets  same
semantic content same
```

Không được:

* mất scene;
* đổi topic;
* tạo artifact orphan;
* ghi đè bản render trước trái phép.

---

# 21. Acceptance matrix

| Gate | Requirement                   | Severity |
| ---- | ----------------------------- | -------- |
| P0   | Infrastructure operational    | HARD     |
| P1   | Project/Episode persisted     | HARD     |
| P2   | Full screenplay generated     | HARD     |
| P3   | Screenplay locked             | HARD     |
| P4   | Storyboard complete           | HARD     |
| P5   | Production assets resolved    | HARD     |
| P6   | Recording plan generated      | HARD     |
| P7   | WGC/encoder preflight real    | HARD     |
| P8   | Real recording produced       | HARD     |
| P9   | Take ingested into Production | HARD     |
| P10  | Timeline/EDL assembled        | HARD     |
| P11  | Final video rendered          | HARD     |
| P12  | Technical/content quality     | HARD     |
| P13  | Full provenance trace         | MEDIUM   |
| P14  | Basic crash recovery          | MEDIUM   |
| P15  | Production repeatable         | MEDIUM   |

---

# 22. Quy tắc verdict cuối cùng

## `VIDEO_PRODUCTION_READY`

Chỉ được sử dụng nếu:

```text
P0-P13 PASS
```

và final MP4 thực sự được tạo bởi WindAgent.

---

## `VIDEO_PRODUCTION_READY_WITH_LIMITATIONS`

Dùng khi:

```text
P0-P13 PASS
```

nhưng tồn tại limitation không phá pipeline, ví dụ:

* chưa có TTS production;
* chưa có B-roll automation;
* chưa có auto subtitle;
* một số asset phải chuẩn bị trước.

Phải liệt kê chính xác limitation.

---

## `VIDEO_PRODUCTION_PARTIAL`

Dùng khi hệ thống có thể:

```text
Screenplay
+
Storyboard
+
Production Plan
+
Recording
```

nhưng không thể tự:

```text
Assemble
+
Render
```

hoặc ngược lại.

---

## `VIDEO_PRODUCTION_BLOCKED`

Chỉ cần một trong các HARD GATE cốt lõi fail:

```text
P3
P7
P8
P10
P11
```

là không được tuyên bố WindAgent đã có khả năng sản xuất video end-to-end.

---

# 23. Evidence bắt buộc

Sau test phải giữ lại:

```text
REPORT.md

baseline.txt

episode.json
screenplay.json
screenplay_lock.json
storyboard.json

production_manifest.json
recording_plan.json
recording_session.json

takes/
  take_01.mkv
  ...

timeline/
  edl.json

renders/
  lesson_01_llm_token_prediction.mp4

media_probe.json

quality_report.json

logs/
  api.log
  worker.log
  desktop.log
  production.log

screenshots/

failures/
```

Tên file thực tế có thể dùng schema hiện tại của WindAgent; không cần ép codebase đổi theo tên phía trên.

---

# 24. Báo cáo cuối cùng

Không viết kiểu:

```text
Video production works.
```

Báo cáo phải có dạng:

```text
VIDEO PRODUCTION ACCEPTANCE REPORT

Baseline:
<sha>

Topic:
01 — LLM thực sự làm gì:
dự đoán token, không tự hành động

FINAL VERDICT:
VIDEO_PRODUCTION_READY
or
VIDEO_PRODUCTION_READY_WITH_LIMITATIONS
or
VIDEO_PRODUCTION_PARTIAL
or
VIDEO_PRODUCTION_BLOCKED

PIPELINE

Topic                  PASS
Episode                PASS
Screenplay             PASS
Review                 PASS
Lock                   PASS
Storyboard             PASS
Production Plan        PASS
Asset Preparation      PASS
Recording Preflight    PASS
Recording              PASS
Media Ingest           PASS
Timeline               PASS
Render                 PASS
Quality                PASS
Provenance             PASS
Recovery               PASS/WARN
Repeatability          PASS/WARN

FINAL ARTIFACT

path:
...

duration:
...

resolution:
...

fps:
...

codec:
...

size:
...

FAILURES

...

MANUAL INTERVENTIONS

...

MISSING CAPABILITIES

...

RECOMMENDED FIXES

P0:
...

P1:
...

P2:
...
```

---

# 25. Definition of Success

Mục tiêu cuối cùng của test không phải:

> “WindAgent có 163 endpoint và test suite pass.”

Mà phải chứng minh được pipeline này bằng artifact thật:

```text
ROADMAP
  │
  ▼
LESSON 01
  │
  ▼
EPISODE
  │
  ▼
SCREENPLAY
  │
  ▼
LOCK
  │
  ▼
STORYBOARD
  │
  ▼
PRODUCTION PLAN
  │
  ▼
LIVE RECORD
  │
  ▼
TAKES
  │
  ▼
TIMELINE
  │
  ▼
RENDER
  │
  ▼
QUALITY
  │
  ▼
lesson_01_llm_token_prediction.mp4
```

Chỉ khi chuỗi này chạy thật, WindAgent V2 mới có bằng chứng rằng nó đã bước từ **“kiến trúc cho sản xuất video”** sang **“thực sự sản xuất được video”**.
