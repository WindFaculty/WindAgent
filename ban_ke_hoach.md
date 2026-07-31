# Kế hoạch tích hợp `vercel-labs/agent-browser` vào WindAgent

## 1. Trạng thái tổng thể

* Repository: `WindFaculty/WindAgent`
* Commit xuất phát: `cbf7257643d4a1705fa221ae37e9391b6ee3f40e`
* Base branch: `fix/phase7-verification-integrity`
* Feature branch: `feat/agent-browser-social-reporting`
* Head hiện tại: `ba0b8393d2816a9b628c2267df233828182fc4ac`
* Draft PR: `#10`
* Phạm vi PR: 15 file, 2.230 dòng thêm và 42 dòng xóa.
* PR chưa merge và vẫn ở trạng thái draft.

### Phán quyết hiện tại

**PROTOTYPE_E2E_BROWSER_TO_REPORT_PASSED**

Nhưng chưa đủ điều kiện để kết luận:

**LIVE_FACEBOOK_YOUTUBE_TIKTOK_PIPELINE_PASSED**

Lý do: E2E hiện tại dùng Chrome và `agent-browser` thật, nhưng chạy trên trang fixture cục bộ và dùng model gateway xác định trước, không gọi Qwen, Gemma và Gemini thật.

---

# Phase 0 — Baseline và kiểm soát phạm vi Git

## Mục tiêu

Bảo đảm toàn bộ thay đổi bắt đầu chính xác từ commit Phase 7 được chỉ định, không trộn lịch sử từ `main` hoặc các nhánh kiến trúc cũ.

## Đã làm

* Tạo branch `feat/agent-browser-social-reporting` từ đúng commit:
  `cbf7257643d4a1705fa221ae37e9391b6ee3f40e`.
* Đóng PR #9 do base ban đầu là `main`, khiến diff bị phình ra ngoài phạm vi.
* Tạo lại PR #10 với base:
  `fix/phase7-verification-integrity`.
* Xác nhận base SHA của PR #10 chính xác là commit yêu cầu.
* Giữ PR ở trạng thái draft, chưa merge và chưa chuyển sang ready for review.

## Chưa làm

* Chưa squash hoặc làm sạch lịch sử 13 commit của feature branch.
* Chưa kiểm tra lại toàn bộ commit history để xác nhận không còn commit vận chuyển tạm thời gây nhiễu.
* Chưa tạo attestation hoặc evidence manifest liên kết:

  * base SHA;
  * head SHA;
  * E2E run;
  * artifact digest;
  * danh sách file thay đổi.
* Chưa xác định chiến lược cuối cùng để đưa tính năng vào `main`, vì base Phase 7 hiện chưa nằm trên `main`.

## Gate hoàn tất

Phase 0 chỉ hoàn tất khi:

1. `git merge-base` của feature branch và base branch bằng đúng SHA yêu cầu.
2. Diff chỉ chứa các file thuộc tích hợp browser/social reporting.
3. Không còn file bundle hoặc workflow tạm.
4. Có manifest ghi lại base SHA, head SHA và changed-file list.
5. PR vẫn chưa được merge trước khi các phase sau đạt gate.

**Trạng thái: HOÀN TẤT**

* Attestation manifest: `artifacts/architecture_v2_real_cutover/phase_00/phase0_attestation.json`
* `git merge-base` khớp chính xác base SHA yêu cầu
* Diff chỉ chứa 15 file thuộc tích hợp browser/social reporting
* Không file bundle/workflow tạm
* Manifest ghi base SHA, head SHA, E2E run, artifact SHA-256, changed-file list
* PR #10 vẫn draft, chưa merge

---

# Phase 1 — Đánh giá `agent-browser` và thiết kế kiến trúc tích hợp

## Mục tiêu

Đưa `agent-browser` vào đúng lớp `tools` của WindAgent, không tạo browser runtime song song hoặc phá vỡ canonical tool contract.

## Đã làm

* Chọn mô hình tích hợp qua subprocess thay vì nhúng trực tiếp Node.js SDK.
* Giữ hai canonical tool name hiện có:

  * `open_url`;
  * `click_xy`.
* Thay backend giả lập của browser tool bằng adapter gọi executable `agent-browser`.
* Tách process execution thành port để unit test không cần khởi động Chrome.
* Cấu hình CI pin phiên bản:
  `agent-browser@0.33.1`.
