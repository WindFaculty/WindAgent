Đối với WindAgent, tôi khuyến nghị **không test khả năng viết kịch bản bằng 1–2 prompt đơn lẻ**. Cần coi đây là một subsystem độc lập và xây một **Script Generation Evaluation Pipeline** trước khi nối sang asset → animation → audio → render.

Mục tiêu cuối cùng là trả lời được bằng evidence:

> **WindAgent có thể tự tạo một kịch bản hoạt hình 3D dài 5–20 phút, nhất quán về nhân vật/bối cảnh/cốt truyện, đủ chi tiết để Director Layer và engine sản xuất video sử dụng trực tiếp hay chưa?**

---

# 1. Phạm vi bài test

Pipeline test nên dừng ở ranh giới:

```text
User Prompt
    ↓
Idea / Story Concept
    ↓
Creative Brief
    ↓
Characters + World Bible
    ↓
Synopsis
    ↓
Beat Sheet
    ↓
Story Outline
    ↓
Scene Breakdown
    ↓
Dialogue + Action
    ↓
Continuity Validation
    ↓
Safety / Kids Content Validation
    ↓
Director Review
    ↓
Production Script
    ↓
Shot / Production Handoff
    ↓
[STOP]

Không tạo:
Asset
Animation
Voice
Music
Render
Video
```

Như vậy nếu kết quả thất bại, ta biết vấn đề nằm ở **reasoning / planning / screenplay pipeline**, không bị nhiễu bởi Blender, Unreal, TTS hoặc asset generation.

---

# 2. Kiến trúc test tôi đề xuất

```text
                    ┌────────────────────┐
                    │     TEST BRIEF     │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │   Story Planner    │
                    └─────────┬──────────┘
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   ┌──────────────────┐              ┌──────────────────┐
   │ Character Agent  │              │ World/Setting    │
   └────────┬─────────┘              └────────┬─────────┘
            └──────────────┬──────────────────┘
                           ▼
                  ┌─────────────────┐
                  │ Story Architect │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Scene Planner   │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Script Writer   │
                  └────────┬────────┘
                           ▼
       ┌───────────────────┼────────────────────┐
       ▼                   ▼                    ▼
┌─────────────┐    ┌───────────────┐    ┌─────────────┐
│ Continuity  │    │ Kids Safety   │    │ Production  │
│ Reviewer    │    │ Reviewer      │    │ Feasibility │
└──────┬──────┘    └───────┬───────┘    └──────┬──────┘
       └───────────────────┼────────────────────┘
                           ▼
                  ┌─────────────────┐
                  │ Director Agent  │
                  └────────┬────────┘
                           │
                     FAIL ─┼─ PASS
                           ▼
                  ┌─────────────────┐
                  │ Final Script    │
                  │ + Evidence      │
                  └─────────────────┘
```

Điểm quan trọng: **writer và reviewer không nên là cùng một agent context**. Nếu cùng context/model role, reviewer rất dễ tự xác nhận lỗi do chính nó tạo ra.

---

# 3. Phase 0 — Freeze baseline

Đây là phase bắt buộc trước khi đánh giá chất lượng.

### Công việc

Xác định:

| Thành phần       | Cần lưu                |
| ---------------- | ---------------------- |
| Git              | commit SHA             |
| WindAgent        | version                |
| Model            | provider/model/version |
| Temperature      | giá trị                |
| Seed             | nếu provider hỗ trợ    |
| System prompt    | SHA256                 |
| Story prompt     | SHA256                 |
| Character prompt | SHA256                 |
| Reviewer prompt  | SHA256                 |
| Config           | snapshot               |
| Runtime          | Python/OS/hardware     |
| Timestamp        | thời gian test         |

Không được thay prompt/model giữa test rồi gộp kết quả với nhau.

### Artifact

```text
artifacts/video_production/script_eval/
└── phase_00_baseline/
    ├── baseline_manifest.json
    ├── model_manifest.json
    ├── prompt_manifest.json
    ├── environment.json
    └── baseline_verdict.json
```

### Gate

