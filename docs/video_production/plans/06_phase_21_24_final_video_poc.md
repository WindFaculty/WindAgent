# Kế hoạch 06 — Phase 21–24: Final Video PoC

## 1. Mục đích

Kế hoạch này hoàn thiện audio, hậu kỳ, production workspace và chạy một PoC thật có kiểm soát từ ý tưởng đến MP4 30–45 giây. PoC phải chứng minh traceability, resume, human takeover, cost control và quality gates; một video “trông ổn” nhưng thiếu evidence hoặc vượt budget không được coi là pass.

Tài liệu kế thừa [`road_map.md`](../../../road_map.md) và [Kế hoạch 05](05_phase_17_20_orchestration_cost_review.md).

## 2. Kết quả cần đạt

```text
approved shot candidates
      + dialogue/audio intent
      ↓
audio production
      ↓
reproducible FFmpeg post-production
      ↓
Web/Desktop supervision
      ↓
controlled real Flow E2E
      ↓
final MP4 + production report
```

Các gate:

```text
VP21_AUDIO_PIPELINE_VERIFIED
VP22_POST_PRODUCTION_VERIFIED
VP23_PRODUCTION_WORKSPACE_VERIFIED
VP24_E2E_POC_PASSED
```

## 3. Điều kiện bắt đầu

- `VP17` đến `VP20` đã pass.
- Có approved clip/reference set cho fixture và ít nhất một controlled live run.
- Dialogue/narration có stable IDs và shot binding.
- Artifact dependency graph và cost ledger hoạt động.
- FFmpeg/ffprobe có version pin hoặc toolchain manifest.
- API V2, event stream và client runtime hiện có dùng được.
- Người dùng phê duyệt creative brief, maximum credits và thời điểm chạy PoC thật.

## 4. Phạm vi Release 0.1

```text
Thời lượng: 30–45 giây
Scene: 2
Shot: 5–7
Nhân vật: tối đa 2
Bối cảnh: 1–2
Tỷ lệ: 16:9
Candidate/shot: tối đa 2
Flow session: 1
Concurrency: 1
```

Audio trong release này ưu tiên rõ lời và đồng bộ cơ bản. Lip-sync phức tạp, multi-language dubbing và timeline editor nâng cao bị hoãn.

## 5. Branch và evidence

```text
feat/video-production-phase21-audio
feat/video-production-phase22-postproduction
feat/video-production-phase23-workspace
feat/video-production-phase24-e2e
```

Media evidence lớn không được commit tùy tiện nếu repository policy không cho phép. Manifest phải ghi content hash, storage locator, retention và cách truy cập; artifact nhạy cảm cần redaction/access control.

---

# Phase 21 — Dialogue, TTS và audio production

## 6. Mục tiêu

Tạo dialogue/narration track chính xác, có voice consistency, timestamp và mix plan; không phụ thuộc audio do Flow tự sinh.

## 7. Domain model

```text
CharacterVoiceProfile
DialogueTrack
WordTimestamp
SoundEffectCue
MusicCue
AudioMixPlan
```

Mỗi `CharacterVoiceProfile` gắn character ID/revision, không gắn bằng display name. Nếu dùng voice/likeness người thật, phải có rights/consent metadata và approval.

## 8. Workstream

### 8.1 Dialogue preparation

- Chuẩn hóa text nhưng không làm đổi nghĩa/lời thoại locked.
- Tách spoken dialogue, narration và non-verbal cue.
- Xử lý punctuation, abbreviation, number và pronunciation lexicon.
- Ghi language/locale, speaking intent và target duration.
- Text revision tạo audio revision mới và downstream invalidation.

### 8.2 Voice casting

- Chọn voice theo character profile/style, có human approval khi cần.
- Không reuse cùng voice gây nhầm identity nếu policy cấm.
- Provider/model/voice/version và license/terms được ghi.
- Voice preview không trở thành final track nếu chưa approve.

### 8.3 TTS

