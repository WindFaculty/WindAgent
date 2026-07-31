# Kế hoạch 07 — Phase 25–27: Hardening và Release

## 1. Mục đích

Kế hoạch này biến PoC đã pass thành Release 0.1 có thể phát hành có kiểm soát. Ba lớp chứng nhận bắt buộc là:

1. recovery đúng dưới failure injection;
2. security/privacy fail closed;
3. CI và release evidence đầy đủ trên đúng candidate SHA.

Tài liệu kế thừa [`road_map.md`](../../../road_map.md) và [Kế hoạch 06](06_phase_21_24_final_video_poc.md).

## 2. Kết quả cần đạt

```text
VP24 E2E PoC
   ↓
reliability / chaos certification
   ↓
security / privacy certification
   ↓
CI matrix + controlled real-credit release test
   ↓
VIDEO_PRODUCTION_PLATFORM_VERIFIED
READY_FOR_CONTROLLED_RELEASE
```

Gate:

```text
VP25_RECOVERY_AND_CHAOS_VERIFIED
VP26_SECURITY_VERIFIED
VIDEO_PRODUCTION_PLATFORM_VERIFIED
READY_FOR_CONTROLLED_RELEASE
```

## 3. Điều kiện bắt đầu

- `VP24_E2E_POC_PASSED` trên candidate lineage rõ ràng.
- PoC evidence, defect inventory, cost report và known limitations đầy đủ.
- Có môi trường test cô lập; chaos/security test không dùng dữ liệu hoặc account production không được phép.
- Có backup/restore cho database và browser/session test profile.
- Có release owner, security reviewer và người phê duyệt real-credit test.
- Các thay đổi user-owned/unrelated trong worktree được bảo vệ.

## 4. Nguyên tắc

- Hardening sửa defect ở branch riêng; sửa code sau test làm candidate SHA cũ mất hiệu lực.
- Chaos test không được phá dữ liệu ngoài project/session test.
- Security test dùng safe fixture; không phát tán secret hoặc malicious payload ra ngoài allowlist.
- Không hạ threshold/gate để phù hợp kết quả.
- Known limitation chỉ được chấp nhận nếu có impact, mitigation, owner và release decision.
- Live Flow không chạy trong mọi PR.

## 5. Branch và evidence

```text
feat/video-production-phase25-reliability
feat/video-production-phase26-security
feat/video-production-phase27-release
```

Mỗi fix cần:

- defect/finding ID;
- failing reproduction;
- implementation diff;
- regression test;
- rerun scope;
- candidate SHA mới;
- updated risk/evidence manifest.

---

# Phase 25 — Reliability, chaos và failure injection

## 6. Mục tiêu

Chứng minh system không tạo duplicate side effect, không mất durable state, không publish artifact sai và có recovery/human outcome rõ ràng khi process, browser, network, provider hoặc database thất bại.

## 7. Failure-injection harness

Harness cần:

- chọn injection point theo workflow/event/action ID;
- arm/disarm rõ ràng;
- giới hạn đúng test project/session;
- timeout toàn run;
- lưu pre-state/post-state;
- tự thu thập DB/event/job/artifact/cost evidence;
- cleanup có kiểm tra;
- không dùng lệnh destructive trên workspace rộng.

Injection phải reproducible. Nếu scenario chỉ làm thủ công, runbook và observable assertions phải đủ để lặp lại.

## 8. Ma trận test bắt buộc

| Scenario | Injection point | Expected behavior |
|---|---|---|
| Kill worker khi Flow generating | Sau submit đã xác nhận | Lease hết, worker mới reconcile cùng job, không resubmit |
| Kill browser sau submit | Job active | Workflow pause/recover, reattach/inspect |
| Mất mạng | Navigation/poll/download | Bounded retry, state durable, không click submit lại |
| Session hết hạn | Trước hoặc sau submit | Human login required, safe resume |
| Selector thay đổi | Trước action quan trọng | Drift/error fail closed, không coordinate click |
| Download 0 byte | Candidate download | Reject/quarantine, retry download trong budget |
| Không có video stream | Technical review | Candidate reject, job không hoàn tất giả |
| Insufficient credits | Pre/after submit UI state | Circuit open, workflow pause, ledger reconcile |
| CAPTCHA | Bất kỳ browser step | Human CAPTCHA required, zero bypass |
| User cancel | Pending/active generation | Dừng schedule, reconcile external truth |
| Database restart | Transaction/outbox | Atomicity và replay idempotent |
| Duplicate event | Event ingestion | Một state transition/ledger effect |
| Lease expiry | Worker đang giữ step | Stale write bị reject |
| Stale worker write | Sau reassignment | Optimistic version/lease chặn |
| Flow project bị xóa | Navigation/recovery | Terminal/manual decision, không tự thay project |