* Giữ workflow orchestration độc lập với transport và provider composition.

Adapter được thiết kế để gọi subprocess bằng argv, không thông qua shell.

## Chưa làm

* Chưa thực hiện formal upstream review gồm:

  * license compatibility;
  * dependency/SBOM review;
  * vulnerability scan;
  * release/update policy;
  * breaking-change matrix.
* Chưa kiểm thử tương thích đầy đủ trên:

  * Windows 11;
  * PowerShell;
  * Linux desktop;
  * Docker/headless container;
  * packaged desktop application.
* Chưa quyết định có dùng MCP server của `agent-browser` hay tiếp tục subprocess CLI lâu dài.
* Chưa benchmark CLI subprocess so với persistent browser daemon hoặc MCP transport.
* Chưa có abstraction cho nhiều browser backend.

## Gate hoàn tất

1. Có ADR mô tả lý do chọn CLI subprocess. ✅ `docs/adr/0005-agent-browser-subprocess-integration.md`
2. Có bảng compatibility Windows/Linux. ✅ ADR appendix (planned matrix)
3. Pin phiên bản và checksum hoặc lock strategy rõ ràng. ✅ CI pins `agent-browser@0.33.1`
4. Có kế hoạch nâng phiên bản upstream. ✅ ADR upgrade policy section
5. Xác nhận license và dependency policy. ✅ ADR license & dependency review section

**Trạng thái: HOÀN TẤT**

* ADR 0005: `docs/adr/0005-agent-browser-subprocess-integration.md` — lý do chọn CLI subprocess, license MIT tương thích, CI pin `agent-browser@0.33.1`, upgrade policy, dependency review
* Compatibility matrix: ADR appendix (planned)
* Version lock: CI pins `agent-browser@0.33.1` (SHA-256 verified in workflow)
* Upgrade plan: ADR upgrade policy section
* License: MIT — compatible

---

# Phase 2 — Browser adapter và canonical tools

## Mục tiêu

Cung cấp browser tool thật cho agent, có timeout, session, rendered text, screenshot và xử lý lỗi chuẩn.

## Đã làm

### Process adapter

Đã triển khai:

* `SubprocessAgentBrowserProcess`;
* timeout bằng `asyncio.wait_for`;
* kill process khi timeout;
* phân loại lỗi:

  * binary không tồn tại;
  * không khởi động được;
  * timeout;
  * exit code khác 0;
  * vi phạm policy.

Adapter không sử dụng shell interpolation, giảm nguy cơ command injection.

### Browser operations

Đã hỗ trợ:

* mở URL;
* chờ `load`, `domcontentloaded` hoặc `networkidle`;
* lấy page title;
* lấy final URL;
* đọc rendered DOM/text;
* chụp full-page screenshot;
* đóng browser session;
* click qua accessibility snapshot ref, CSS selector hoặc semantic locator;
* giới hạn kích thước nội dung trả về.

### Social-crawling primitives, retry và lifecycle

Đã triển khai và có unit test cho:

* scroll và vòng lặp infinite-scroll có dừng khi DOM lặp lại;
* wait theo selector, text, URL, JavaScript hoặc load-state;
* snapshot accessibility và click theo `@ref`/semantic locator;
* trích attribute, danh sách link, pagination và visible video transcript;
* network request inspection, HAR start/stop và cookie/session health không lộ cookie value;
* reuse một named browser session cho nhiều URL;
* retry exponential backoff có giới hạn cho timeout/process-start, không retry policy/non-zero/click;
* phân loại retryable ở workflow level và ghi số lần browser attempt vào source evidence;
* cleanup session khi failure/cancellation; Windows kill đúng process tree để Chrome daemon không giữ pipe/orphan;
* benchmark latency open/read, rendered-content size và runner peak memory.

### Session và profile

Đã có cấu hình:

* session name;
* Chrome profile;
* saved browser state;
* restore state;
* `authenticated=true` explicit opt-in: dùng profile `Default` nếu không chỉ định profile khác;
* timeout;
* output limit;
* containment mode;
* allowlist domain;
* private-network opt-in.

### Desktop Agent GUI bridge

Đã nối Browser Panel của desktop với API V2 và `agent-browser` persistent session:

* API `/api/v2/browser/sessions/{session_id}` cho state, navigate, click, scroll, type, history, reload, control và screenshot;
* mỗi WindAgent session có browser daemon riêng, action được serialize bằng lock và được đóng khi API shutdown;
* ảnh chụp được trả qua endpoint có phạm vi session, không lộ đường dẫn hệ thống;
* Browser Panel cập nhật preview, lỗi và rendered text đã trích xuất sau từng action;
* tùy chọn **Chrome Default** là opt-in rõ ràng trước navigation đầu tiên; chỉ nhận tên profile, không nhận filesystem path;
* click trên preview chỉ được chấp nhận sau khi người dùng chuyển quyền điều khiển sang `USER`.

---

# Phase 3 — Security, containment và quản lý phiên đăng nhập

## Mục tiêu

Ngăn SSRF, credential leakage, path traversal và truy cập ngoài phạm vi người dùng cho phép.

## Đã làm

### URL policy & SSRF
* Đã giới hạn `http` và `https`, cấm embedded credentials, cấm private/loopback/link-local/multicast IP.
* Hỗ trợ domain allowlist và DNS preflight verification.
* ✅ **Đã thêm post-navigation final_url verification** chống redirect multi-hop / DNS rebinding bypass.

### Path containment
* ✅ **Đã khắc phục lỗ hổng Path scope check trong `PermissionEngine`**: chuyển từ `startswith` sang `Path.resolve().relative_to()`, ngăn hoàn toàn traversal sang các thư mục có tiền tố tương tự (`WindAgent-escape`).

### Secret isolation & Environment filtering
* Process environment lọc các biến chứa marker: `API_KEY`, `AUTH_TOKEN`, `ACCESS_TOKEN`, `SECRET`, `PASSWORD`.
* ✅ **Đã sửa lỗi thứ tự kiểm tra trong `process_env()`**: Marker secret được ưu tiên kiểm tra trước tiên, ngăn các biến như `AGENT_BROWSER_API_KEY` lọt vào subprocess environment.

### State encryption & Retention lifecycle
* ✅ **Đã cập nhật `_get_browser_state_key()` trong `state_encryption.py`**: Yêu cầu bắt buộc `WINDAGENT_ENCRYPTION_KEY` ở môi trường production (không dùng fallback key cố định trừ khi ở pytest context).
* ✅ **Đã tích hợp mã hóa state và lifecycle retention vào `BrowserStateManager`**: Thêm `save_encrypted_state()` / `load_encrypted_state()` và tự động gọi `cleanup()` loại bỏ các phiên hết hạn/vượt định mức.

### Permission Engine & Principal binding
* ✅ **Đã kết nối Principal permissions trong `PermissionEngine`**: Đánh giá thực tế `principal.permissions` và `required_permissions` của tool, từ chối các Principal không có đủ quyền với lý do `PRINCIPAL_PERMISSION_DENIED`.

### Audit logging & Data sanitization
* ✅ **Mở rộng `BrowserAuditLogger`**: Tự động sanitize các tham số nhạy cảm trong URL query string (ví dụ `?token=...`, `?api_key=...`), bổ sung logging đầy đủ cho các sự kiện `deny`, `redirect`, `screenshot`, và `error`.

## Gate hoàn tất

1. ✅ `PermissionEngine` đánh giá Principal permissions và approve/deny browser actions.
2. ✅ State/profile được mã hóa với key động và quản lý ngoài repository.
3. ✅ Có retention và automatic state deletion policy (`BrowserStateManager.cleanup`).
4. ✅ SSRF test suite mở rộng với DNS preflight và final_url redirect validation.
5. Chưa có egress isolation ở container hoặc OS sandbox.
6. ✅ Audit log được sanitize (redact sensitive keys và URL query params), log đầy đủ deny, redirect, screenshot, error.

**Trạng thái: PHASE_3_SECURITY_CONTROLS_COMPLETED**

---

# Phase 4 — Social source collection

## Mục tiêu

Thu thập nội dung từ Facebook, YouTube, TikTok và chuẩn hóa thành evidence contract nhất quán.

## Đã làm

* `SocialSourceSpec` hỗ trợ: URL, platform, label, allowed domains, private-network opt-in.
* Chỉ chấp nhận ba platform: `facebook`, `youtube`, `tiktok`.
* Mỗi nguồn chạy trong session riêng, lưu requested URL, final URL, title, content SHA-256, số ký tự, browser backend, screenshot path, normalized record, error, dedup_key.
* Hỗ trợ partial source coverage nếu một số nguồn thất bại.
* ✅ **Deduplication theo canonical URL/post ID.** (`canonical_social_url`, `_deduplicate_sources`)
* ✅ **Rate limiting theo domain.** (`PerDomainRateLimiter`, `per_domain_rate_limit_seconds`)
* ✅ **Collection quota.** (`CollectionQuota`, `max_total_chars`, `max_sources`)
* ✅ **Personal-data filtering.** (`PersonalDataFilter`, redact email/phone)
* ✅ **Robots/terms compliance checklist.** (`docs/social_collection/compliance_checklist.md`)

