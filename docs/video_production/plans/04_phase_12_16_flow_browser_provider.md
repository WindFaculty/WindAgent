# Kế hoạch 04 — Phase 12–16: Flow Browser Provider

## 1. Mục đích

Kế hoạch này triển khai Google Flow như một `MediaGenerationProviderPort` dựa trên GUI trình duyệt hợp lệ. Provider nhận `GenerationRequest`, thao tác bằng bounded actions, trả media artifact/job state và dừng để người dùng xử lý khi gặp login, CAPTCHA, account verification, terms hoặc payment.

Provider không reverse-engineer endpoint riêng, không intercept token, không bypass challenge và không nắm project/task/artifact/cost authority của WindAgent.

Tài liệu kế thừa [`road_map.md`](../../../road_map.md) và [Kế hoạch 03](03_phase_08_11_director_layer.md).

## 2. Kết quả cần đạt

```text
GenerationRequest
      ↓
bounded browser session
      ↓
Flow project + generation job
      ↓
downloaded candidates + evidence
      ↓
WindAgent validation/storage
```

Các gate:

```text
VP12_BROWSER_RUNTIME_VERIFIED
VP13_FLOW_NAVIGATION_VERIFIED
VP14_FLOW_IMAGE_GENERATION_VERIFIED
VP15_FLOW_VIDEO_GENERATION_VERIFIED
VP16_FLOW_HUMAN_CONTROL_VERIFIED
```

## 3. Điều kiện bắt đầu

- `VP11_FLOW_REQUEST_COMPILER_VERIFIED` đã pass.
- Có provider port, valid/invalid request fixtures và request hash algorithm.
- Có headed Chrome/Chromium phù hợp và phiên bản `agent-browser` được pin.
- Live test chỉ dùng tài khoản hợp lệ do người dùng kiểm soát.
- Có explicit approval trước test có thể submit generation/tiêu credits.
- Có chính sách lưu browser profile, screenshot, prompt và downloaded media.

## 4. Phạm vi Release 0.1

- Một Flow account hợp lệ.
- Một persistent browser session/profile.
- Một production project tại một thời điểm.
- Concurrency bằng 1.
- Image operations và video operations trong roadmap.
- Download, inspection, resume và human takeover.
- Mock/fixture contract tests trong PR; live smoke theo manual/nightly policy.

Ngoài phạm vi: multi-account, proxy rotation, cloud browser, headless Flow, private API, tự mua credit và né quota.

## 5. Vị trí kiến trúc

Repository đã có browser primitives tại:

```text
tools/windagent_tools/browser/
├── agent_browser.py
├── tool.py
├── state_manager.py
└── state_encryption.py
```

Phase 12 phải mở rộng hoặc tái sử dụng boundary này, không tạo browser runtime song song. Các module roadmap như `runtime.py`, `session.py`, `command_runner.py`, `snapshot_parser.py`, `action_policy.py`, `evidence_capture.py`, `healthcheck.py` chỉ được thêm khi trách nhiệm chưa tồn tại trong code hiện hành.

Flow-specific code:

```text
tools/windagent_tools/google_flow/
├── provider.py
├── navigation.py
├── state_machine.py
├── project_manager.py
├── image_generation.py
├── video_generation.py
├── candidate_downloader.py
├── human_control.py
└── selectors/
```

`providers/` không phụ thuộc `tools/google_flow`. Composition root inject provider implementation qua core port.

## 6. Branch và evidence

```text
feat/video-production-phase12-browser-runtime
feat/video-production-phase13-flow-navigation
feat/video-production-phase14-flow-images
feat/video-production-phase15-flow-video
feat/video-production-phase16-human-control
```

Live evidence phải redact account identifier, cookie, token, payment data, local profile path và nội dung riêng tư ngoài phạm vi test.

---

# Phase 12 — Browser runtime foundation

## 7. Mục tiêu

Cung cấp browser worker bền vững, bounded, có health check/evidence/cancel semantics nhưng chưa submit generation thật.

## 8. Workstream

### 8.1 Upstream runtime pin

