# NHIỆM VỤ: KIỂM THỬ QUÁ TRÌNH TẠO KỊCH BẢN VÀ ĐÁNH GIÁ MỨC ĐỘ HOÀN THIỆN CỦA VIDEO PRODUCTION PIPELINE

Bạn đang làm việc trong repository **WindAgent**, với kiến trúc mục tiêu:

```text
VideoClaw
    ↓
WindAgent Director Layer
    ↓
Google Flow Browser Provider
    ↓
Generated Assets / Video
```

Mục tiêu của nhiệm vụ này **không phải tuyên bố pipeline đã hoàn thiện**, mà là thực hiện một đợt kiểm thử có kiểm soát để xác định chính xác:

1. Quá trình tạo kịch bản hiện hoạt động đến đâu.
2. Những thành phần nào của pipeline đã chạy thật.
3. Những thành phần nào mới chỉ là scaffold, mock, demo hoặc dry-run.
4. Pipeline bị dừng tại bước nào.
5. Nguyên nhân kỹ thuật cụ thể của từng lỗi hoặc blocker.
6. Chất lượng đầu ra kịch bản có đủ để chuyển sang quá trình sản xuất video hay không.
7. Cần thực hiện những công việc nào tiếp theo để đạt được một pipeline end-to-end hoàn chỉnh.

Kết quả bắt buộc là một **bộ artifact và báo cáo chi tiết, có evidence kiểm chứng được**, không chỉ là phần tóm tắt trong terminal.

---

# 1. NGUYÊN TẮC THỰC HIỆN

## 1.1. Không sửa bừa để làm test chuyển sang PASS

Không được:

* Sửa test để che giấu lỗi.
* Xóa hoặc bỏ qua assertion quan trọng.
* Chuyển pipeline thật thành mock nhưng vẫn báo PASS.
* Hardcode đầu ra để vượt qua kiểm thử.
* Tự động thay đổi CI khi chưa xác định được nguyên nhân.
* Tự ý sửa những module ngoài phạm vi kiểm thử.
* Dùng dữ liệu giả nhưng ghi là dữ liệu production.
* Tuyên bố Google Flow hoạt động nếu chỉ mới tạo request payload.
* Tuyên bố video đã được tạo nếu chưa có file video hợp lệ.
* Ghi nhận bước browser automation là PASS nếu trình duyệt chưa thực sự thao tác thành công.
* Bỏ qua lỗi do thiếu credential, browser profile, model hoặc dependency.

Nếu phát hiện lỗi, ưu tiên:

1. Thu thập evidence.
2. Phân loại lỗi.
3. Xác định root cause.
4. Ghi blocker vào báo cáo.
5. Chỉ sửa lỗi khi đó là lỗi nhỏ, rõ ràng, nằm trực tiếp trong test harness hoặc instrumentation và không làm thay đổi hành vi nghiệp vụ.

Nếu cần sửa source code đáng kể, dừng việc sửa và ghi rõ đề xuất vào báo cáo.

---

## 1.2. Không làm bẩn baseline

Trước khi chạy test:

* Ghi lại current branch.
* Ghi lại current HEAD SHA.
* Ghi lại trạng thái worktree.
* Ghi lại danh sách file tracked đang thay đổi.
* Ghi lại danh sách file untracked.
* Ghi lại Python, Node.js, package manager, browser và OS version.
* Ghi lại cấu hình provider đang được sử dụng nhưng phải che toàn bộ secret.

Nên chạy kiểm thử trong:

* Git worktree cô lập; hoặc
* Temporary checkout; hoặc
* Môi trường test riêng.

Sau khi kiểm thử:

* So sánh worktree trước và sau.
* Phát hiện file tracked bị thay đổi ngoài dự kiến.
* Liệt kê chính xác test hoặc command nào gây mutation.
* Không tự động reset những thay đổi đó trước khi thu thập evidence.

---

## 1.3. Không giả định cấu trúc đã hoạt động

Phải kiểm tra source code và runtime để phân biệt:

* Implemented và được gọi thật.
* Implemented nhưng chưa được wiring.
* Được wiring nhưng chỉ chạy mock.
* Chỉ có interface hoặc protocol.
* Chỉ có test fixture.
* Chỉ có demo mode.
* Chưa được implement.
* Bị chặn bởi credential hoặc môi trường.
* Bị chặn bởi lỗi runtime.
* Bị chặn bởi thiết kế chưa hoàn chỉnh.

Mọi kết luận phải có đường dẫn source, command, log hoặc artifact hỗ trợ.

---

# 2. PHẠM VI KIỂM THỬ

Đánh giá toàn bộ luồng sau:

```text
Production Brief
    ↓
Idea / Story Concept
    ↓
Audience and Safety Constraints
    ↓
Story Bible
    ↓
Character Bible
    ↓
World / Location Bible
    ↓
Episode Outline
    ↓
Beat Sheet
    ↓
Scene Breakdown
    ↓
Dialogue Script
    ↓
Shot List
    ↓
Asset Requirements
    ↓
Image / Video Generation Prompt
    ↓
Provider Request
    ↓
Google Flow Browser Automation
    ↓
Generated Image / Clip
    ↓
Clip Validation
    ↓
Assembly / Timeline
    ↓
Final Video
    ↓
Production Report
```

Mỗi bước phải được gắn một trong các trạng thái:

```text
PASS_LIVE
PASS_LOCAL
PASS_DRY_RUN
PASS_MOCK_ONLY
PARTIAL
BLOCKED_ENVIRONMENT
BLOCKED_CREDENTIAL
BLOCKED_DEPENDENCY
BLOCKED_RUNTIME
NOT_IMPLEMENTED
NOT_WIRED
NOT_TESTED
FAILED
```

Không sử dụng từ `PASS` chung chung.

---

# 3. KỊCH BẢN KIỂM THỬ CHUẨN

Tạo một production brief cố định để dùng xuyên suốt đợt kiểm thử.

## 3.1. Nội dung thử nghiệm

```text
Loại nội dung: Phim hoạt hình cho trẻ em
Độ tuổi mục tiêu: 6–9 tuổi
Thời lượng mục tiêu: 5–7 phút
Ngôn ngữ: Tiếng Việt
Thể loại: Phiêu lưu, hài nhẹ, giáo dục
Chủ đề: Biết nhận lỗi và sửa lỗi
Số nhân vật chính: 2
Số nhân vật phụ tối đa: 2
Số bối cảnh chính: 3
Số cảnh mục tiêu: 8–12 cảnh
Phong cách hình ảnh: Hoạt hình 3D mềm mại, màu sắc rõ ràng, thân thiện với trẻ em
Yêu cầu nhất quán: Nhân vật, trang phục, màu sắc và tỷ lệ cơ thể phải nhất quán giữa các cảnh
Yêu cầu an toàn: Không bạo lực, không kinh dị, không hành vi nguy hiểm có thể bắt chước
Đầu ra cuối mong muốn: Kịch bản có thể chuyển trực tiếp sang shot list và video generation
```

## 3.2. Nội dung câu chuyện gợi ý

```text
Hai người bạn nhỏ vô tình làm hỏng một món đồ quan trọng trong thư viện của làng.
Ban đầu, một nhân vật muốn giấu lỗi.
Nhân vật còn lại khuyên nên nói thật.
Hai người cùng tìm cách sửa lại món đồ và nhận được sự giúp đỡ từ người quản lý thư viện.
Kết thúc phải cho thấy việc nhận lỗi và sửa lỗi giúp mọi người tin tưởng nhau hơn.
```

Có thể điều chỉnh chi tiết để phù hợp với schema hiện tại, nhưng không được thay đổi mục tiêu giáo dục cốt lõi.

---

# 4. PHASE A — KHẢO SÁT KIẾN TRÚC VÀ INVENTORY

Trước khi chạy pipeline, hãy lập inventory đầy đủ.

## 4.1. Xác định module liên quan

Tìm và lập danh sách các module thực tế liên quan đến:

* VideoClaw integration.
* Director Layer.
* Script writer.
* Story planner.
* Character manager.
* Scene planner.
* Shot planner.
* Prompt generator.
* Asset manager.
* Production state.
* Workflow engine.
* Provider abstraction.
* Google Flow provider.
* Browser automation.
* Browser session/profile management.
* Image generation.
* Video generation.
* Clip validation.
* Timeline or assembly.
* Reporting.
* Artifact persistence.
* Retry and recovery.
* Human approval gates.

Với mỗi module, ghi:

```text
Module:
Path:
Purpose:
Implementation status:
Runtime entry point:
Caller:
Dependencies:
Uses mock/demo/live data:
Existing tests:
Known gaps:
```

## 4.2. Xác định entry point thật

Tìm tất cả entry point có khả năng khởi chạy pipeline:

* CLI command.
* Python module.
* API endpoint.
* Worker job.
* Workflow definition.
* Desktop action.
* Web action.
* Test helper.
* Script trong thư mục scripts.
* Makefile, task runner hoặc package script.

Không tự tạo entry point mới trước khi xác nhận các entry point hiện có.

## 4.3. Xác định schema và contract

Thu thập các schema cho:

* Production brief.
* Story concept.
* Story bible.
* Character.
* Location.
* Episode outline.
* Scene.
* Dialogue.
* Shot.
* Asset.
* Provider request.
* Provider response.
* Browser action.
* Generated clip.
* Production report.
* Workflow state.

Kiểm tra:

* Field bắt buộc.
* Validation.
* Versioning.
* Serialization.
* ID relationships.
* Referential integrity.
* Trạng thái lifecycle.
* Khả năng resume sau lỗi.

---

# 5. PHASE B — BASELINE TEST

Chạy các test hiện có có liên quan trực tiếp đến video production pipeline.

Ưu tiên khám phá command từ repository thay vì đoán. Có thể bao gồm:

```bash
pytest
pytest tests/video_production
pytest tests/director
pytest tests/providers
pytest tests/workflows
pytest tests/browser
pytest tests/integration
pytest tests/e2e
```

Với frontend hoặc desktop:

```bash
npm test
npm run test
npm run build
npm run typecheck
npm run lint
```

Chỉ chạy command tồn tại thật trong repository.

Ghi lại cho mỗi command:

```text
command_id
command
cwd
started_at
finished_at
duration_ms
exit_code
expected_exit_codes
stdout artifact
stderr artifact
environment
git_sha
result
warnings
output_sha256
```

Phân loại test thành:

* Unit.
* Contract.
* Integration.
* Browser.
* End-to-end.
* Live provider.
* Dry-run.
* Mock-only.
* Regression.
* Architecture.
* Artifact validation.

Không gộp tất cả thành một con số tổng duy nhất.

---

# 6. PHASE C — KIỂM THỬ TẠO KỊCH BẢN

Thực hiện pipeline tạo kịch bản bằng production brief chuẩn.

## 6.1. Kiểm tra đầu vào

Xác minh:

* Brief được parse thành công.
* Không mất dữ liệu.
* Có ID ổn định.
* Có schema version.
* Có production ID.
* Có target duration.
* Có target audience.
* Có content safety constraints.
* Có language.
* Có style.
* Có character and location limits.

## 6.2. Kiểm tra idea và story concept

Đầu ra tối thiểu phải có:

* Logline.
* Premise.
* Theme.
* Educational objective.
* Central conflict.
* Resolution.
* Intended emotional arc.
* Audience suitability.
* Estimated duration.
* Rationale.

Đánh giá xem đầu ra được tạo bởi:

* Model thật.
* Local model.
* Remote API.
* Rule-based fallback.
* Fixture.
* Hardcoded sample.
* Mock.

## 6.3. Kiểm tra story bible

Story bible tối thiểu phải có:

* Story world.
* Tone.
* Narrative rules.
* Educational objective.
* Continuity rules.
* Prohibited content.
* Visual style.
* Character relationships.
* Canonical facts.
* Episode-level constraints.

Kiểm tra tính nhất quán giữa story concept và story bible.

## 6.4. Kiểm tra character bible

Với từng nhân vật, yêu cầu:

* Character ID.
* Name.
* Role.
* Age group.
* Personality.
* Motivation.
* Strength.
* Weakness.
* Speech style.
* Visual description.
* Clothing.
* Color palette.
* Distinctive features.
* Prohibited variations.
* Relationship with other characters.
* Character arc.
* Image generation identity prompt.

Kiểm tra:

* Không đổi tên giữa các artifact.
* Không đổi màu trang phục.
* Không đổi loài, giới tính biểu hiện hoặc độ tuổi ngoài ý muốn.
* Không xuất hiện thêm nhân vật không được định nghĩa.
* Mỗi nhân vật có ID được tham chiếu ổn định.

## 6.5. Kiểm tra location bible

Mỗi bối cảnh phải có:

* Location ID.
* Name.
* Purpose.
* Time of day.
* Lighting.
* Color palette.
* Key props.
* Spatial constraints.
* Visual prompt.
* Continuity rules.

Kiểm tra giới hạn tối đa ba bối cảnh chính.

## 6.6. Kiểm tra episode outline và beat sheet

Outline phải có:

* Opening.
* Inciting incident.
* Escalation.
* Midpoint.
* Crisis.
* Decision.
* Resolution.
* Educational payoff.
* Closing image.

Kiểm tra:

* Mỗi beat đóng góp cho câu chuyện.
* Không có cảnh thừa rõ ràng.
* Mâu thuẫn được giải quyết hợp lý.
* Bài học không bị trình bày quá giáo điều.
* Kết thúc phù hợp trẻ em.
* Thời lượng ước tính nằm trong khoảng 5–7 phút.

## 6.7. Kiểm tra scene breakdown

Mỗi scene phải có:

```text
scene_id
sequence_number
title
purpose
location_id
character_ids
estimated_duration_seconds
time_of_day
continuity_from_previous_scene
action
dialogue_summary
emotional_state
required_props
visual_requirements
audio_requirements
transition
```

Kiểm tra:

* Số scene từ 8 đến 12.
* Sequence liên tục.
* Không trùng scene ID.
* Tổng thời lượng hợp lý.
* Không dùng location hoặc character ID không tồn tại.
* Trạng thái nhân vật nối tiếp hợp lý.
* Đạo cụ không xuất hiện hoặc biến mất vô lý.
* Scene có mục đích rõ ràng.

## 6.8. Kiểm tra dialogue script

Kịch bản thoại phải có:

* Scene heading.
* Action.
* Dialogue.
* Speaker ID.
* Emotion.
* Pause hoặc timing nếu cần.
* Voice direction.
* Narration nếu có.
* Không dùng từ ngữ không phù hợp trẻ em.
* Không vượt quá số lượng thoại khiến thời lượng bị sai lệch lớn.

Ước lượng thời lượng dựa trên số từ và nhịp nói tiếng Việt.

Ghi rõ phương pháp ước lượng.

## 6.9. Kiểm tra shot list

Mỗi shot tối thiểu phải có:

```text
shot_id
scene_id
shot_number
shot_type
camera_angle
camera_movement
subject
character_ids
location_id
action
emotion
composition
lighting
duration_seconds
continuity_constraints
start_frame_description
end_frame_description
generation_prompt
negative_prompt
audio_reference
```

Kiểm tra:

* Shot tham chiếu đúng scene.
* Tổng thời lượng shot gần với scene duration.
* Không có shot duration bằng 0 hoặc âm.
* Camera direction hợp lý.
* Không thay đổi nhận dạng nhân vật.
* Prompt không mâu thuẫn với character bible.
* Prompt không mâu thuẫn với location bible.
* Có continuity từ shot trước sang shot sau.

---

# 7. PHASE D — ĐÁNH GIÁ CHẤT LƯỢNG KỊCH BẢN

Tạo bộ chấm điểm từ 0 đến 100.

## 7.1. Story quality — 20 điểm

* Cấu trúc rõ ràng: 5.
* Mâu thuẫn và giải quyết hợp lý: 5.
* Nhịp kể chuyện: 5.
* Kết thúc thỏa đáng: 5.

## 7.2. Child audience suitability — 15 điểm

* Ngôn ngữ phù hợp: 5.
* Nội dung an toàn: 5.
* Khả năng hiểu của trẻ 6–9 tuổi: 5.

## 7.3. Educational effectiveness — 15 điểm

* Bài học rõ nhưng không giáo điều: 5.
* Hành động nhân vật thể hiện bài học: 5.
* Kết quả của lựa chọn có logic: 5.

## 7.4. Character consistency — 15 điểm

* Tính cách nhất quán: 5.
* Hành vi phù hợp động cơ: 5.
* Visual identity nhất quán: 5.

## 7.5. Scene and continuity quality — 15 điểm

* Scene ordering: 5.
* Props/location continuity: 5.
* Emotional continuity: 5.

## 7.6. Production readiness — 20 điểm

* Có thể chuyển thành shot list: 5.
* Có đủ visual information: 5.
* Có timing đủ rõ: 5.
* Có prompt generation input đầy đủ: 5.

Phân loại:

```text
90–100: PRODUCTION_READY
80–89: READY_WITH_MINOR_REVISIONS
70–79: REQUIRES_REVISION
50–69: MAJOR_REWORK_REQUIRED
0–49: NOT_USABLE
```

Ngoài điểm số tự động, phải ghi rõ:

* Các lỗi cụ thể.
* Artifact hoặc scene liên quan.
* Mức độ nghiêm trọng.
* Đề xuất sửa.
* Có chặn bước video generation hay không.

Không tự cho điểm cao nếu không có bằng chứng.

---

# 8. PHASE E — KIỂM THỬ MODEL VÀ PROVIDER

Xác định model nào thực sự được gọi ở từng bước.

Với mỗi model call, ghi:

```text
provider
model
endpoint type
local or remote
request ID
task type
input token estimate
output token estimate
latency
retry count
fallback used
structured output validity
response artifact
error
```

Không ghi API key vào artifact.

Nếu kiến trúc hiện tại có:

* Local Qwen.
* Google model cho tổng hợp.
* Model fallback.
* Rule-based fallback.

Hãy chạy và ghi riêng từng đường đi nếu cấu hình và credential cho phép.

Nếu không có model hoặc credential:

* Không giả lập thành công.
* Chuyển sang `BLOCKED_CREDENTIAL` hoặc `BLOCKED_ENVIRONMENT`.
* Vẫn kiểm tra được schema, prompt construction và dry-run payload.
* Ghi rõ bước nào chưa được kiểm chứng live.

Kiểm tra structured output:

* JSON parse thành công.
* Schema validation.
* Không mất field.
* Không có malformed JSON.
* Không có markdown wrapper ngoài ý muốn.
* Không có ID không hợp lệ.
* Không có text bị truncate.
* Có retry khi output sai schema.
* Retry có giới hạn.
* Có lưu raw response phục vụ audit.

---

# 9. PHASE F — KIỂM THỬ PIPELINE ORCHESTRATION

Chạy pipeline từ production brief đến mức xa nhất mà hệ thống hiện tại hỗ trợ.

Kiểm tra:

* Workflow được tạo.
* Production ID được duy trì.
* Mỗi stage có state rõ ràng.
* Stage output được persist.
* Stage dependency được tôn trọng.
* Failure được ghi lại.
* Retry hoạt động đúng.
* Retry không tạo duplicate artifact.
* Pipeline có thể resume.
* Cancel có hiệu lực.
* Timeout có hiệu lực.
* Human approval gate có hoạt động.
* Stage không được đánh dấu completed trước khi artifact hợp lệ.
* Exception không bị nuốt.
* Logs có correlation ID.
* Có deterministic ordering.
* Có provenance cho từng artifact.

Chạy tối thiểu các tình huống:

## F1. Happy path

Production brief hợp lệ, model/provider khả dụng.

## F2. Invalid brief

Thiếu target audience hoặc duration.

Kỳ vọng:

* Validation fail sớm.
* Không gọi model.
* Không tạo downstream artifact sai.

## F3. Model malformed output

Dùng fixture hoặc controlled injection trả JSON lỗi.

Kỳ vọng:

* Validation fail.
* Retry theo policy.
* Không đánh dấu stage PASS.

## F4. Model timeout

Kỳ vọng:

* Timeout rõ ràng.
* Retry có giới hạn.
* Workflow chuyển trạng thái đúng.

## F5. Missing character reference

Một scene tham chiếu character ID không tồn tại.

Kỳ vọng:

* Referential integrity gate chặn pipeline.

## F6. Provider unavailable

Google Flow hoặc model provider không khả dụng.

Kỳ vọng:

* Pipeline dừng đúng stage.
* Artifact trước đó vẫn được giữ.
* Có thể resume sau khi provider hoạt động lại.

## F7. Duplicate execution

Gửi cùng production request hai lần.

Kỳ vọng:

* Có idempotency hoặc ghi rõ hiện chưa có.
* Không âm thầm tạo nhiều production giống nhau.

## F8. Resume after interruption

Dừng pipeline sau script generation rồi khởi động lại.

Kỳ vọng:

* Không tạo lại toàn bộ artifact nếu không cần.
* Tiếp tục từ checkpoint hợp lệ.

---

# 10. PHASE G — KIỂM THỬ GOOGLE FLOW BROWSER PROVIDER

Chỉ chạy live test nếu:

* Có browser profile hợp lệ.
* Có phiên đăng nhập được người dùng cho phép.
* Có credential hợp lệ.
* Không vi phạm điều khoản sử dụng.
* Không sử dụng cơ chế vượt CAPTCHA hoặc né hệ thống bảo vệ.

Phân biệt rõ ba mức:

```text
DRY_RUN:
Chỉ tạo payload hoặc browser action plan.

BROWSER_INTERACTION:
Đã mở trình duyệt và thao tác giao diện, nhưng chưa tạo được asset.

LIVE_GENERATION:
Đã gửi prompt và nhận được asset hợp lệ từ Google Flow.
```

## 10.1. Kiểm tra browser startup

* Browser khởi động.
* Profile được load.
* Session còn hiệu lực.
* Không lộ credential.
* Có screenshot hoặc trace.
* Có timeout.
* Có cleanup.

## 10.2. Kiểm tra navigation

* Điều hướng đúng trang.
* Xác định đúng trạng thái đăng nhập.
* Xác định đúng UI version nếu có thể.
* Selector không phụ thuộc hoàn toàn vào text dễ thay đổi.
* Có fallback selector hợp lý.
* Có screenshot trước và sau thao tác quan trọng.

## 10.3. Kiểm tra prompt submission

* Prompt được lấy từ shot list thật.
* Prompt giữ đúng character identity.
* Không bị cắt nội dung.
* Không gửi trùng.
* Có provider job ID hoặc correlation ID nếu thu được.
* Có ghi thời điểm gửi.

## 10.4. Kiểm tra kết quả

Nếu tạo ảnh:

* File tồn tại.
* MIME type hợp lệ.
* Có kích thước lớn hơn 0.
* Có thể decode.
* Resolution được ghi nhận.
* Hash được ghi nhận.

Nếu tạo video:

* File tồn tại.
* Container hợp lệ.
* Có video stream.
* Duration lớn hơn 0.
* Resolution hợp lệ.
* Frame count hợp lý.
* Có thể đọc bằng công cụ media probe.
* Hash được ghi nhận.

Không được báo `LIVE_GENERATION PASS` chỉ dựa trên screenshot giao diện.

## 10.5. Kiểm tra download và persistence

* Asset được tải về thư mục production riêng.
* Tên file không va chạm.
* Có metadata.
* Có source prompt.
* Có shot ID.
* Có generation attempt.
* Có model/provider information nếu thu được.
* Có checksum.
* Có thumbnail hoặc preview nếu pipeline hỗ trợ.

Nếu bị CAPTCHA, thay đổi UI, hết quota hoặc session hết hạn:

* Ghi đúng blocker.
* Chụp evidence.
* Không cố vượt qua cơ chế bảo vệ.
* Không báo lỗi chung chung là “browser failed”.

---

# 11. PHASE H — KIỂM THỬ ASSET VÀ VIDEO ASSEMBLY

Nếu pipeline đã tạo được image hoặc clip, kiểm tra:

* Asset manifest.
* Mapping giữa shot và asset.
* Thiếu shot.
* Asset trùng.
* Duration mismatch.
* Aspect ratio.
* Resolution.
* Codec.
* Audio presence.
* Corrupted media.
* Character consistency metadata.
* Retry attempt selection.

Nếu có assembly:

* Timeline được tạo.
* Shot order đúng.
* Clip duration đúng.
* Transition hợp lệ.
* Audio sync.
* Voice-over mapping.
* Background music mapping.
* Subtitle mapping.
* Export thành công.
* File đầu ra được media probe xác nhận.

Nếu chưa implement assembly, đánh dấu `NOT_IMPLEMENTED`, không xem các clip rời là video cuối.

---

# 12. PHASE I — XÁC ĐỊNH PIPELINE ĐÃ HOẠT ĐỘNG ĐẾN ĐÂU

Tạo một bảng stage matrix như sau:

| Stage                | Source path | Runtime entry | Test type | Data source | Status | Evidence | Blocker | Next action |
| -------------------- | ----------- | ------------- | --------- | ----------- | ------ | -------- | ------- | ----------- |
| Brief ingestion      |             |               |           |             |        |          |         |             |
| Idea generation      |             |               |           |             |        |          |         |             |
| Story bible          |             |               |           |             |        |          |         |             |
| Character bible      |             |               |           |             |        |          |         |             |
| Episode outline      |             |               |           |             |        |          |         |             |
| Scene breakdown      |             |               |           |             |        |          |         |             |
| Dialogue script      |             |               |           |             |        |          |         |             |
| Shot list            |             |               |           |             |        |          |         |             |
| Prompt generation    |             |               |           |             |        |          |         |             |
| Workflow persistence |             |               |           |             |        |          |         |             |
| Google Flow payload  |             |               |           |             |        |          |         |             |
| Browser startup      |             |               |           |             |        |          |         |             |
| Browser navigation   |             |               |           |             |        |          |         |             |
| Prompt submission    |             |               |           |             |        |          |         |             |
| Asset generation     |             |               |           |             |        |          |         |             |
| Asset download       |             |               |           |             |        |          |         |             |
| Asset validation     |             |               |           |             |        |          |         |             |
| Timeline assembly    |             |               |           |             |        |          |         |             |
| Final video export   |             |               |           |             |        |          |         |             |
| Production report    |             |               |           |             |        |          |         |             |

Bảng này là evidence chính để trả lời câu hỏi:

> Pipeline hiện đã hoạt động thực tế đến bước nào?

---

# 13. PHÂN LOẠI ROOT CAUSE

Mọi lỗi hoặc blocker phải được phân loại:

```text
ARCHITECTURE_GAP
IMPLEMENTATION_MISSING
WIRING_MISSING
CONTRACT_MISMATCH
SCHEMA_INVALID
MODEL_OUTPUT_INVALID
MODEL_UNAVAILABLE
CREDENTIAL_MISSING
QUOTA_EXHAUSTED
BROWSER_SESSION_INVALID
UI_SELECTOR_CHANGED
DEPENDENCY_MISSING
ENVIRONMENT_INCOMPATIBLE
STATE_PERSISTENCE_ERROR
IDEMPOTENCY_ERROR
RETRY_ERROR
TIMEOUT_ERROR
ASSET_INVALID
MEDIA_PROCESSING_ERROR
TEST_HARNESS_ERROR
BASELINE_MUTATION
UNKNOWN
```