```text
SCRIPT_EVAL_BASELINE_FROZEN
```

Nếu không freeze được baseline → dừng evaluation.

---

# 4. Phase 1 — Test contract/schema

Trước khi hỏi "kịch bản hay không", cần kiểm tra WindAgent có tạo **đúng dữ liệu** không.

Một production script tối thiểu nên chứa:

```text
Project
Episode
Target audience
Target duration
Genre
Theme
Educational goal

World bible

Characters
  ID
  name
  age/type
  appearance
  personality
  motivation
  voice profile
  relationships

Story
  logline
  synopsis
  acts
  beats

Scenes
  scene_id
  location
  time
  characters
  objective
  conflict
  action
  dialogue
  emotional state
  continuity state
  estimated_duration

Ending
Moral / lesson
Continuity summary
Production notes
```

### Automated test

Kiểm tra:

```text
missing field
duplicate scene_id
unknown character
unknown location
negative duration
zero duration
scene ordering
broken references
invalid enum
empty dialogue
empty scene objective
duration mismatch
```

### Gate

```text
Schema validity = 100%
Reference integrity = 100%
```

Hard fail nếu một production script còn dangling reference.

---

# 5. Phase 2 — Test Idea Generation

Không nên cho model tự chọn một chủ đề duy nhất rồi đánh giá chính chủ đề đó.

Tạo benchmark gồm khoảng **12–20 briefs**.

Ví dụ:

| Case | Loại                 |
| ---- | -------------------- |
| T01  | Phiêu lưu            |
| T02  | Hài                  |
| T03  | Giáo dục             |
| T04  | Tình bạn             |
| T05  | Gia đình             |
| T06  | Problem-solving      |
| T07  | Khoa học đơn giản    |
| T08  | Bảo vệ môi trường    |
| T09  | Bedtime story        |
| T10  | Fantasy              |
| T11  | Mystery nhẹ          |
| T12  | Không lời / ít thoại |

Mỗi case chạy:

```text
5 phút
10 phút
20 phút
```

Tức tối thiểu:

```text
12 × 3 = 36 script runs
```

Tốt hơn là khoảng **40–60 runs**.

### Đánh giá

Idea phải có:

* hook rõ;
* conflict phù hợp trẻ em;
* premise đủ để duy trì thời lượng;
* khác biệt so với các test khác;
* có payoff;
* có lesson nhưng không quá giáo điều;
* có khả năng thể hiện bằng hình ảnh.

---

# 6. Phase 3 — Story Architecture Test

Đây là một trong những phase quan trọng nhất.

Kiểm tra:

```text
Setup
↓
Goal
↓
Obstacle
↓
Escalation
↓
Turning Point
↓
Climax
↓
Resolution
```

Không chỉ kiểm tra "đủ trường".

Ví dụ lỗi:

```text
Scene 1:
Mèo muốn tìm quả bóng.

Scene 2:
Mèo đi tìm.

Scene 3:
Mèo hỏi bạn.

Scene 4:
Mèo tìm thấy bóng.

Scene 5:
Cả nhóm vui vẻ.
```

Schema hoàn toàn đúng nhưng screenplay rất yếu vì:

* không escalation;
* conflict gần như bằng 0;
* không surprise;
* nhân vật không cần đưa ra quyết định;
* climax yếu.

Reviewer phải phát hiện được dạng lỗi này.

### Gate đề xuất

```text
Story Architecture ≥ 8/10
```

---

# 7. Phase 4 — Character Consistency Test

Đây là bài test cực kỳ cần thiết trước khi chuyển sang phim 3D.

Mỗi character phải có canonical state.

Ví dụ:

```text
CHAR_001
Name: Miko

Appearance:
yellow shirt
blue shorts
brown hair

Personality:
curious
slightly impatient
kind

Knowledge:
cannot swim

Relationship:
Luna = younger sister
```

Sau mỗi scene tạo:

```text
character_state_before
character_state_after
```

Reviewer kiểm tra:

```text
appearance contradiction
knowledge contradiction
relationship contradiction
personality violation
position contradiction
object ownership contradiction
injury/state contradiction
```

Ví dụ:

```text
Scene 3:
Miko không biết bơi.

Scene 8:
Miko tự nhiên bơi qua hồ rất giỏi.
```

Nếu không có scene học bơi hoặc explanation → continuity failure.

### Gate

```text
Major character contradiction = 0
Minor contradiction <= 1 / episode
```

---

# 8. Phase 5 — World Continuity Test

Tương tự character, world cũng cần state.

Ví dụ:

```text
HOUSE
  kitchen
  bedroom
  backyard

SCHOOL
  classroom
  playground

FOREST
  bridge
  river
```

Agent không được:

```text
Scene 4:
nhân vật đang ở trường

Scene 5:
nhân vật xuất hiện trong rừng

không có transition.
```

Kiểm tra:

```text
location
time
weather
props
transportation
distance
day/night
object permanence
```

---

# 9. Phase 6 — Scene Quality Test

Mỗi scene nên trả lời được ít nhất:

```text
Ai?
Ở đâu?
Muốn gì?
Tại sao?
Điều gì cản họ?
Scene thay đổi điều gì?
Tại sao scene tiếp theo xảy ra?
```

Nếu bỏ scene mà câu chuyện không thay đổi → scene có khả năng dư thừa.

Nên tính:

```text
Scene Purpose Coverage
```

Yêu cầu:

```text
>= 95%
```

---

# 10. Phase 7 — Dialogue Evaluation

Với phim cho trẻ nhỏ, dialogue đặc biệt quan trọng.

Reviewer kiểm tra:

| Metric              | Kiểm tra                             |
| ------------------- | ------------------------------------ |
| Naturalness         | Có giống lời nói không               |
| Age appropriateness | Đúng lứa tuổi                        |
| Character voice     | Mỗi nhân vật khác nhau               |
| Exposition          | Có giải thích quá mức                |
| Repetition          | Có lặp lại                           |
| Speakability        | TTS có đọc tự nhiên                  |
| Visual redundancy   | Có nói lại những gì hình đã thể hiện |

Ví dụ xấu:

> "Như chúng ta đã biết, hôm qua chúng ta tới đây để tìm chiếc chìa khóa màu đỏ mà mẹ đã đánh mất."

Agent cần tránh kiểu exposition nhân tạo này.

---

# 11. Phase 8 — Duration Accuracy

Đây là phần tôi đặc biệt khuyến nghị test kỹ.

Với target:

```text
5 phút
10 phút
20 phút
```

WindAgent phải estimate:

```text
dialogue duration
action duration
transition duration
pause
reaction
establishing shot
```

Không chỉ lấy:

```text
word_count / speaking_speed
```

vì animation có nhiều đoạn không thoại.

Nên lưu:

```text
estimated_dialogue_duration
estimated_visual_duration
estimated_transition_duration
estimated_total_duration
```

### Gate

Trước production có thể cho tolerance:

```text
Target duration ±15%
```

Sau này khi có actual render data, giảm xuống:

```text
±10%
```

---

# 12. Phase 9 — Kids Safety & Content Policy

Đây là **hard gate**, không tính chung vào điểm trung bình.

Kiểm tra:

```text
violence
dangerous imitation
sexual content
strong language
fear/horror
bullying
discrimination
unsafe challenges
drug/alcohol
weapon glorification
dangerous instructions
age-inappropriate concepts
```

Ngoài safety còn kiểm tra:

```text
positive resolution
healthy social behavior
clear consequences
age-appropriate vocabulary
```

Một lỗi critical:

```text
SAFETY FAIL
```

không được phép reviewer khác nâng điểm để PASS.

---

# 13. Phase 10 — Production Feasibility

Đây là phần nhiều AI screenplay pipeline bỏ qua.

Một kịch bản có thể rất hay nhưng cực kỳ đắt để làm animation.

Ví dụ:

```text
100 nhân vật
50 địa điểm
crowd simulation
ocean simulation
city destruction
20 costume changes
complex vehicles
```

