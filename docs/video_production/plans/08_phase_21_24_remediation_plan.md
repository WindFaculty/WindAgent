# Kế hoạch 08 — Khắc phục và tái chứng nhận Phase 21–24

## 1. Quyết định và mục tiêu

Kế hoạch này thay thế mọi kết luận `PASSED` hiện có của Phase 21–24 bằng
trạng thái **chưa được chấp nhận** cho đến khi có evidence chạy thật. Đây là
kế hoạch khắc phục, không phải một thay đổi tiêu chí để hợp thức hóa fixture.

Mục tiêu là tạo lại một candidate có thể chứng minh được toàn bộ chuỗi:

```text
approved inputs + live Flow jobs + real audio assets
    → real FFmpeg render
    → verified 30–45s MP4
    → API/Web/Desktop supervision
    → traceable, budget-reconciled E2E evidence
```

Kết quả cuối cùng cần tái cấp bốn gate, theo đúng thứ tự:

```text
VP21_AUDIO_PIPELINE_VERIFIED
VP22_POST_PRODUCTION_VERIFIED
VP23_PRODUCTION_WORKSPACE_VERIFIED
VP24_E2E_POC_PASSED
```

Phase 25–27 vẫn bị chặn; không được bắt đầu release certification dựa trên
candidate hoặc verdict fixture hiện tại.

## 2. Finding đầu vào và non-negotiable rules

Các finding phải được đóng bằng evidence, không chỉ bằng test mới:

| ID | Finding | Hệ quả bắt buộc |
|---|---|---|
| R21-01 | Verifier audio dùng fake TTS/fixture. | Tách test contract khỏi receipt production; receipt production phải trỏ tới audio asset và provider request thật đã redaction. |
| R22-01 | File `.mp4`/`.wav` fixture là mock payload; không có `ffprobe` thật. | Render phải dùng FFmpeg thật; ffprobe phải parse file thật và decode sample frame. |
| R22-02 | `--no-write` không hoạt động nhất quán. | Mọi verifier phải mặc định read-only hoặc yêu cầu `--write`; dry-run không được tạo/sửa artefact. |
| R23-01 | Build/test Web/Desktop được tự khai báo. | Receipt phải derive từ command thật, exit code, log hash, build hash và candidate SHA. |
| R24-01 | Run manifest, hash, Flow receipt và timing dùng placeholder. | Tất cả ID/hash phải có format/lineage thực; placeholder bị fail-closed. |
| R24-02 | Không có final MP4 30–45 giây hoặc evidence Flow live. | Chạy controlled real-credit E2E có phê duyệt; lưu final artifact, locator, SHA-256, ffprobe receipt và recovery evidence. |

Quy tắc chung:

- Không sửa trực tiếp `phase_verdict.json` để đổi trạng thái.
- Không dùng verifier vừa tạo evidence vừa tự kết luận evidence đó là đúng trong cùng lần chạy.
- Một receipt chỉ hợp lệ khi liên kết đến candidate SHA 40/64-hex, input/output SHA-256 64-hex, command/run ID, thời gian và locator đã redaction.
- File media phải được xác thực bằng bytes và tool thật; extension, duration khai báo hoặc hash placeholder không đủ.
- Test mock/fixture vẫn được giữ trong PR CI, nhưng tên gate phải là `CONTRACT_TESTED`, không phải production `PASSED`.
- Chỉ thực hiện Flow live sau khi người dùng phê duyệt creative brief, ngân sách tối đa và thời điểm chạy. Không tự mua credit, chấp nhận điều khoản, hoặc vượt quota.

## 3. Trạng thái đích và evidence taxonomy

Tách rõ ba tầng chứng minh để tránh false PASS:

| Tầng | Mục đích | Được phép dùng fixture? | Điều kiện verdict |
|---|---|---:|---|
| Unit/contract | Logic domain, input xấu, fail-closed. | Có | `CONTRACT_TESTED` |
| Integration | Adapter, filesystem sandbox, FFmpeg/API/client local. | Có, nhưng subprocess/build thật | `INTEGRATION_VERIFIED` |
| Production PoC | Flow account/session, asset/audio/video và cost thật trong scope. | Không | `VPxx_*_VERIFIED` / `VP24_E2E_POC_PASSED` |

Mọi production receipt có tối thiểu schema sau:

```json
{
  "schema_version": "1.0.0",
  "candidate_sha": "<40-or-64-hex>",
  "run_id": "<stable-id>",
  "started_at": "<RFC3339>",
  "completed_at": "<RFC3339>",
  "command_or_provider": "<redacted identity>",
  "input_hashes": ["<sha256>"],
  "output_hashes": ["<sha256>"],
  "evidence_locator": "<authorized/redacted locator>",
  "status": "PASSED | FAILED | BLOCKED"
}
```

Validator phải từ chối receipt thiếu field, hash không đúng định dạng, timestamp
nghịch lý, locator không được phép, hoặc candidate SHA khác manifest gốc.

## 4. Trình tự thực hiện

```text
R0 Freeze findings + repair verification boundary
 ↓
R1 Toolchain and real-media integration
 ↓
R2 Production audio evidence
 ↓
R3 Workspace build and interaction evidence
 ↓
R4 Controlled real Flow E2E
 ↓
R5 Independent evidence validation and re-certification
```

Mỗi bước tạo candidate SHA mới nếu có thay đổi code/config/lockfile. Verdict của
candidate cũ tự hết hiệu lực; không ghép receipt từ các SHA khác nhau.

---

# R0 — Đóng false-PASS path và sửa verifier

## 5. Mục tiêu

Biến verification thành công cụ kiểm tra evidence đã tồn tại, không phải factory
đẻ fixture rồi đánh dấu pass.

## 6. Công việc

1. Đổi CLI của các verifier Phase 21–24:

   ```text
   verifier --evidence-dir <dir> --candidate-sha <sha>    # mặc định: read-only
   verifier --write-fixture <dir>                         # chỉ phục vụ test fixture
   ```

   `--no-write` có test bảo vệ: snapshot hash/mtime của toàn bộ evidence trước và
   sau chạy phải giống nhau. Không nhận flag không dùng.

2. Tách `scripts/verification/fixture_*` khỏi `scripts/verification/verify_*`.
   Fixture writer chỉ được tạo dữ liệu dưới temporary test directory, không được
   ghi `artifacts/video_production/phase_*`.

3. Thêm schema JSON cho từng receipt và một `evidence_manifest.json` content-
   addressed. Manifest ghi schema hash, candidate SHA, file hash, size, media
   MIME/container thực, retention và locator.

4. Thêm các negative regression test: mock payload đổi đuôi `.mp4`, hash
   `sha256_*`, build receipt không có log, Flow receipt không có external ID,
   duration lệch scope, và missing final MP4 đều phải trả `FAILED`/`BLOCKED`.

## 7. Gate R0

R0 hoàn tất khi:

- verifier read-only không làm thay đổi evidence;
- fixture writer không thể ghi vào artifact production;
- placeholder/invalid media bị fail-closed;
- verdict được derive từ manifest đã validate, không từ boolean hard-code.

Artefact:

```text
artifacts/video_production/remediation/r0/
├── verifier_mode_test_receipt.json
├── negative_evidence_matrix.json
├── receipt_schema_validation.json
└── phase_verdict.json
```

---

# R1 — Khôi phục toolchain và post-production thật

## 8. Mục tiêu

Tái cấp `VP22_POST_PRODUCTION_VERIFIED` bằng một MP4 thật, render tái lập được và
được kiểm tra bằng FFmpeg/ffprobe thật.

## 9. Công việc

1. Cài đặt hoặc cung cấp FFmpeg/ffprobe trong controlled toolchain; ghi đường dẫn
   executable, version, build configuration, SHA-256 binary (nếu policy cho phép)
   vào toolchain manifest. CI phải fail nếu không tìm thấy cả hai executable.
2. Dùng `subprocess` argv không shell interpolation; log command đã redact, exit
   code, elapsed time, input/output bytes, input/output SHA-256.
3. Render từ clip/audio thật dưới controlled workspace. Không chấp nhận byte string
   mock, filename giả hay media extension không tương ứng container magic.
4. `ffprobe` phải xuất structured JSON từ file final; decode frame đầu/giữa/cuối,
   xác minh duration, codec, stream audio/video, resolution, fps, loudness/peak,
   subtitle bounds và black/truncated ending.
5. Render lặp lại theo encoding profile đã pin. Nếu byte-identical không được bảo
   đảm, ghi rõ semantic reproducibility và những field được phép khác; không tự
   tuyên bố byte-identical.

## 10. Artefact và gate VP22

```text
artifacts/video_production/phase_22/<candidate_sha>/
├── toolchain_receipt.json
├── render_manifest.json
├── ffmpeg_command_receipts/
├── ffprobe_raw.json
├── media_decode_receipt.json
├── reproducibility_report.json
├── final_media_manifest.json
└── phase_verdict.json
```