## 9. Workstream

### 9.1 Recovery invariants

Mọi scenario kiểm tra:

- project/revision/workflow state vẫn truy được;
- không duplicate generation/TTS/cost debit do WindAgent;
- approval không tự sinh hoặc tái sử dụng sai revision;
- artifact `VALID/APPROVED` luôn tồn tại và hash đúng;
- outbox/event replay idempotent;
- stale worker không overwrite state;
- human-required/error state có lý do/evidence;
- retry không vượt retry/credit budget.

### 9.2 Reconciliation

Reconciler xử lý truth sources theo thứ tự:

```text
durable WindAgent intent/checkpoint
→ provider observable state
→ downloaded artifact/validation state
→ event/outbox state
→ cost ledger
→ workflow transition
```

Không suy `COMPLETED` chỉ vì file tồn tại hoặc UI từng hiện result.

### 9.3 Recovery objective

Trước test, mỗi scenario phải chốt:

- maximum time/attempt để phát hiện;
- trạng thái safe expected;
- tự recover hay human recover;
- dữ liệu/side effect được phép mất;
- cleanup requirement.

Không tự công bố một RTO chung nếu chưa đo. Kết quả PoC/chaos ghi observed detection/recovery time để làm baseline release.

### 9.4 Soak/repeat

- Chạy repeated mocked production workflows để tìm leak/flaky race.
- Theo dõi process/browser handle, temporary storage, lease, queue depth và duplicate event.
- Live Flow không dùng làm soak test thường xuyên.
- Failure không reproducible được phân loại flaky/observability gap, không đóng finding.

## 10. Deliverables

```text
docs/video_production/reliability/
├── recovery_invariants.md
├── failure_injection_runbook.md
├── reconciliation_policy.md
└── operational_recovery.md

artifacts/video_production/phase_25/
├── chaos_scenario_manifest.json
├── failure_injection_receipts/
├── duplicate_side_effect_audit.json
├── recovery_timing_report.json
├── soak_test_report.json
├── open_reliability_findings.json
└── phase_verdict.json
```

## 11. Acceptance gate

`VP25_RECOVERY_AND_CHAOS_VERIFIED` chỉ pass khi:

1. Tất cả scenario bắt buộc đã chạy ở mock/integration level.
2. Scenario browser/session trọng yếu có controlled environment receipt.
3. Không duplicate submit/debit/publish.
4. Không mất/corrupt durable state.
5. Retry/circuit/human state đúng policy.
6. Không còn reliability finding mức release-blocking.
7. Regression tests chạy trong CI phù hợp.

---

# Phase 26 — Security và privacy hardening

## 12. Mục tiêu

Chứng minh browser automation, asset ingestion, media processing, storage, API/UI và evidence không cho phép vượt trust boundary hoặc làm lộ/xử lý sai dữ liệu nhạy cảm.

## 13. Threat model

Assets:

- Flow account/session/profile/cookie;
- API/provider secrets;
- project screenplay/media chưa phát hành;
- real-person likeness/voice;
- cost/payment state;
- approvals/audit evidence;
- local filesystem/database.

Trust boundaries:

```text
internet assets → downloader quarantine
model output → structured validator
browser UI → Flow adapter/state machine
browser profile → worker/session store
media files → decoder/FFmpeg sandbox
API clients → authorization/domain commands
evidence/logs → redaction/access control
```

Threat model gắn finding ID, affected component, likelihood/impact, control, test và residual risk.

## 14. Workstream

### 14.1 Browser profile và secret

- Encryption at rest và key management dùng boundary canonical.
- Profile directory permission/ownership tối thiểu.
- Cookie/token/profile path không vào log, event, screenshot metadata hoặc support bundle.
- Secret redaction tests dùng canary values.
- Session deletion/rotation policy rõ ràng.