với một tập 10 phút sẽ phá production budget.

Reviewer cần tính:

```text
unique characters
unique environments
unique props
new assets required
crowd scenes
FX complexity
animation complexity
camera complexity
simulation requirements
```

Sau đó tạo:

```text
Production Complexity Score
```

Ví dụ:

```text
1 = trivial
2 = easy
3 = normal
4 = expensive
5 = impractical
```

Production bình thường nên:

```text
≤ 3
```

---

# 14. Phase 11 — Director Layer Test

Đây là bài test handoff quan trọng nhất đối với WindAgent.

Director Agent nhận **chỉ production script**, không được đọc hidden reasoning của writer.

Nó phải có khả năng tạo:

```text
Scene
↓
Shot
↓
Camera
↓
Character action
↓
Expression
↓
Animation requirement
↓
Environment
↓
Props
↓
Audio requirement
```

Ví dụ:

```text
SCENE_007

SHOT_007_01
Wide establishing shot

SHOT_007_02
Medium shot Miko

SHOT_007_03
Close-up reaction

SHOT_007_04
Tracking shot
```

Nếu Director thường xuyên phải suy đoán:

```text
ai đang đứng đâu
nhân vật đang cầm gì
camera phải thấy gì
emotion là gì
```

thì screenplay contract chưa đủ tốt.

### Gate

```text
Director ambiguity rate < 5%
```

---

# 15. Phase 12 — Adversarial Test

Cần cố tình làm khó agent.

Ví dụ input:

```text
10 phút
7 nhân vật
3 location
không violence
chủ đề chia sẻ
phải có mystery
không narration
chỉ tối đa 2 nhân vật xuất hiện đồng thời
không tạo asset mới ngoài asset library
```

Sau đó kiểm tra agent có vi phạm constraint hay không.

Các nhóm test:

```text
contradictory requirement
very sparse prompt
very detailed prompt
large character count
restricted asset set
single environment
dialogue-free scene
flashback
time jump
parallel storylines
```

---

# 16. Phase 13 — Repeatability / Regression Test

Một vấn đề lớn của LLM là nondeterminism.

Chọn khoảng:

```text
10 benchmark prompts
```

Mỗi prompt chạy:

```text
3 lần
```

Tổng:

```text
30 executions
```

Không yêu cầu câu chuyện giống nhau.

Nhưng các thuộc tính phải ổn định:

```text
schema compliance
duration
safety
continuity
production complexity
constraint satisfaction
```

Nếu một prompt:

```text
Run 1 = 92
Run 2 = 89
Run 3 = 61
```

thì hệ thống chưa production-ready.

---

# 17. Phase 14 — Multi-agent Review

Tôi đề xuất ít nhất ba reviewer độc lập:

```text
Reviewer A
Story / screenplay

Reviewer B
Continuity / logic

Reviewer C
Production / safety
```

Sau đó:

```text
                    Script
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     Story          Logic       Production
    Reviewer       Reviewer      Reviewer
        │             │             │
        └─────────────┼─────────────┘
                      ▼
                 Judge Agent
                      │
              ┌───────┴────────┐
              ▼                ▼
            PASS              FIX
                               │
                               ▼
                           Rewrite
                               │
                               └──────► Review
```

Giới hạn:

```text
max_revision_cycles = 3
```

Nếu qua 3 vòng vẫn fail:

```text
SCRIPT_REJECTED
```

Không cho infinite self-correction.

---

# 18. Scorecard chính thức

Tôi đề xuất thang 100:

| Tiêu chí                 |    Điểm |
| ------------------------ | ------: |
| Story structure          |      15 |
| Character quality        |      10 |
| Character consistency    |      10 |
| World continuity         |       8 |
| Scene quality            |      10 |
| Dialogue                 |      10 |
| Pacing                   |       8 |
| Emotional progression    |       7 |
| Originality              |       5 |
| Visual storytelling      |       5 |
| Production feasibility   |       7 |
| Director handoff quality |       5 |
| **Tổng**                 | **100** |

Safety không nằm trong 100.