- Request có dialogue ID, voice profile hash và synthesis parameters.
- Output audio có content hash, sample rate, channel layout và duration.
- Retry bounded, output invalid không publish.
- Cùng request có request hash để tránh duplicate cost.

### 8.4 Alignment

Pipeline:

```text
DialogueLine
→ TTS
→ forced alignment
→ word timestamps
→ shot timing comparison
→ timing adjustment proposal
```

- Alignment confidence thấp chuyển human review.
- Không kéo/nén audio quá policy mà không cảnh báo.
- Nếu lời dài hơn shot, ưu tiên proposal đổi timing/shot, không cắt lời im lặng.

### 8.5 SFX, BGM và mix

- SFX/music có license/provenance.
- Cue gắn timeline/shot và fade intent.
- Dialogue ducking, loudness target và peak ceiling là versioned mix policy.
- BGM thay đổi chỉ invalidate mix/final cut, không invalidate clip.
- Mix output có command/parameter manifest.

### 8.6 Optional lip-sync

Release 0.1 chỉ bật nếu:

- provider/tool được review;
- input/output traceable;
- không phá identity/quality;
- có separate candidate review;
- không làm PoC phụ thuộc bắt buộc.

Nếu không đạt, dùng audio replacement/alignment đơn giản và ghi limitation.

## 9. Kiểm thử

- Multi-character voice mapping không tráo.
- Unicode/Vietnamese pronunciation fixture.
- Empty/overlong line.
- TTS timeout/invalid file.
- Alignment confidence thấp.
- Dialogue dài hơn shot.
- SFX/BGM license unknown.
- Loudness/peak technical checks.
- Dialogue change invalidates đúng audio/mix/final artifacts.

## 10. Deliverables và gate

```text
docs/video_production/audio/
├── voice_profile_policy.md
├── tts_provider_contract.md
├── alignment_policy.md
├── mix_policy.md
└── audio_rights_and_provenance.md

artifacts/video_production/phase_21/
├── dialogue_fixture_matrix.json
├── tts_contract_receipt.json
├── alignment_receipt.json
├── loudness_receipt.json
├── provenance_receipt.json
└── phase_verdict.json
```

`VP21_AUDIO_PIPELINE_VERIFIED` chỉ pass khi dialogue/voice mapping đúng, alignment/timing issue không bị che, final mix qua technical checks và mọi audio asset có provenance.

---

# Phase 22 — FFmpeg post-production

## 11. Mục tiêu

Tạo final video reproducibly từ approved clips/audio/subtitle bằng explicit render plan, bounded subprocess và deterministic verification.

## 12. Post-production model

```text
EditDecisionList
TransitionPlan
SubtitleTrack
AudioMixPlan
EncodingProfile
PostProductionJob
FinalDeliverable
```

Edit decision list trỏ content hash của input, không chỉ file path.

## 13. Workstream

### 13.1 Tool boundary

- FFmpeg/ffprobe invocation dùng argv, không shell interpolation.
- Pin/ghi version và build configuration.
- Timeout/cancel giết process tree.
- Path nằm trong controlled workspace/artifact store.
- Log command đã redact; không nhận filter/script tùy ý từ model.

### 13.2 Normalize input

Trước concatenate:

- validate video/audio stream;
- normalize time base, frame rate, resolution, pixel format và audio sample rate theo profile;
- phát hiện rotation metadata;
- không silently stretch/crop ngoài aspect policy;
- tạo proxy preview riêng, không nhầm với final.

### 13.3 Assembly

Hỗ trợ:

- concatenate shots;
- transition versioned/bounded;
- audio replacement/mixing;
- subtitle;
- aspect conversion;
- loudness normalization;
- thumbnail;
- metadata;
- final encoding.

Mọi filter graph hoặc intermediate artifact được derive từ typed render plan.

### 13.4 Reproducibility

Render receipt ghi:

```text
input artifact hashes
edit decision list hash
FFmpeg/ffprobe version
argv/filter plan
encoding profile version
environment-relevant settings
output SHA-256
```