- Pin version `agent-browser` và lock/checksum theo cơ chế build hiện có.
- Ghi browser/driver compatibility matrix cho Windows và CI platform.
- Xác minh license và update policy.
- Không tự tải executable mới trong production ngoài update flow được duyệt.

### 8.2 Process boundary

Command runner:

- dùng argv, không shell interpolation;
- timeout mọi command;
- giới hạn stdout/stderr;
- phân loại binary missing, start failure, timeout, non-zero exit và policy violation;
- kill process tree khi cancel/timeout;
- không truyền secret qua argv nếu có kênh an toàn khác;
- redact log trước khi publish event.

### 8.3 Session và profile

- Một WindAgent browser session ID ánh xạ đúng một profile.
- Profile path không đi qua message queue hoặc domain event.
- Profile at rest dùng encryption/control hiện có.
- Lock ngăn hai worker dùng cùng profile.
- Session metadata gồm owner, created/last health time, state và lease.
- Close/reopen không làm mất job mapping đã lưu ở WindAgent.

### 8.4 Action policy

Allow:

- open URL trong allowlist;
- accessibility snapshot;
- semantic click/fill/select/upload;
- screenshot;
- bounded wait;
- download qua controlled path.

Deny hoặc yêu cầu confirmation:

- arbitrary `eval`;
- navigation ngoài domain allowlist;
- file upload ngoài approved asset store;
- payment/terms/destructive action;
- cookie export;
- arbitrary filesystem read;
- command do model tạo không qua typed operation.

### 8.5 Evidence và health

Mỗi bounded action ghi:

```text
action_id
session_id
operation
target_semantics
started_at / finished_at
result_state
redacted_screenshot_hash
snapshot_hash
error_class
```

Health check xác định process alive, browser reachable, current domain allowed, profile lock valid và session không ở human-required state.

## 9. Kiểm thử

- Command timeout và process-tree cleanup.
- Cancel giữa action.
- Session/profile lock collision.
- Domain allowlist và redirect ra ngoài.
- Arbitrary eval, cookie logging và unapproved upload bị chặn.
- Screenshot/evidence redaction.
- Worker restart và session reattach bằng fake browser.
- Health state phân loại chính xác.

## 10. Gate

`VP12_BROWSER_RUNTIME_VERIFIED` chỉ pass khi runtime có bounded action policy, persistent session, timeout/cancel/cleanup, redacted evidence và không cần Flow production để test.

---

# Phase 13 — Flow navigation và project management

## 11. Mục tiêu

Tự động hóa navigation deterministic đến trạng thái `SUBMIT_READY`, chưa submit generation trong acceptance chính của phase.

## 12. UI state machine

```text
UNKNOWN
SIGNED_OUT
READY
PROJECT_OPEN
EDITOR_READY
CONFIGURED
SUBMIT_READY
GENERATING
RESULT_READY
ERROR
HUMAN_ACTION_REQUIRED
```

Mỗi transition cần:

- observable precondition;
- bounded action;
- observable postcondition;
- timeout;
- retry classification;
- evidence;
- recovery/human state.

Không suy trạng thái chỉ từ một selector; dùng URL + semantic region + visible control khi có thể.

## 13. Workstream

### 13.1 Session/account inspection

- Mở Flow domain canonical.
- Phân biệt signed-out, ready, challenge và error.
- Không nhập credential từ log/config không được phê duyệt.
- Signed-out/challenge chuyển Phase 16 human state.

### 13.2 Project mapping

WindAgent lưu mapping:

```text
project_id
production_revision_id
flow_project_id
flow_project_url_or_stable_locator
browser_session_id
last_verified_at
mapping_status
```

- Mở project hiện có trước khi tạo mới.
- Xác nhận đúng project bằng ít nhất hai tín hiệu.
- Không dùng display name làm identity duy nhất.
- Project mất/xóa chuyển typed failure; không tự tạo project thay thế rồi tiếp tục.

### 13.3 Configuration

Hỗ trợ đến `SUBMIT_READY`:

1. mở create workspace;
2. chọn generation mode;
3. upload reference theo binding plan;
4. điền compiled prompt;
5. chọn model, duration, aspect ratio;
6. đọc lại visible config;
7. chụp pre-submit evidence.