`VP22_POST_PRODUCTION_VERIFIED` chỉ pass khi final media manifest trỏ tới MP4
container thực có hash 64-hex, tất cả checks kỹ thuật pass, và output chỉ được
publish sau verification. Không có FFmpeg/ffprobe, media không đọc được hoặc
duration ngoài policy đều là `BLOCKED`/`FAILED`.

---

# R2 — Production audio evidence

## 11. Mục tiêu

Tái cấp VP21 bằng audio asset thật và provenance hoàn chỉnh; fake TTS vẫn giữ làm
unit test, không được làm production receipt.

## 12. Công việc

1. Chọn provider/voice được phê duyệt; lưu provider/model/voice/version, rights
   state, consent/license reference đã redaction và request id/hash.
2. Thực hiện TTS cho dialogue locked. Lưu audio asset thật, sample rate, channel
   layout, duration, SHA-256 và word timestamps/alignment output.
3. Áp dụng policy low-confidence, overlong dialogue, SFX/BGM rights và mix policy.
   Mọi human override phải có actor, reason, target revision/hash.
4. Đo loudness/peak bằng tool thật; command và raw measurement là evidence.
5. Chứng minh invalidation: thay đổi dialogue/BGM tạo revision mới và chỉ invalidates
   scope đúng, không reuse output stale.

## 13. Gate VP21

`VP21_AUDIO_PIPELINE_VERIFIED` pass khi từng audio asset trong final mix có
provenance/rights hợp lệ, alignment finding không bị che, technical measurement
pass và input/output thực đều có hash. Thiếu consent/license, asset file, timestamp
hoặc provider request thì `BLOCKED`, không substitute bằng fixture.

---

# R3 — Workspace Web/Desktop có bằng chứng chạy thật

## 14. Mục tiêu

Tái cấp VP23 bằng API, frontend và desktop build/test thực trên đúng candidate.

## 15. Công việc

1. Thay self-reported build/test counter bằng executor tạo receipt từ command thật:
   argv, working directory, lockfile hash, exit code, stdout/stderr hash, duration,
   source candidate SHA và output bundle hash.
2. Chạy Web unit/build và browser E2E against API V2 test deployment. E2E phải thực
   hiện: xem candidate, approve/reject/override có reason, cost block, stale revision,
   cancel/publish confirmation và state recovery snapshot + replay.
3. Chạy Desktop unit/build/smoke với Web client contracts. Xác minh restart không
   tạo backend authority mới và takeover không làm lộ profile path/token.
4. Kiểm tra authorization thật cho approve, cost approval, human resolution, cancel
   và publish. Các response/event phải bảo toàn revision, idempotency key và cursor.
5. Screenshot/video evidence chỉ lưu ở authorized/redacted store; không lưu secret
   hay absolute profile path.

## 16. Gate VP23

```text
artifacts/video_production/phase_23/<candidate_sha>/
├── api_integration_receipt.json
├── realtime_e2e_receipt.json
├── web_command_receipt.json
├── web_build_manifest.json
├── desktop_command_receipt.json
├── desktop_build_manifest.json
├── accessibility_core_flow_receipt.json
└── phase_verdict.json
```

`VP23_PRODUCTION_WORKSPACE_VERIFIED` pass khi command log và output build thật hợp
lệ, core human-control flow chạy được trên API V2, reconnect không duplicate action,
và desktop không có state authority riêng. Bất kỳ receipt hard-code hoặc command
không chạy đều là `FAILED`.

---

# R4 — Controlled real Flow E2E

## 17. Điều kiện yêu cầu phê duyệt

Trước khi thực hiện bước này, cần có xác nhận rõ ràng của người có thẩm quyền về:

- creative brief/revision đã lock;
- maximum credits, retry reserve và thời điểm live run;
- Flow account/session/project test đã được phép dùng;
- human operator trực takeover và phương án dừng;
- artifact storage, retention và redaction policy.

Không có xác nhận này thì R4 giữ `BLOCKED`; các bước R0–R3 vẫn có thể hoàn thành.

## 18. Freeze manifest

Manifest phải chứa candidate SHA thực, 2 scenes, 5–7 shots, 1–2 characters,
1–2 locations, 16:9, 30–45 seconds, tối đa 2 candidates/shot, concurrency 1 và
budget. Mọi hash đầu vào là SHA-256 thực; thay đổi sau freeze tạo run mới.

## 19. Runbook và recovery