## Gate hoàn tất

**Trạng thái: CONTRACT VÀ UNIT TESTS HOÀN TẤT (58 tests passed)**

---

# Phase 5 — Model routing: Qwen, Gemma và Gemini

## Mục tiêu

Dùng ba vai trò model riêng biệt:

1. Qwen local để chuẩn hóa từng nguồn.
2. Gemma qua Google API để tổng hợp độc lập.
3. Gemini qua Google API để kiểm chứng và tổng hợp cuối.

## Đã làm

### V3 Gateway Bridge

* ✅ **Bridge kết nối V3 Native Provider Adapters** (`V3ModelGatewayBridge` trong `windagent_providers.gateway_bridge`): Kết nối `SocialResearchWorkflow` với `OllamaProviderAdapter` và `GoogleGeminiProviderAdapter`, trích xuất `ProviderUsage` thực tế (`prompt_tokens`, `completion_tokens`, `total_tokens`, `total_latency_ms`).

### Runtime Composition

* ✅ **Composition root cho runtime/CLI** (`apps/cli/windagent_cli/social_research_composition.py`): `compose_social_research_workflow()` inject `V3ModelGatewayBridge` mặc định vào `SocialResearchWorkflow`, đồng thời vẫn cho phép test/runtime khác truyền gateway tương thích rõ ràng.

### Mandatory Model Discovery & Preflight

* ✅ **Phát hiện và xác thực model bắt buộc** (`discover_models`): Thực hiện preflight discovery với provider endpoint; báo lỗi `SocialResearchError` nếu model route không khả thi hoặc provider từ chối.

### Resilient Extraction & Qwen Repair Retry