### 14.2 Network và upload allowlist

- Flow/domain allowlist, redirect revalidation.
- Downloader SSRF controls từ Phase 7.
- Upload chỉ từ approved artifact store và supported media type.
- Không cho arbitrary local path hoặc symlink escape.
- DNS/private address test.

### 14.3 File sandbox

- Canonicalize path trước authorization.
- Chặn `..`, absolute path ngoài root, alternate data stream nếu platform áp dụng và symlink/junction escape.
- Temporary/quarantine/output directories tách nhau.
- Filename từ web không điều khiển target path.
- Archive/SVG/executable policy fail closed.

### 14.4 Prompt/content injection

- Web/EXIF/metadata không được coi là instruction.
- Model output chỉ đi qua typed schema/allowlist.
- Browser action không nhận raw command từ prompt.
- Media metadata được strip/sanitize trước downstream model khi policy yêu cầu.
- Generated text không điều khiển FFmpeg filter/shell.

### 14.5 Browser action safety

Confirmation/human gate cho:

- terms acceptance;
- payment/credit purchase;
- project delete;
- external publish;
- account/security setting;
- destructive overwrite.

Automation không bypass CAPTCHA/fingerprint/rate/quota.

### 14.6 API và UI

- Authn/authz cho read, approve, cost, takeover, cancel, archive, delete, publish.
- Object-level authorization theo project.
- CSRF/CORS/session policy phù hợp deployment.
- Idempotency và optimistic concurrency cho command.
- Media URL/access token bounded và không lộ storage path.
- SSE/WebSocket không phát event project khác.

### 14.7 Audit và redaction

- Audit actor/action/target/revision/result.
- Không log raw secret/cookie/payment detail.
- Screenshot account/payment area được redact hoặc không lưu.
- Evidence manifest không chứa local absolute path khi portable.
- Audit tamper evidence theo mechanism hiện có.

### 14.8 Privacy lifecycle

Định nghĩa:

- purpose và data class;
- retention cho source assets, generated media, rejected candidates, screenshots, browser profile và logs;
- user-visible deletion;
- project archive vs delete;
- content-addressed shared object/reference-count handling;
- backup deletion limitations;
- legal hold nếu áp dụng.

Deletion:

1. authorization + confirmation;
2. mark/schedule;
3. remove project references;
4. delete unreferenced data theo retention;
5. clear session/profile nếu requested;
6. deletion receipt không chứa deleted content.

## 15. Security test matrix

- Secret canary qua logs/events/errors/screenshots.
- Profile encryption/unauthorized read.
- Domain/redirect/DNS allowlist.
- Path traversal, symlink/junction và malicious filename.
- SSRF/private IP.
- Wrong MIME/polyglot/decompression bomb/malicious metadata.
- Prompt injection từ asset metadata/model output.
- Arbitrary eval/shell/FFmpeg filter.
- Unapproved upload.
- Terms/payment/delete/publish confirmation.
- Cross-project API/media/event access.
- Stale approval/CSRF/idempotency.
- Data retention/project deletion.

Pen-test finding chưa sửa phải có severity và release decision; critical/high exploit khả thi trong scope chặn release.

## 16. Deliverables

```text
docs/video_production/security/
├── threat_model.md
├── browser_profile_and_secret_policy.md
├── network_file_prompt_boundaries.md
├── action_confirmation_policy.md
├── audit_and_redaction.md
└── privacy_retention_deletion.md

artifacts/video_production/phase_26/
├── threat_model_manifest.json
├── security_test_receipts/
├── secret_redaction_report.json
├── api_authorization_report.json
├── file_network_sandbox_report.json
├── privacy_deletion_receipt.json
├── open_security_findings.json
└── phase_verdict.json
```

## 17. Acceptance gate

`VP26_SECURITY_VERIFIED` chỉ pass khi:

1. Threat model bao phủ tất cả trust boundary.
2. Secret/profile/payment data không xuất hiện trong evidence/log tests.
3. SSRF/path traversal/prompt injection/unapproved upload bị chặn.
4. Destructive/payment/terms action luôn có human confirmation.
5. API/event/media object authorization pass.
6. Retention/deletion có implementation và receipt.
7. Không còn release-blocking security/privacy finding.

---