Chạy lần lượt 14 bước trong Kế hoạch 06. Sau một generation đã submit nhưng trước
download, thực hiện controlled browser-close/re-attach:

```text
submit confirmed
→ close/lose browser
→ workflow pauses or enters recovery state
→ reattach authorized session
→ reconcile same external job ID
→ download/review existing result
→ assert duplicate_submits = 0 and duplicate_debits = 0
```

Flow receipt tối thiểu cần external job ID đã sanitize, provider-visible timestamps,
request/candidate hashes, approved candidate ID, cost observation và evidence locator.
Không lưu cookie, token, profile path hoặc payment detail.

## 20. Final assembly and acceptance

Final output phải là MP4 thật có duration 30–45s và được assemble từ approved
shot/audio hashes của chính run đó. Traceability DAG phải nối:

```text
final MP4 hash
→ EDL hash
→ approved shot/audio hashes
→ Flow/TTS request hashes
→ compiled prompts/references
→ cinematic plan
→ locked screenplay/package revision
```

Automation rate dùng dữ liệu event/action thực; approval, login, takeover và browser
recovery không tính manual media editing. Candidate review phải cho thấy identity
defect, score, blocking defect, confidence và mọi human override.

## 21. Gate VP24

`VP24_E2E_POC_PASSED` chỉ pass khi đồng thời thỏa:

1. VP21–VP23 trên cùng candidate lineage đã pass.
2. Tất cả 5–7 shot có evidence job/candidate thật, không duplicate submit/debit.
3. Browser recovery/reconciliation có receipt thật.
4. Final MP4 30–45s pass full FFprobe/decode/loudness verification.
5. Traceability graph có hash thực và đầy đủ lineage.
6. Automation rate >= 80%, character consistency không có blocking defect ẩn.
7. Ledger observed/adjusted <= approved maximum và reconciled.
8. Final-cut approval tham chiếu đúng final artifact hash.

Một điều kiện không đạt tạo `BLOCKED` hoặc `FAILED`; tuyệt đối không có “partial
success” hoặc pass do receipt fixture.

---

# R5 — Independent validation, handoff và kiểm soát thay đổi

## 22. Independent validation

Một validator độc lập với generator thực hiện theo thứ tự:

1. xác minh worktree/candidate SHA và lockfile/toolchain;
2. xác minh manifest + toàn bộ file hash/size/MIME;
3. chạy lại ffprobe/decode trên final media;
4. kiểm tra receipt lineage, revision, event sequence và duplicate invariant;
5. kiểm tra cost ledger, final approval và redaction;
6. đối chiếu acceptance matrix Kế hoạch 06;
7. xuất `PASSED`, `FAILED` hoặc `BLOCKED` kèm blocking reasons cụ thể.

Validator không được viết artefact nguồn. Báo cáo kết quả có checksum của input
manifest, validator version và command receipt riêng.

## 23. Deliverable cuối

```text
artifacts/video_production/phase_24/<candidate_sha>/
├── poc_run_manifest.json
├── input_revision_manifest.json
├── workflow_event_receipt.json
├── flow_job_receipts/
├── browser_recovery_receipt.json
├── candidate_review_report.json
├── audio_production_receipt.json
├── postproduction_receipt.json
├── final_media_manifest.json
├── final_media_verification.json
├── cost_report.json
├── traceability_graph.json
├── automation_rate.json
├── final_cut_approval.json
├── evidence_manifest.json
├── independent_validation_receipt.json
└── phase_verdict.json
```

Media lớn có thể ở authorized artifact store, nhưng manifest phải có SHA-256,
content type, byte size, retention và locator có thể truy cập bởi reviewer được
ủy quyền. Không commit asset nhạy cảm chỉ để làm bằng chứng.

## 24. Definition of done

- [ ] R0 loại bỏ false-PASS và enforce read-only verification.
- [ ] FFmpeg/ffprobe có trong toolchain và render/verify MP4 thật.
- [ ] VP21 có audio/provider/provenance production evidence.
- [ ] VP22 có render, media và reproducibility evidence thật.
- [ ] VP23 có build/test/API/UI evidence thật trên candidate SHA.
- [ ] User đã phê duyệt live Flow scope và real-credit cap trước R4.
- [ ] VP24 có final MP4 30–45s, recovery, traceability, automation và ledger thật.
- [ ] Independent validator pass trên manifest bất biến.
- [ ] Không còn placeholder, mock payload hoặc self-attested receipt trong production evidence.

Chỉ sau checklist này mới được cập nhật verdict của Phase 21–24 và mở lại
Phase 25–27.