Mỗi root cause entry phải có:

```text
issue_id
title
category
severity
affected_stage
symptom
reproduction_command
expected_behavior
actual_behavior
root_cause
evidence
affected_files
temporary_workaround
recommended_fix
blocks_end_to_end
confidence
```

Severity:

```text
CRITICAL
HIGH
MEDIUM
LOW
INFO
```

---

# 14. ARTIFACT BẮT BUỘC

Tạo thư mục:

```text
artifacts/video_production/pipeline_evaluation/
```

Nếu repository đã có convention versioned hoặc phase-based thì sử dụng convention hiện tại, nhưng phải giữ đầy đủ các file dưới đây.

## 14.1. Báo cáo chính

```text
artifacts/video_production/pipeline_evaluation/pipeline_evaluation_report.md
```

Báo cáo phải gồm:

1. Executive summary.
2. Current branch và commit SHA.
3. Environment.
4. Phạm vi kiểm thử.
5. Kiến trúc thực tế phát hiện được.
6. Entry point thực tế.
7. Test matrix.
8. Script generation results.
9. Script quality score.
10. Model/provider results.
11. Orchestration results.
12. Google Flow browser provider results.
13. Asset/video results.
14. Stage-by-stage status.
15. Root-cause analysis.
16. Blockers.
17. Risk assessment.
18. Những phần đã hoạt động thật.
19. Những phần chỉ hoạt động mock hoặc dry-run.
20. Những phần chưa implement.
21. Lộ trình đề xuất tiếp theo.
22. Final verdict.

## 14.2. Báo cáo JSON máy đọc được

```text
artifacts/video_production/pipeline_evaluation/pipeline_evaluation_report.json
```

Schema tối thiểu:

```json
{
  "report_version": "1.0.0",
  "generated_at": "",
  "repository": "",
  "branch": "",
  "git_sha": "",
  "worktree_before": {},
  "worktree_after": {},
  "environment": {},
  "production_case": {},
  "test_summary": {},
  "script_quality": {},
  "stage_matrix": [],
  "model_calls": [],
  "provider_tests": [],
  "browser_tests": [],
  "asset_tests": [],
  "root_causes": [],
  "blockers": [],
  "risks": [],
  "recommended_next_phases": [],
  "final_verdict": ""
}
```

## 14.3. Stage matrix

```text
artifacts/video_production/pipeline_evaluation/stage_matrix.json
artifacts/video_production/pipeline_evaluation/stage_matrix.md
```

## 14.4. Root-cause matrix

```text
artifacts/video_production/pipeline_evaluation/root_cause_matrix.json
artifacts/video_production/pipeline_evaluation/root_cause_matrix.md
```

## 14.5. Script artifacts

```text
artifacts/video_production/pipeline_evaluation/production_case/
├── production_brief.json
├── story_concept.json
├── story_bible.json
├── character_bible.json
├── location_bible.json
├── episode_outline.json
├── beat_sheet.json
├── scene_breakdown.json
├── dialogue_script.json
├── dialogue_script.md
├── shot_list.json
├── generation_prompts.json
├── asset_requirements.json
└── script_quality_report.json
```

Chỉ tạo file cho stage thực sự chạy được. Nếu stage không chạy, ghi rõ trong stage matrix; không tạo output giả.

## 14.6. Runtime evidence

```text
artifacts/video_production/pipeline_evaluation/evidence/
├── command_receipts/
├── logs/
├── stdout/
├── stderr/
├── browser_screenshots/
├── browser_traces/
├── provider_payloads/
├── provider_responses/
├── media_probe/
└── hashes/
```

## 14.7. Evidence manifest

```text
artifacts/video_production/pipeline_evaluation/evidence_manifest.json
```

Mỗi artifact phải có:

```text
path
type
size_bytes
sha256
created_at
producer_command_id
production_id
stage
contains_secret
validation_status
```

Không đưa file chứa secret vào manifest hoặc artifact bundle.

---

# 15. FINAL VERDICT

Chỉ sử dụng một trong các verdict sau:

```text
PIPELINE_END_TO_END_LIVE_VERIFIED
PIPELINE_END_TO_END_DRY_RUN_VERIFIED
SCRIPT_PIPELINE_VERIFIED_VIDEO_GENERATION_BLOCKED
SCRIPT_GENERATION_PARTIAL
PIPELINE_PARTIAL_WITH_BLOCKERS
PIPELINE_NOT_OPERATIONAL
EVALUATION_BLOCKED
```

Quy tắc:

## `PIPELINE_END_TO_END_LIVE_VERIFIED`