# Phase 27 — CI matrix và release certification

## 18. Mục tiêu

Chứng nhận đúng candidate SHA bằng CI nhiều tầng, controlled live test và evidence bundle cuối; phát hành có giới hạn đúng Release 0.1.

## 19. Candidate freeze

Trước certification:

- Chọn release branch/tag candidate.
- Ghi full candidate SHA và parent/baseline lineage.
- Worktree sạch.
- Version thống nhất giữa Python/web/desktop/release manifest.
- Lockfiles frozen.
- Migration set/checksum frozen.
- Third-party manifest/license/notice frozen.
- Known limitations và release scope frozen.

Mọi code/config/lockfile/migration thay đổi sau freeze tạo candidate SHA mới và rerun các lane bị ảnh hưởng; final verdict cũ bị vô hiệu.

## 20. CI lanes

### 20.1 PR CI

Không dùng authenticated live Flow:

```text
Python unit
Architecture imports
Canonical schema
Database migrations
SQLite
PostgreSQL
Worker recovery
Browser adapter mock
Browser contract/state-machine tests
Flow provider mock contract
Frontend unit
Frontend build
Desktop unit
Desktop build
FFmpeg verification fixtures
License/notice check
Third-party manifest check
Secret/security static checks
```

### 20.2 Nightly/manual

```text
authenticated Flow navigation smoke
session health and project open
selector drift detection
optional bounded image/video smoke with approval
longer recovery/soak matrix
cross-platform compatibility
```

Nightly live failure không tự động resubmit nhiều lần và phải tôn trọng credit cap.

### 20.3 Release candidate

```text
full clean CI on candidate SHA
database upgrade/rollback rehearsal
controlled real-credit E2E
browser recovery exercise
final media verification
security/privacy regression
evidence bundle validation
```

## 21. Platform/database matrix

Tối thiểu chứng nhận theo support policy đã công bố:

- Python versions trong `pyproject`;
- Windows cho desktop/browser flow mục tiêu;
- CI platform cho unit/build;
- SQLite và PostgreSQL;
- web/desktop supported Node/toolchain;
- FFmpeg version/profile;
- headed browser/runtime version.

Combination chưa test phải ghi limitation, không trình bày là supported.

## 22. Migration certification

- Upgrade từ release/baseline được support.
- Schema checksum/registry đúng.
- Backup trước migration.
- Rollback rehearsal hoặc forward-fix policy rõ.
- Existing non-video data không bị hỏng.
- Video workflow/artifact/job/ledger records bảo toàn.
- Re-run migration idempotent hoặc fail an toàn.

## 23. Release evidence bundle

```text
artifacts/video_production/final/
├── implementation_manifest.json
├── upstream_manifest.json
├── test_matrix.json
├── real_flow_e2e_receipt.json
├── cost_report.json
├── security_report.json
├── architecture_report.json
├── known_limitations.md
└── final_verdict.md
```

Nên bổ sung trong manifest hoặc receipt:

- baseline/candidate SHA;
- branch/tag/version;
- build artifact hashes;
- migration checksums;
- toolchain versions;
- individual CI run IDs/URLs nếu có;
- phase verdict hashes;
- Flow test project/job IDs đã sanitize;
- final MP4 hash;
- approvers và timestamps;
- open risk IDs.

`final_verdict.md` không tự nhận pass; nó tổng hợp machine-readable phase/CI receipts và ghi rõ điều kiện release.

## 24. Release blocker policy

Chặn release nếu có một trong các điều kiện:

- bất kỳ phase gate 0–27 chưa pass;
- required CI job fail/missing trên candidate SHA;
- duplicate submit/debit/publish chưa giải quyết;
- final E2E không truy vết hoặc vượt budget;
- critical/high security finding trong release scope;
- migration/rollback chưa chứng nhận;
- license/notice/third-party manifest sai;
- secret trong artifact/log;
- known limitation mâu thuẫn support claim;
- final evidence validation fail.

Flaky required test được coi là blocker cho đến khi phân loại và có quyết định rõ.

## 25. Controlled release

Release 0.1 chỉ tuyên bố:

- một Flow account/session/project;
- video 30–45 giây;
- tối đa hai character/bảy shot;
- concurrency 1;
- bounded approval/cost/retry;
- simple TTS/FFmpeg;
- basic resume/human takeover;
- mock CI + controlled live smoke/E2E.