Schema cũng không nằm trong 100.

Vì:

```text
Schema = hard gate
Safety = hard gate
```

---

# 19. Quy tắc PASS/FAIL

Tôi sẽ đặt production gate tương đối cao:

```text
Schema valid                    = 100%
Critical safety violations      = 0
Major continuity violations     = 0

Constraint satisfaction         >= 98%
Duration accuracy               within ±15%
Director ambiguity              < 5%

Overall screenplay              >= 85/100

Story structure                 >= 8/10 equivalent
Character consistency           >= 9/10
Production feasibility          >= 8/10 equivalent

Regression success              >= 95%
```

### Verdict

```text
>= 90
SCRIPT_PRODUCTION_READY

85–89
SCRIPT_READY_WITH_MINOR_REVIEW

75–84
SCRIPT_REQUIRES_IMPROVEMENT

60–74
SCRIPT_PIPELINE_NOT_READY

<60
SCRIPT_PIPELINE_FAILED
```

Nhưng bất kỳ hard gate nào fail:

```text
SCRIPT_PIPELINE_BLOCKED
```

dù tổng điểm là 95.

---

# 20. Human evaluation

Không nên để LLM tự đánh giá 100%.

Sau automated evaluation, lấy khoảng:

```text
10 script đại diện
```

gồm:

```text
3 tốt nhất
4 trung bình
3 tệ nhất
```

Human reviewer chấm blind.

So sánh:

```text
AI score
vs
Human score
```

Nếu AI reviewer liên tục cho:

```text
92/100
```

nhưng con người cho:

```text
65/100
```

thì vấn đề nằm ở **evaluator**, không phải writer.

Đây là lỗi rất phổ biến trong hệ thống agent tự đánh giá.

---

# 21. Artifact structure

Tôi đề xuất tạo riêng:

```text
artifacts/video_production/script_eval/

├── phase_00_baseline/
├── phase_01_contract/
├── phase_02_idea/
├── phase_03_story/
├── phase_04_character/
├── phase_05_continuity/
├── phase_06_scene/
├── phase_07_dialogue/
├── phase_08_duration/
├── phase_09_safety/
├── phase_10_production/
├── phase_11_director_handoff/
├── phase_12_adversarial/
├── phase_13_regression/
├── phase_14_multi_agent_review/
└── final/
```

Trong mỗi test case:

```text
case_001/
├── input.json
├── execution_receipt.json
├── creative_brief.json
├── world_bible.json
├── character_bible.json
├── synopsis.json
├── beat_sheet.json
├── script.json
├── production_script.json
├── continuity_report.json
├── safety_report.json
├── production_report.json
├── director_handoff.json
├── reviewer_scores.json
└── verdict.json
```

---

# 22. Final report

Cuối benchmark, WindAgent phải sinh:

```text
script_evaluation_report.md
benchmark_manifest.json
score_summary.json
failure_matrix.json
regression_report.json
human_ai_agreement.json
production_readiness.json
final_verdict.json
```

`failure_matrix.json` đặc biệt hữu ích.

Ví dụ:

| Error                   | Count | Severity |
| ----------------------- | ----: | -------- |
| Character contradiction |     7 | High     |
| Duration mismatch       |    12 | Medium   |
| Weak climax             |    18 | High     |
| Repetitive dialogue     |    23 | Medium   |
| Missing transition      |     5 | High     |
| Safety violation        |     0 | Critical |
| Production too complex  |     8 | High     |

Từ đây mới biết chính xác phải sửa **prompt**, **agent**, **workflow**, **memory**, hay **model**.

---

# 23. Phase 15 — Script-only E2E Dry Run

Sau khi tất cả component test PASS, chạy một bài cuối.

Input chỉ nên giống yêu cầu thật của người dùng, ví dụ:

```text
"Tạo một tập hoạt hình 3D khoảng 10 phút cho trẻ em,
chủ đề tình bạn và giúp đỡ người khác."
```

WindAgent tự thực hiện:

```text
Prompt
 ↓
Idea generation
 ↓
Idea selection
 ↓
Creative brief
 ↓
Character design
 ↓
World design
 ↓
Synopsis
 ↓
Story architecture
 ↓
Scene breakdown
 ↓
Dialogue
 ↓
Continuity
 ↓
Safety
 ↓
Production feasibility
 ↓
Reviewer
 ↓
Revision
 ↓
Director handoff
 ↓
Final production script
 ↓
Final report
```

Không can thiệp bằng tay giữa pipeline.

Đây mới là test chứng minh agent có thể **tự vận hành**.

---

# 24. Final Gate trước khi sản xuất video

Tôi sẽ tạo một gate riêng:

```text
VIDEO_SCRIPTING_PRODUCTION_GATE
```

Chỉ PASS khi:

```text
✓ Contract tests PASS
✓ Story benchmark PASS
✓ Character tests PASS
✓ Continuity tests PASS
✓ Dialogue tests PASS
✓ Duration tests PASS
✓ Safety tests PASS
✓ Production feasibility PASS
✓ Director handoff PASS
✓ Adversarial tests PASS
✓ Regression PASS
✓ Human evaluation PASS
✓ Full autonomous E2E PASS
```

Verdict cuối cùng chỉ có:

```text
VIDEO_SCRIPTING_PRODUCTION_READY
```

hoặc:

```text
VIDEO_SCRIPTING_PRODUCTION_BLOCKED
```

---

# 25. Thứ tự thực hiện thực tế

Tôi đề xuất roadmap:

```text
Phase 0
Baseline
   │
   ▼
Phase 1
Schema / Contract
   │
   ├──────────────┐
   ▼              ▼
Phase 2         Phase 4
Idea/Story      Character
   │              │
   ▼              ▼
Phase 3         Phase 5
Structure       Continuity
   │              │
   └──────┬───────┘
          ▼
       Phase 6
       Scenes
          │
    ┌─────┼─────────┐
    ▼     ▼         ▼
 Phase7 Phase8    Phase9
Dialogue Duration Safety
    │     │         │
    └─────┼─────────┘
          ▼
       Phase10
 Production feasibility
          │
          ▼
       Phase11
 Director handoff
          │
    ┌─────┴─────┐
    ▼           ▼
 Phase12      Phase13
Adversarial  Regression
    └─────┬─────┘
          ▼
       Phase14
 Multi-review
          │
          ▼
       Phase15
 Autonomous E2E
          │
          ▼
   HUMAN VALIDATION
          │
          ▼
VIDEO_SCRIPTING_PRODUCTION_GATE
```

**Phase 2–5 có thể chạy một phần song song**, và Phase 7–9 có thể chạy hoàn toàn song song trên cùng một generated script. Điều này phù hợp với định hướng WindAgent sử dụng orchestration để giảm tổng thời gian pipeline.

---

## Khuyến nghị quan trọng nhất

Đừng bắt đầu bằng việc yêu cầu WindAgent:

> "Viết một kịch bản hay rồi xem thử."

Hãy tạo **benchmark cố định khoảng 40–60 script executions**, scorecard cố định và evidence đầy đủ. Sau mỗi thay đổi prompt/model/agent architecture, chạy lại cùng benchmark.

Khi đó bạn sẽ có dữ liệu kiểu:

```text
Build A
82.3 / 100
Continuity failure: 14%

Build B
87.6 / 100
Continuity failure: 4%

Build C
91.1 / 100
Continuity failure: 0%
Director ambiguity: 2.1%
```

Lúc đó mới có cơ sở kết luận phiên bản nào thực sự tốt hơn.

Với kiến trúc video hiện tại của WindAgent, tôi sẽ coi **Phase 15 + VIDEO_SCRIPTING_PRODUCTION_GATE là Phase bắt buộc ngay trước khi pipeline bắt đầu tạo asset 3D, audio và điều khiển Blender/Unreal**. Việc này giúp tránh trường hợp pipeline kỹ thuật hoạt động hoàn hảo nhưng phải render lại cả tập vì lỗi cốt truyện hoặc continuity.