### 13.4 Selector strategy

Ưu tiên:

```text
accessibility role
label
visible text
stable URL
semantic region
```

CSS class, DOM index và coordinate không được là selector chính. Selector catalog có version, locale assumption, confidence và fallback. Fallback không được click control phá hủy hoặc thanh toán.

### 13.5 Drift detection

- Snapshot fixture cho các state quan trọng.
- Khi selector không còn unique hoặc postcondition sai, dừng ở `ERROR`/`HUMAN_ACTION_REQUIRED`.
- Chụp sanitized snapshot/screenshot cho debug.
- Không retry click mù.

## 14. Kiểm thử

- Fixture/mocked UI cho từng state và transition.
- Signed-out, wrong project, missing control, duplicate label và locale mismatch.
- Upload đúng approved file, unapproved path bị chặn.
- Pre-submit config read-back khớp request.
- Selector drift fail closed.
- Live navigation smoke dừng trước submit.

## 15. Gate

`VP13_FLOW_NAVIGATION_VERIFIED` chỉ pass khi adapter đi từ ready đến `SUBMIT_READY`, xác nhận đúng project/config bằng observable state và không submit trong navigation test.

---

# Phase 14 — Image generation qua Flow

## 16. Mục tiêu

Thực hiện image generation/edit operations, tải mọi candidate, kiểm tra file và đưa candidate vào WindAgent review/approval.

## 17. Operations

```text
CREATE_CHARACTER_REFERENCE
CREATE_LOCATION_REFERENCE
CREATE_PROP_REFERENCE
CREATE_STORYBOARD_FRAME
CREATE_FIRST_FRAME
CREATE_LAST_FRAME
EDIT_IMAGE
UPSCALE_IMAGE
```

Mỗi operation ánh xạ từ typed request sang navigation/configuration, không nhận raw browser instruction.

## 18. Workstream

### 18.1 Pre-submit guard

Trước click submit:

- request/schema/hash hợp lệ;
- reference approved và upload hash khớp;
- project/session mapping healthy;
- operation được provider capability hỗ trợ;
- candidate limit xác định;
- cost/quota policy tạm thời cho phép hoặc explicit test approval;
- pre-submit screenshot/evidence tồn tại.

### 18.2 Submit và observe

- Ghi action/job record trước hoặc atomically với submit intent.
- Click submit đúng một lần theo idempotency token nội bộ.
- Xác định transition sang generating/result/error.
- Poll có backoff và deadline; browser đóng không tạo submit mới.
- UI không rõ trạng thái chuyển `UNKNOWN_REQUIRES_RECONCILIATION`.

### 18.3 Candidate acquisition

Với từng candidate:

- định danh stable trong phạm vi job;
- download vào quarantine;
- hash, MIME/decode/dimension validation;
- lưu screenshot/result metadata;
- publish vào canonical asset store atomically;
- liên kết request hash và Flow project/job.

Không mặc định chọn candidate đầu.

### 18.4 Review và approval

- Deterministic file validity trước VLM.
- VLM chấm prompt compliance và identity.
- Character master luôn cần human approval trong Release 0.1.
- Reject giữ reason/evidence và không bind tự động.
- Re-generation tạo attempt/job mới nhưng giữ causal link.

## 19. Kiểm thử và gate

- Mock submit tạo 0/1/n candidates.
- Duplicate result và repeated inspection.
- Download fail/0 byte/wrong MIME.
- Invalid candidate không vào approved store.
- VLM low confidence → human review.
- Character master không auto-approve.
- Live controlled image smoke nếu có approval.

`VP14_FLOW_IMAGE_GENERATION_VERIFIED` pass khi các operation trong phạm vi có contract test, candidate được tải/validate/truy vết và approval fail closed.

---

# Phase 15 — Video generation qua Flow

## 20. Mục tiêu

Tạo clip theo shot plan, quản lý durable job record và bảo đảm retry/resume không submit trùng.

## 21. Operations