Nếu byte-identical output không bảo đảm do encoder/platform, policy phải định nghĩa mức reproducibility semantic và các field được phép khác.

### 13.5 Verification

- `ffprobe` parse thành structured receipt.
- Duration nằm trong approved tolerance.
- Codec/container/resolution/frame rate đúng profile.
- Có audio stream khi required.
- Decode sample frames đầu/giữa/cuối.
- Không black/truncated ending theo detector đã định nghĩa.
- Loudness/peak đúng mix policy.
- Subtitle/timeline bounds hợp lệ.
- Final SHA-256 và thumbnail/proxy relationships.

Final artifact chỉ publish sau verification; failed output giữ quarantine evidence.

## 14. Kiểm thử

- Mixed codecs/frame rates/resolutions.
- Missing audio/video stream.
- Corrupt/truncated clip.
- Transition duration vượt clip.
- Subtitle ngoài timeline/invalid encoding.
- Cancel/crash trong render.
- Output 0 byte hoặc `ffprobe` invalid.
- Repeat render theo reproducibility policy.
- BGM/audio revision invalidates final cut đúng cách.

## 15. Deliverables và gate

```text
docs/video_production/postproduction/
├── edit_decision_list.md
├── encoding_profiles.md
├── ffmpeg_safety_policy.md
└── final_media_verification.md

artifacts/video_production/phase_22/
├── render_fixture_matrix.json
├── ffmpeg_command_receipts/
├── ffprobe_verification_receipt.json
├── reproducibility_report.json
└── phase_verdict.json
```

`VP22_POST_PRODUCTION_VERIFIED` chỉ pass khi fixture render reproducibly theo policy, invalid input/output fail closed và final artifact chỉ publish sau verification.

---

# Phase 23 — Web/Desktop production workspace

## 16. Mục tiêu

Cho người dùng quan sát, approve, pause/resume và takeover production workflow qua API V2/event stream hiện có, không tạo backend hoặc state authority mới.

## 17. Thiết kế trải nghiệm

Các màn hình roadmap được tổ chức thành lát dọc:

### Lát 1 — Project và creative authority

- Projects.
- Creative Brief.
- Screenplay Editor.
- Character Bible.
- Location Bible.

### Lát 2 — Director và generation

- Storyboard.
- Shot Board.
- Continuity Inspector.
- Flow Session.
- Generation Queue.

### Lát 3 — Review và delivery

- Candidate Comparison.
- Cost Ledger.
- Timeline.
- Final Review.

Release 0.1 có thể dùng route/panel thay vì editor timeline nâng cao, nhưng mọi approval/human-action/cost state bắt buộc phải quan sát và thao tác được.

## 18. Workstream

### 18.1 API

- Mở rộng API V2 routers/services hiện có.
- Request/response schema versioned.
- Mutating command có idempotency key và optimistic concurrency/revision.
- Authorization cho approve, cost approval, cancel, human resolution và publish.
- UI không ghi trực tiếp database/storage.

### 18.2 Realtime

- Dùng SSE/WebSocket/event client hiện có.
- Event có sequence/cursor hoặc cơ chế resume.
- Reconnect không duplicate notification/action.
- UI phục hồi state bằng snapshot API + event replay.
- Không coi connection alive là bằng chứng workflow healthy.

### 18.3 Approval và command UX

- Hiển thị target revision/hash, cost và impact trước approve.
- Confirmation cho cancel/archive/publish/payment-related handoff.
- Disable stale approval khi underlying revision đổi.
- Human-action panel hướng dẫn takeover/resume.
- Không tự động submit/retry do UI reconnect.

### 18.4 Candidate comparison

- Hiển thị tất cả candidate, technical result, per-dimension scores, blocking defects và confidence.
- Cho approve/reject/override với reason.
- Không chỉ hiển thị aggregate score.
- Media URL dùng authorized delivery, không lộ filesystem path.

### 18.5 Cost và observability