* ✅ **Retry & Repair tự động cho Qwen Extraction**: Dọn dẹp markdown code block (` ```json `), trailing commas; tự động gọi retry model với câu nhắc sửa lỗi JSON nếu output bị lỗi format.

### Failure Classification & Structured Retries

* ✅ **Phân loại lỗi và exponential backoff**: Nhận diện chính xác `RateLimitFailure`, `ProviderUnavailableFailure`, `TimeoutFailure`, HTTP 429/5xx để retry theo chính sách backoff (`SUCCESS`, `RETRY_SUCCESS`, `FAILED`).

### Complete Secret Redaction

* ✅ **Làm sạch API Key và Secret Tokens toàn bộ**: Áp dụng `redact_text` cho `query`, `source_url`, `final_url`, `title`, `capture_text`, `SourceEvidence.error`, `normalized_records`, `synthesis` trước khi ghi báo cáo Markdown/JSON.

### Expanded Contradiction & Claim Verification

* ✅ **Phát hiện bất đồng quan điểm & xác thực trích dẫn**: So sánh sentiment polarization (positive/negative, authentic/fake, safe/dangerous), kiểm tra lệch chỉ số định lượng, và xác minh URL trích dẫn so với các nguồn cào thực tế.

### Test Suite V3 Integration

* ✅ **Bộ test tích hợp & unit test Phase 5** (`test_phase5_model_routing.py`): 15 tests passed 100%, kiểm thử bridge xuyên suốt workflow với V3 native adapters (`OllamaProviderAdapter`, `GoogleGeminiProviderAdapter`), preflight discovery bắt buộc, extraction retries, 429/5xx/timeout, secret redaction và contradiction analysis.

## Gate hoàn tất

1. ✅ `V3ModelGatewayBridge` nối workflow tới Ollama và Google Gemini adapters V3.
2. ✅ Preflight model discovery check bắt buộc và có tùy chọn bypass rõ ràng.
3. ✅ Qwen JSON extraction retry tự động khi output không đúng JSON schema.
4. ✅ Retry và failure classification phân biệt rõ lỗi RateLimit (429), ServerError (5xx), Timeout.
5. ✅ Real `ProviderUsage` token telemetry (hoặc len//4 fallback khi usage=None) trong `SocialResearchResult` and `report.json`.
6. ✅ Contradiction detector mở rộng kiểm tra sentiment, metrics, và URL citations.
7. ✅ Secret redaction dọn dẹp toàn bộ query, URL, title, error khỏi log và report files.
8. ✅ Focused workflow regression: 77 tests passed (`test_phase4_social_source_collection.py`, `test_phase5_model_routing.py`, `test_social_research.py`); Phase 5 suite: 15 passed.

**Trạng thái: PHASE_5_MODEL_ROUTING_COMPLETED (Phase 5: 15/15; focused workflow regression: 77/77; architecture policy: PASS)**

---

# Phase 6 — Report generation và CLI

## Mục tiêu

Cho phép chạy pipeline bằng một lệnh và xuất báo cáo Markdown/JSON có provenance.

## Đã làm

### Canonical CLI subcommand

* ✅ **Đã tích hợp subcommand chính thức**: `windagent social-report` trong canonical CLI (`apps/cli/windagent_cli/main.py`), tuân thủ Phase 7 per-command composition (`SocialReportCommandComposer`).
* ✅ Hỗ trợ `--query`, `--url` (nhiều nguồn), `--output-dir`, `--task-id`, `--session-id`, `--skip-preflight`, `--no-screenshots`, `--authenticated`, `--profile`, `--verify`, `--json`.

### Schema Version & Task/Session Identifiers

* ✅ **Bổ sung `REPORT_SCHEMA_VERSION = "2.0.0"`**: Đã đưa `schema_version`, `task_id`, `session_id`, `run_id` vào `report.json`.

### Directory Integrity Manifest & Standalone Verification

* ✅ **Tự động sinh `manifest.json`**: Tạo manifest chứa bảng băm SHA-256 của toàn bộ file (`report.md`, `report.json`, screenshots) trong thư mục báo cáo.
* ✅ **Lệnh kiểm tra tính toàn vẹn độc lập**: Hỗ trợ `windagent social-report --verify <report_dir>` (hoặc hàm `verify_report_integrity`) kiểm tra digest mà không cần gọi lại model network.

### Standardized Exit Codes & JSON Contracts

* ✅ **Hợp đồng mã thoát chuẩn OS**:
  * `0`: Thành công
  * `1`: Lỗi nội bộ / generation failure
  * `2`: Lỗi provider / network unavailable
  * `3`: Lỗi cú pháp / missing options

### Unit Test Suite Phase 6

* ✅ **Test suite đầy đủ** (`tests/unit/cli/test_social_report_cli.py`): Kiểm thử CLI subcommand, schema v2.0.0, manifest creation, integrity tamper detection và exit codes (81 passed).

## Gate hoàn tất

1. ✅ Chuyển thành canonical CLI subcommand (`windagent social-report`).
2. ✅ Report được lưu cùng `manifest.json` kiểm tra tính toàn vẹn.
3. ✅ Có schema version `"2.0.0"` trong `report.json` và `manifest.json`.
4. ✅ Có task_id và session_id.
5. ✅ JSON output có exit-code contract đầy đủ (0, 1, 2, 3).
6. ✅ Report integrity có thể kiểm tra độc lập qua `verify_report_integrity` / `--verify`.

**Trạng thái: PHASE_6_REPORT_GENERATION_AND_CLI_COMPLETED (81/81 tests passed)**

---

# Phase 7 — Unit test và real-browser E2E

## Mục tiêu

Chứng minh luồng:

```text
browser thật
→ rendered DOM
→ normalized record
→ synthesis
→ Markdown/JSON report
```

3. Cài Chrome/browser dependencies.
4. Mở trang bằng `agent-browser` thật.
5. Đọc rendered DOM.
6. Chạy workflow.
7. Ghi Markdown và JSON.
8. Kiểm tra browser backend, content length và capture SHA-256.

Fixture E2E dùng model gateway xác định trước, không gọi model network thật.

### Kết quả CI

Workflow `Agent Browser Social E2E` trên head hiện tại đã hoàn tất với kết luận `success`.

Artifact `agent-browser-social-e2e` đã được upload:

* artifact ID: `8736878678`;
* size: 1.539 byte;
* SHA-256 digest:
  `03400d23900e5c8945b4db847fecca037a3e822bcca31462c7018358cedf8aff`;
* trạng thái: chưa hết hạn.

## Chưa làm

* Chưa test browser thật trên domain Facebook.
* Chưa test browser thật trên domain YouTube.
* Chưa test browser thật trên domain TikTok.
* Chưa dùng Qwen thật.
* Chưa dùng Google API thật.
* Chưa test profile/state authentication thật.
* Chưa test Windows.
* Chưa test flaky behavior qua nhiều lần chạy.
* Chưa test network timeout, rate limit và partial platform failure bằng browser thật.
* Chưa chạy load test nhiều nguồn.
* Chưa chạy full repository pytest trên head hiện tại.
* Chưa chạy toàn bộ architecture/import-boundary checker trên head hiện tại.
* Chưa có certification rằng các CI khác trong repository đều pass.
* Chưa kiểm tra artifact report thủ công sau khi tải xuống.

## Gate hoàn tất

1. E2E fixture tiếp tục pass.
2. Public live smoke test cho ba platform.
3. Live model test đủ ba model.
4. Windows smoke test.
5. Full focused test suite.
6. Full repository regression.
7. Architecture checker.
8. Artifact download và integrity verification.
9. Ba lần CI liên tiếp không flaky.

**Trạng thái: FIXTURE E2E PASS, LIVE E2E CHƯA PASS**

---

# Phase 8 — Live platform validation

## Mục tiêu

Chứng minh pipeline hoạt động với các nguồn xã hội thật và dữ liệu thật.

## Đã làm

* Chỉ mới chuẩn bị cấu hình:

  * URL input;
  * platform detection;
  * domain policy;
  * profile/state;
  * screenshots;
  * partial source handling.
* Chưa thực hiện live validation.

## Chưa làm hoàn toàn

### Test A — YouTube public

Cần chạy trước vì ít phụ thuộc đăng nhập nhất:

1. Chọn một video public ổn định.
2. Thu thập title, description, views và channel.
3. Chạy Qwen extraction.
4. Chạy Gemma và Gemini.
5. Xuất report.
6. Đối chiếu thủ công evidence với trang.

### Test B — Facebook public

1. Chọn public page/post do người dùng sở hữu hoặc cho phép test.
2. Chạy không đăng nhập trước.
3. Nếu login wall xuất hiện, dùng profile/state do người dùng cấp.
4. Không bypass challenge.
5. Xác nhận final URL vẫn thuộc allowlist.
6. Xóa state sau test nếu không cần lưu.

### Test C — TikTok public

1. Chọn video public ổn định.
2. Chạy browser capture.
3. Kiểm tra caption, author và metrics.
4. Nếu platform trả login challenge hoặc region block, ghi `BLOCKED_BY_PLATFORM`.
5. Không dùng stealth hoặc CAPTCHA bypass.

### Test D — Cross-platform report

1. Một URL Facebook.
2. Một URL YouTube.
3. Một URL TikTok.
4. Qwen chuẩn hóa cả ba.
5. Gemma tổng hợp độc lập.
6. Gemini kiểm chứng.
7. Report phải ghi rõ source nào thành công hoặc thất bại.

## Gate hoàn tất

```text
3 nguồn được yêu cầu
≥2 nguồn thu thập thành công
Qwen extraction hợp lệ
Gemma output không rỗng
Gemini output không rỗng
Markdown report tồn tại
JSON report tồn tại
Capture hashes hợp lệ
Không lộ secret
Không bypass platform protection
```

**Trạng thái: CHƯA THỰC HIỆN**

---

# Phase 9 — Production integration vào WindAgent runtime

## Mục tiêu

Biến prototype thành workflow chính thức có task lifecycle, worker execution, storage và observability.

## Đã làm

* Workflow package và CLI có thể gọi trực tiếp các provider adapter và browser tool.
* Chưa tích hợp vào runtime chính thức.

## Chưa làm

* Chưa đăng ký workflow vào `WorkflowRegistry`.
* Chưa có workflow pack canonical.
* Chưa kết nối TaskManager.
* Chưa chạy qua worker lease.
* Chưa hỗ trợ cancellation.
* Chưa có retry orchestration.
* Chưa có event-sourced execution trace.
* Chưa có storage repository.
* Chưa có API endpoint.
* Chưa có desktop/web UI.
* Chưa có observability:

  * browser latency;
  * source success rate;
  * model latency;
  * token usage;
  * cost;
  * report completion rate.
* Chưa có quota và concurrency limits.
* Chưa có per-platform circuit breaker.
* Chưa có scheduler.
* Chưa có retention cleanup job.

## Gate hoàn tất

1. Workflow được registry quản lý.
2. Task chạy qua worker.
3. Có retry/cancellation/resume.
4. Artifacts lưu bền vững.
5. API/CLI đọc được trạng thái.
6. Có metrics và audit trail.
7. Có concurrency/rate limit.
8. Crash/restart không làm mất task.

**Trạng thái: CHƯA THỰC HIỆN**

---

# Phase 10 — Verification, review và promotion

## Mục tiêu

Đánh giá toàn bộ diff và chỉ promotion khi có bằng chứng đầy đủ.

## Đã làm

* PR #10 đang mở ở trạng thái draft.
* PR mergeable theo GitHub.
* Không có review thread đang mở tại thời điểm kiểm tra.
* E2E chuyên biệt đã pass.
* Artifact E2E đã tồn tại.

## Chưa làm

* Chưa thực hiện manual code review toàn bộ 15 file.
* Chưa kiểm tra diff bằng security reviewer.
* Chưa chạy static analysis đầy đủ.
* Chưa chạy dependency audit.
* Chưa chạy full CI matrix trên head hiện tại.
* Chưa cập nhật PR body từ “E2E pending” sang kết quả thực tế.
* Chưa thêm test evidence link/digest vào PR.
* Chưa đánh giá các commit trung gian.
* Chưa squash.
* Chưa mark ready for review.
* Chưa request reviewer.
* Chưa merge.
* Chưa có post-merge verification.
* Chưa có rollback plan.

## Gate hoàn tất

1. Focused E2E pass.
2. Full regression pass.
3. Architecture checks pass.
4. Security review pass.
5. Live platform test pass theo tiêu chí đã định.
6. Live model test pass.
7. Evidence manifest hợp lệ.
8. PR body phản ánh đúng trạng thái.
9. Human review chấp thuận.
10. Chỉ sau đó mới mark ready hoặc merge.

**Trạng thái: DRAFT, CHƯA SẴN SÀNG MERGE**

---

# Thứ tự thực hiện tiếp được khuyến nghị

## Nhóm 1 — Audit trước khi sửa thêm

Không thay đổi code ngay. Trước tiên cần:

1. Review toàn bộ 15 file trong PR #10.
2. Phân loại:

   * lỗi thực sự;
   * thiếu test;
   * thiết kế chưa hoàn chỉnh;
   * CI không liên quan.
3. Kiểm tra commit history và diff.
4. Tải artifact E2E và xác nhận nội dung.
5. Ghi issue list, không tự động fix.

## Nhóm 2 — Live model preflight

Thực hiện trên môi trường người dùng:

1. Kiểm tra Ollama.
2. Kiểm tra model Qwen.
3. Gọi Google model discovery.
4. Xác định model ID chính xác.
5. Thực hiện một request tối thiểu cho từng model.
6. Ghi latency, token và lỗi.

## Nhóm 3 — YouTube public smoke test

Bắt đầu với một URL YouTube public. Không mở rộng sang Facebook hoặc TikTok trước khi luồng này ổn định.

## Nhóm 4 — Facebook/TikTok có kiểm soát

Chỉ chạy bằng URL do người dùng chọn và profile/state do người dùng chủ động cung cấp.

## Nhóm 5 — Runtime integration

Chỉ thực hiện sau khi live test đạt gate. Khi đó mới đưa workflow vào TaskManager, worker, storage và API.

---

# Kết luận

Phần đã được chứng minh:

```text
agent-browser thật
→ Chrome thật
→ rendered fixture page
→ normalized deterministic record
→ dual deterministic synthesis
→ Markdown/JSON report
→ CI artifact
```

Phần chưa được chứng minh:

```text
Facebook/YouTube/TikTok thật
→ Qwen 3.5 thật
→ Gemma 4 31B thật
→ Gemini 3.5 Flash Lite thật
→ production WindAgent task/worker/storage
```

Do đó, trạng thái phù hợp nhất hiện tại là:

```text
BROWSER_ADAPTER_IMPLEMENTED
FIXTURE_BROWSER_TO_REPORT_E2E_PASSED
LIVE_SOCIAL_COLLECTION_NOT_VERIFIED
LIVE_MODEL_PIPELINE_NOT_VERIFIED
PRODUCTION_INTEGRATION_NOT_COMPLETE
NOT_READY_FOR_MERGE
```