```text
TEXT_TO_VIDEO
FRAMES_TO_VIDEO
INGREDIENTS_TO_VIDEO
VIDEO_EXTENSION
VIDEO_TO_VIDEO
```

## 22. Durable job model

```json
{
  "generation_id": "...",
  "project_id": "...",
  "revision_id": "...",
  "shot_id": "...",
  "provider": "google_flow_browser",
  "request_hash": "...",
  "submitted_at": "...",
  "browser_session_id": "...",
  "flow_project_id": "...",
  "status": "GENERATING",
  "attempt": 1
}
```

Status tối thiểu:

```text
PREPARED
SUBMITTING
GENERATING
RESULT_READY
DOWNLOADING
COMPLETED
FAILED_RETRYABLE
FAILED_TERMINAL
UNKNOWN_REQUIRES_RECONCILIATION
HUMAN_ACTION_REQUIRED
CANCELLED
```

## 23. Workstream

### 23.1 Idempotency và reconciliation

Trước submit:

```text
lookup request_hash + provider + project mapping
├── COMPLETED → reuse candidate set
├── active → inspect/resume
├── UNKNOWN → reconcile, never blind resubmit
├── failed retryable + budget → new attempt
└── missing → create PREPARED record
```

Persist `SUBMITTING` intent trước click và evidence ngay sau observable transition. Crash giữa hai bước luôn vào reconciliation.

### 23.2 Mode validation

- Frames-to-video: first/last frame approved, correct media type/hash.
- Ingredients-to-video: tất cả ingredient/reference bindings hợp lệ.
- Extension: predecessor clip approved và continuity state đúng.
- Video-to-video: source clip và transformation intent rõ.
- Duration/aspect/model nằm trong compiled request/policy.

### 23.3 Result inspection và download

- Poll bounded, có deadline/backoff.
- Download từng candidate.
- `ffprobe`/decoder kiểm tra video stream, duration, resolution, frame rate.
- Candidate invalid không được `COMPLETED`.
- Job `COMPLETED` chỉ sau atomic artifact publish và relationship record.

### 23.4 Cancel/retry

- Cancel WindAgent ngừng action/poll; không khẳng định đã cancel provider nếu UI không chứng minh.
- Retry tạo attempt mới, không overwrite receipt cũ.
- Terminal policy lỗi account/payment/safety không tự retry.
- Browser/session failure sau submit ưu tiên inspect lại cùng Flow project.

## 24. Kiểm thử và gate

- Crash trước/giữa/sau submit intent.
- Repeated command với cùng request hash.
- Existing completed/active/unknown job.
- Browser close sau submit và resume inspection.
- Invalid/no-video-stream result.
- Mode input validation.
- Bounded retry và cancellation semantics.
- Một live clip smoke có explicit cost approval.

`VP15_FLOW_VIDEO_GENERATION_VERIFIED` chỉ pass khi không có duplicate submit trong failure matrix, job/artifact trace đầy đủ và video candidate qua technical validation.

---

# Phase 16 — Human intervention và account safety

## 25. Mục tiêu

Biến các tình huống cần con người thành trạng thái durable, quan sát được và resume được, thay vì cố vượt challenge hoặc retry vô hạn.

## 26. Human states

```text
HUMAN_LOGIN_REQUIRED
HUMAN_CAPTCHA_REQUIRED
HUMAN_ACCOUNT_VERIFICATION_REQUIRED
HUMAN_TERMS_ACCEPTANCE_REQUIRED
HUMAN_PAYMENT_CONFIRMATION_REQUIRED
```

Record tối thiểu:

```text
human_action_id
session_id
project_id
generation_id
reason
detected_at
safe_resume_state
redacted_evidence
status
resolved_by / resolved_at
```

## 27. Workstream

### 27.1 Detection

- Dùng semantic text/region/URL và negative absence của expected state.
- Không OCR hoặc suy đoán để tự giải CAPTCHA.
- Payment/terms/destructive confirmation luôn human-required.
- Unknown account challenge fail closed.

### 27.2 Pause và takeover