- Estimate, reserve, observed debit, remaining budget.
- Session/project/job state.
- Retry/attempt và current blocker.
- Evidence link đã redact.
- Known UI drift/account warning.

### 18.6 Desktop

- Tái sử dụng web client/contracts.
- Browser takeover mở đúng headed session theo policy, không expose profile path/token.
- Desktop build không bundle upstream VideoClaw/ViMax.
- Restart desktop không làm mất server-side workflow state.

## 19. Kiểm thử

- API contract và authorization.
- Stale revision/approval.
- SSE/WebSocket disconnect/reconnect/replay.
- Duplicate event và state recovery.
- Candidate review/override.
- Cost approval và over-budget disabled action.
- Human takeover/resume.
- Cancel/publish confirmation.
- Frontend unit/build và desktop unit/build.
- Accessibility cho core approval/review flow.

## 20. Deliverables và gate

```text
docs/video_production/workspace/
├── information_architecture.md
├── api_contract.md
├── event_projection.md
├── approval_ux.md
└── desktop_takeover.md

artifacts/video_production/phase_23/
├── api_contract_receipt.json
├── realtime_recovery_receipt.json
├── web_test_receipt.json
├── web_build_receipt.json
├── desktop_test_receipt.json
├── desktop_build_receipt.json
└── phase_verdict.json
```

`VP23_PRODUCTION_WORKSPACE_VERIFIED` chỉ pass khi người dùng hoàn thành core approval/review/human-control flow, reconnect không mất state và web/desktop không tạo authority mới.

---

# Phase 24 — PoC E2E có kiểm soát

## 21. Mục tiêu

Chạy một production project thật trong đúng scope Release 0.1 và phát hành evidence đủ để kết luận toàn chuỗi hoạt động, không chỉ từng component riêng lẻ.

## 22. Chuẩn bị PoC

### 22.1 Freeze input

Trước run:

- creative brief/revision đã approve;
- 2 scene, 5–7 shot, tối đa 2 character và 1–2 location;
- 16:9, target 30–45 giây;
- dialogue/voice/style constraints;
- candidate limit 2;
- approved maximum credits và retry reserve;
- one Flow account/session/project;
- release candidate SHA và tool versions.

Không thay input sau freeze mà không tạo PoC run/revision mới.

### 22.2 Preflight

- Full mocked E2E pass trên candidate SHA.
- Browser/session health và account signed in.
- Flow project mapping đúng.
- Credit state đủ và đã approve.
- FFmpeg/ffprobe available.
- Storage capacity và retention path.
- Human operator sẵn sàng takeover.
- No secret in planned evidence/log path.

### 22.3 Runbook

```text
1. CREATE_PROJECT / freeze run manifest
2. idea → concepts → selected concept
3. screenplay → approval/lock
4. character/location bibles → references → approval
5. cinematic plan → shot graph/continuity → approval/lock
6. cost estimate → approval/reserve
7. Flow image generation → candidate review
8. Flow video generation, one job at a time
9. technical/VLM/cross-shot review
10. TTS/alignment/audio mix
11. FFmpeg assembly
12. final verification
13. final-cut approval
14. publish final deliverable + report
```

Mỗi bước cập nhật checkpoint/evidence trước khi chuyển bước.

## 23. Bài kiểm tra recovery bắt buộc trong PoC

Thực hiện có kiểm soát ít nhất:

1. Đóng browser sau một generation đã submit và trước download.
2. Xác nhận workflow chuyển pause/recovery phù hợp.
3. Mở lại/reattach session.
4. Reconcile đúng existing job.
5. Tiếp tục download/review mà không submit trùng.

Không cố tình phá account/payment hoặc tạo CAPTCHA.

## 24. Cách tính acceptance

### Traceability

Mỗi final frame/audio segment truy được:

```text
final deliverable
→ edit decision list
→ approved shot/audio artifacts
→ generation/TTS request
→ prompt/reference hashes
→ cinematic plan/continuity
→ screenplay/package revision
```

### Tỷ lệ tự động

```text
automation_rate =
shots completed without manual media editing
/ total planned shots
```