Không tuyên bố hỗ trợ các mục hoãn trong roadmap.

## 26. Operational runbook

Trước phát hành:

- backup/migration plan;
- browser runtime/profile setup;
- Flow login/takeover procedure;
- credit/budget configuration;
- health checks;
- artifact storage/retention;
- known UI assumptions;
- incident and disable/circuit-breaker procedure.

Rollback/disable:

- có feature flag/composition option để ngừng Flow provider;
- không xóa project/artifact evidence khi disable;
- active run được pause/reconcile;
- API provider/future provider port vẫn tồn tại;
- release rollback không downgrade database nếu không an toàn.

## 27. Final certification

Trình tự:

```text
1. Verify clean candidate SHA
2. Run complete PR CI matrix
3. Run migration/rollback rehearsal
4. Run Phase 25 regression
5. Run Phase 26 regression
6. Approve real-credit maximum
7. Run controlled E2E + browser recovery
8. Verify final media/cost/traceability
9. Build and hash release artifacts
10. Validate evidence bundle
11. Review known limitations/open risks
12. Issue final verdict and controlled-release approval
```

Verdict cuối:

```text
VIDEO_PRODUCTION_PLATFORM_VERIFIED
READY_FOR_CONTROLLED_RELEASE
```

Hai dòng chỉ được ghi khi tất cả blocker policy đã thỏa.

## 28. Deliverables và gate Phase 27

Ngoài final bundle:

```text
docs/video_production/release/
├── support_matrix.md
├── release_runbook.md
├── migration_and_rollback.md
├── incident_response.md
└── release_0_1_notes.md

artifacts/video_production/phase_27/
├── candidate_attestation.json
├── ci_run_manifest.json
├── build_hash_manifest.json
├── migration_rehearsal_receipt.json
├── release_e2e_receipt.json
├── evidence_validation_receipt.json
└── phase_verdict.json
```

Phase 27 pass khi final verdict được derive trên đúng candidate SHA, bundle hợp lệ và release scope/limitation khớp thực tế.

## 29. Post-release observation

Controlled release cần theo dõi:

- browser/session health;
- selector drift;
- generation success/failure/retry;
- duplicate prevention;
- human-action frequency;
- cost estimate-vs-observed;
- candidate rejection reasons;
- recovery time;
- final media verification;
- storage growth/retention cleanup.

Incident có nguy cơ duplicate cost, account safety, secret leak hoặc corrupt artifact phải mở circuit/disable provider trước khi tiếp tục run mới.

## 30. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Chaos test gây hỏng dữ liệu thật | Scope theo test project/session, backup và cleanup verification |
| Recovery test chỉ kiểm tra process sống lại | Assert domain/job/artifact/cost invariants |
| Security scan bỏ sót runtime trust boundary | Threat model + dynamic negative tests |
| Evidence chứa secret/screenshot nhạy cảm | Canary redaction test + access/retention policy |
| CI xanh trên SHA khác | Candidate attestation và run-SHA validation |
| Live Flow chạy mọi PR gây tốn credit/flaky | Mock PR, nightly/manual và controlled RC |
| Sửa code sau certification | Invalidate verdict và rerun trên SHA mới |
| Support claim vượt test matrix | Explicit support matrix/known limitations |
| Flow UI đổi sau release | Drift detection, circuit breaker và provider disable path |

## 31. Checklist đóng toàn chương trình

- [ ] Phase 25 failure matrix không có duplicate/corrupt state.
- [ ] Phase 26 threat model và security/privacy tests pass.
- [ ] Required CI matrix green trên đúng candidate SHA.
- [ ] SQLite/PostgreSQL migration rehearsal pass.
- [ ] Web/Desktop/FFmpeg builds và verification pass.
- [ ] License/notice/upstream manifest pass.
- [ ] Controlled real-credit E2E và recovery pass.
- [ ] Cost ledger reconcile và final MP4 hash xác nhận.
- [ ] Final evidence bundle validate.
- [ ] Known limitations khớp Release 0.1.
- [ ] `VIDEO_PRODUCTION_PLATFORM_VERIFIED`.
- [ ] `READY_FOR_CONTROLLED_RELEASE`.