Chỉ được dùng khi:

* Brief đã chạy qua toàn bộ pipeline.
* Kịch bản hợp lệ.
* Shot list hợp lệ.
* Google Flow hoặc provider video đã được gọi thật.
* Asset đã được tạo và tải về.
* Video cuối đã được assembly và xác minh bằng media probe.
* Không dùng mock ở đường đi chính.

## `PIPELINE_END_TO_END_DRY_RUN_VERIFIED`

Chỉ được dùng khi:

* Toàn bộ orchestration chạy đến cuối.
* Mọi payload và contract hợp lệ.
* Nhưng provider generation chỉ chạy dry-run.
* Báo cáo phải ghi rõ chưa xác minh generation live.

## `SCRIPT_PIPELINE_VERIFIED_VIDEO_GENERATION_BLOCKED`

Dùng khi:

* Brief → script → scene → shot list → prompt generation chạy thật và hợp lệ.
* Video generation bị chặn bởi browser, credential, quota hoặc provider.

## `SCRIPT_GENERATION_PARTIAL`

Dùng khi:

* Chỉ một phần của quá trình tạo kịch bản chạy được.
* Chưa tạo được shot list hoặc production-ready script.

## `PIPELINE_PARTIAL_WITH_BLOCKERS`

Dùng khi:

* Có nhiều stage chạy được.
* Nhưng chưa đủ điều kiện xác nhận script pipeline hoặc end-to-end pipeline.

## `PIPELINE_NOT_OPERATIONAL`

Dùng khi:

* Entry point không hoạt động.
* Hầu hết stage chưa được wiring hoặc chỉ là scaffold.

## `EVALUATION_BLOCKED`

Dùng khi:

* Không thể thực hiện đánh giá đáng tin cậy do baseline, dependency hoặc môi trường bị hỏng nghiêm trọng.

Không được dùng verdict tích cực nếu evidence không đủ.

---

# 16. KẾ HOẠCH TIẾP THEO

Dựa trên kết quả, xây dựng roadmap ngắn theo thứ tự ưu tiên:

```text
P0 — Blocker bắt buộc sửa trước
P1 — Cần thiết để có script pipeline hoàn chỉnh
P2 — Cần thiết để có video generation live
P3 — Cần thiết để đạt production quality
P4 — Tối ưu hóa và mở rộng
```

Với mỗi mục:

```text
priority
task
affected_modules
reason
acceptance_criteria
required_tests
expected_artifacts
dependency
risk
```

Không đưa ra roadmap chung chung. Mỗi task phải gắn với root cause hoặc gap đã phát hiện trong đợt kiểm thử.

---

# 17. YÊU CẦU VỀ BÁO CÁO CUỐI TERMINAL

Sau khi hoàn thành, in một phần tóm tắt ngắn trong terminal theo mẫu:

```text
VIDEO PRODUCTION PIPELINE EVALUATION COMPLETE

Branch:
Tested SHA:
Worktree clean before:
Worktree clean after:

Script generation status:
Script quality score:
Furthest verified stage:
Google Flow provider status:
Generated image count:
Generated clip count:
Final video produced:

Tests passed:
Tests failed:
Tests blocked:
Tests mock-only:
Tests dry-run:
Tests live:

Critical blockers:
Final verdict:

Primary report:
Stage matrix:
Root-cause matrix:
Evidence manifest:
```

Không thay thế các file báo cáo bằng phần tóm tắt terminal.

---

# 18. THỨ TỰ THỰC HIỆN BẮT BUỘC

Thực hiện theo thứ tự:

1. Ghi baseline và environment.
2. Kiểm tra worktree.
3. Khảo sát kiến trúc và inventory.
4. Xác định entry point.
5. Xác định test commands hiện có.
6. Chạy baseline tests.
7. Tạo production brief chuẩn.
8. Chạy quá trình tạo kịch bản.
9. Validate từng artifact.
10. Chấm điểm chất lượng kịch bản.
11. Chạy orchestration tests.
12. Kiểm tra provider payload.
13. Chạy browser dry-run.
14. Chạy live browser test nếu môi trường cho phép.
15. Validate generated assets.
16. Kiểm tra assembly nếu đã implement.
17. So sánh worktree trước và sau.
18. Xây dựng stage matrix.
19. Xây dựng root-cause matrix.
20. Sinh evidence manifest.
21. Sinh báo cáo Markdown và JSON.
22. Đưa ra final verdict trung thực.

Bắt đầu bằng việc kiểm tra repository hiện tại. Không giả định kết quả từ các báo cáo cũ là vẫn còn đúng. Mọi trạng thái phải được xác minh lại trên current HEAD.