- Dừng scheduler action cho session.
- Giữ headed browser/profile hợp lệ.
- Hiển thị lý do và bước người dùng cần làm, không hiện secret.
- Không phát sinh click/fill trong vùng challenge.
- Có timeout/lease nhưng không tự đóng nếu làm mất khả năng takeover mà không có policy.

### 27.3 Resume

Sau khi người dùng báo hoàn tất:

1. chạy health check;
2. xác nhận challenge không còn;
3. xác nhận account/project đúng;
4. reconcile active job;
5. resume từ safe state;
6. ghi audit record.

Không resume trực tiếp bằng cách lặp lại submit.

### 27.4 Account safety

- Rate/concurrency limit.
- Exponential backoff có ceiling.
- Không fingerprint spoofing, proxy/account rotation hoặc quota evasion.
- Không tự mua/nạp credit.
- Không log screenshot chứa account/payment data chưa redact.
- Session bị block nhiều lần chuyển terminal/manual review.

## 28. Kiểm thử và gate

- Fixture cho từng human state.
- Challenge xuất hiện trước submit, sau submit và khi download.
- Scheduler pause, không phát sinh action mới.
- Human resolve → health/reconcile → resume.
- Payment/terms không thể auto-confirm.
- Screenshot/audit redaction.
- Retry ceiling và session circuit breaker.

`VP16_FLOW_HUMAN_CONTROL_VERIFIED` chỉ pass khi mọi challenge trong phạm vi chuyển đúng human state, không có bypass path và resume không duplicate submit.

## 29. Test strategy tổng thể

### PR CI

- Browser process fake.
- Snapshot/state-machine fixtures.
- Selector contract tests.
- Mock Flow UI.
- Provider port contract.
- Idempotency/reconciliation.
- Security/action policy negative tests.

### Nightly/manual

- Authenticated navigation smoke.
- Session health.
- Project open/configuration.
- Có thể dừng trước submit để không tiêu credit.

### Controlled real-credit

- Một image generation và một short video generation.
- Chỉ sau approval về account, prompt và maximum cost.
- Evidence được redact và lưu theo retention policy.

Live test failure do UI drift không được sửa selector mù trong cùng run; tạo drift report và review.

## 30. Evidence cuối milestone

```text
artifacts/video_production/flow_provider/
├── browser_runtime_manifest.json
├── selector_catalog_version.json
├── provider_capability_matrix.json
├── idempotency_failure_matrix.json
├── human_control_matrix.json
├── mocked_contract_receipt.json
├── live_smoke_receipt.json
└── known_ui_assumptions.md
```

## 31. Handoff sang Phase 17–20

Handoff gồm:

- provider capability matrix;
- durable job/status/failure catalog;
- request-hash idempotency behavior;
- session/project mapping contract;
- candidate artifact metadata;
- human-action event contract;
- live/mock distinction trong evidence;
- rate/concurrency limits;
- known selector/UI assumptions.

Orchestration không được điều khiển raw browser action; chỉ gọi provider operations và phản ứng với typed state/event.

## 32. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Flow UI thay đổi | Semantic selector, state assertions, drift fail closed |
| Click submit trùng sau crash | Persist intent + request hash + reconciliation |
| Cookie/profile lộ | Encryption, path isolation, redaction, không queue profile |
| Automation vượt challenge | Explicit human states và deny policy |
| Wrong project | Stable mapping + two-signal verification |
| Candidate invalid nhưng job pass | Decode/ffprobe trước atomic publish |
| Live test tiêu credit ngoài ý muốn | Pre-submit approval và bounded candidate/concurrency |
| Browser runtime bị nhân đôi | Mở rộng package browser hiện có |

## 33. Checklist đóng kế hoạch

- [ ] Browser runtime bounded và recoverable.
- [ ] Navigation đạt `SUBMIT_READY` bằng semantic state.
- [ ] Image candidates được validate và review.
- [ ] Video jobs idempotent qua crash/retry.
- [ ] Human challenges không có bypass path.
- [ ] Mock tests chạy trong PR; live receipt ghi rõ phạm vi.
- [ ] `VP12` đến `VP16` đều `PASSED`.
- [ ] Orchestration handoff chỉ dùng typed provider contract.