Approval, login/takeover và deliberate browser-recovery step không tính là manual media editing. Tỷ lệ phải đạt ít nhất 80%.

### Character consistency

- Không tráo character ID/reference.
- Blocking identity defect ở bất kỳ approved shot nào làm PoC fail.
- Accepted minor variation phải có human override và report, không được ẩn.

### Budget

```text
observed/ledger-adjusted credits
≤ approved maximum credits
```

Unknown debit hoặc unreconciled ledger chặn verdict.

## 25. Acceptance gate

`VP24_E2E_POC_PASSED` chỉ pass khi:

1. Tất cả artifact truy vết được.
2. Không duplicate submit.
3. Browser recovery test pass.
4. Human takeover có thể dùng.
5. Không tráo character.
6. Automation rate ≥ 80%.
7. Final MP4 vượt full verification.
8. Budget không vượt approval và ledger đã reconcile.
9. Không false PASS trong review.
10. Không runtime import từ upstream quarantine.
11. Web/Desktop hiển thị đúng trạng thái/approval của run.
12. Final-cut approval gắn đúng final artifact hash.

Một mục fail tạo verdict `BLOCKED`/`FAILED`; không dùng “partial success” để phát hành gate.

## 26. Final PoC artifacts

```text
artifacts/video_production/phase_24/
├── poc_run_manifest.json
├── input_revision_manifest.json
├── workflow_event_receipt.json
├── flow_job_receipts/
├── browser_recovery_receipt.json
├── candidate_review_report.json
├── audio_production_receipt.json
├── postproduction_receipt.json
├── final_media_verification.json
├── cost_report.json
├── traceability_graph.json
├── automation_rate.json
├── production_report.md
└── phase_verdict.json
```

Final MP4/proxy/thumbnail/subtitle/audio stems được content-addressed và liên kết từ manifest.

## 27. Rollback và cleanup sau PoC

- Không xóa evidence khi run fail.
- Release reservation chưa dùng được giải phóng/reconcile.
- Temporary/quarantine files được cleanup theo policy.
- Browser session được đóng hoặc giữ theo explicit session policy.
- Flow project không bị xóa tự động nếu cần audit/recovery.
- Failed/unused media không publish làm final.
- Finding tạo issue/risk cho Phase 25–27.

## 28. Handoff sang hardening

Handoff gồm:

- candidate/release SHA;
- final PoC verdict và complete evidence manifest;
- recovery timings/observations;
- defect, flaky selector và manual intervention inventory;
- cost estimate-vs-observed;
- security/privacy observations;
- known limitations;
- exact failure scenarios chưa thử;
- release blockers.

## 29. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Audio dài hơn video | Forced alignment + timing proposal trước final render |
| FFmpeg command không reproducible | Typed render plan, pinned version và receipt |
| UI thành source of truth | API V2 commands/projections; server giữ authority |
| PoC đổi input giữa run | Freeze manifest và revision mới khi đổi |
| Demo đẹp nhưng thiếu evidence | Acceptance gate kiểm tra traceability/ledger/recovery |
| Live run vượt credit | Candidate/concurrency cap, reserve và stop policy |
| Manual edit làm sai automation rate | Định nghĩa numerator/denominator trước run |
| Final artifact sai nhưng được approve | Verification trước approval, approval gắn output hash |

## 30. Checklist đóng kế hoạch

- [ ] Audio pipeline đúng voice/dialogue và qua technical checks.
- [ ] Final render reproducible theo policy và vượt ffprobe/decoder checks.
- [ ] Web/Desktop hỗ trợ approval, review, cost và human takeover.
- [ ] PoC input/cost/candidate scope đã freeze.
- [ ] Browser recovery không gây duplicate submit.
- [ ] Automation rate ≥ 80%.
- [ ] Final MP4, cost và traceability receipts đầy đủ.
- [ ] `VP21` đến `VP24` đều `PASSED`.
- [ ] Hardening handoff ghi đủ defect và limitation.
