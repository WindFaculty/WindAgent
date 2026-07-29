# Kế hoạch tiếp tục hoàn thiện Phase 7

## Mục tiêu cuối

Chuyển trạng thái từ:

```text
PHASE_7_CODE_CONVERGED_VERIFICATION_BLOCKED
```

sang:

```text
PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED
READY_FOR_MAIN_PROMOTION
```

Điều kiện bắt buộc:

* Artifact Phase 7 đạt schema thật.
* Không còn placeholder hash hoặc receipt viết thủ công.
* CLI không còn false-positive.
* Các command được phân loại rõ: production, diagnostic hoặc demo.
* GitHub Actions chạy trên chính commit cuối.
* Linux, Windows, SQLite, PostgreSQL, web và desktop đều được xác minh.
* `verified_sha` trỏ đến commit đã được CI kiểm tra, không trỏ đến commit cha.

Commit hiện tại là commit công bố artifact, nhưng vẫn chứa artifact có `commands: []`, `artifact_hashes: {}` và các hash placeholder trong khi verdict là `PASS`.

---

# Luồng phase đề xuất

```text
Phase 0  Correct verdict and freeze baseline
   ↓
Phase 1  Repair artifact protocol
   ↓
Phase 2  Build deterministic evidence generator
   ↓
Phase 3  Repair CLI root detection and architecture checks
   ↓
Phase 4  Remove false runtime claims from CLI
   ↓
Phase 5  Repair GitHub Actions and platform matrix
   ↓
Phase 6  Execute complete verification matrix
   ↓
Phase 7  Publish final evidence and authoritative verdict
   ↓
Phase 8  Open PR, review and promote to main
```

Không được bỏ qua Phase 0–3. Phase 6 chỉ được chạy sau khi toàn bộ verification infrastructure đã được sửa.

---

# Phase 0 — Correct Verdict and Freeze Baseline

## Mục tiêu

Ngăn verdict sai tiếp tục được xem là authoritative và tạo baseline có thể audit trước khi sửa.

## Công việc

1. Tạo branch mới từ commit:

```text
601fd1282be7c4a7ae13f02422b70d5f107aaafd
```

Tên đề xuất:

```text
fix/phase7-verification-integrity
```

2. Không sửa trực tiếp `main`.

3. Hạ verdict hiện tại xuống:

```text
PHASE_7_CODE_CONVERGED_VERIFICATION_BLOCKED
```

4. Cập nhật `phase_verdict.md`:

```yaml
implementation_status: substantially_complete
verification_status: blocked
promotion_status: not_ready
blocking_reasons:
  - artifact_schema_noncompliance
  - unverified_command_receipts
  - architecture_check_false_positive
  - no_ci_run_on_final_commit
  - ci_matrix_configuration_defects
```

5. Mở lại các rủi ro:

| Risk                               | Trạng thái mới |
| ---------------------------------- | -------------- |
| Artifact schema integrity          | OPEN / P0      |
| CI evidence integrity              | OPEN / P0      |
| CLI architecture false-positive    | OPEN / P0      |
| Command receipt authenticity       | OPEN / P0      |
| Cross-platform CI                  | OPEN / P1      |
| Demo data exposed as runtime state | OPEN / P1      |

6. Tạo baseline inventory:

```text
artifacts/architecture_v2_production_hardening/phase_07_repair/baseline/
├── baseline_commit.json
├── invalid_artifact_inventory.json
├── cli_command_classification.json
├── ci_defect_inventory.json
└── baseline_verdict.json
```

## Kiểm thử

Chạy validator trên toàn bộ artifact hiện tại và lưu lỗi, không sửa output:

```bash
python scripts/validate_artifact_schema.py \
  artifacts/architecture_v2_production_hardening/phase_07/*.json
```

Lệnh này được phép fail trong Phase 0.

## Acceptance gate

```text
G0.1 Baseline SHA recorded
G0.2 Invalid artifacts fully inventoried
G0.3 Current PASS verdict withdrawn
G0.4 Repair branch clean
G0.5 No implementation files changed yet
```

## Verdict Phase 0

```text
BASELINE_FROZEN_VERDICT_CORRECTED
```

---

# Phase 1 — Repair Artifact Protocol

## Mục tiêu

Làm rõ artifact protocol và buộc mọi artifact thực phải tuân thủ schema.

Schema hiện yêu cầu command receipt đầy đủ và ít nhất một artifact hash, trong khi nhiều artifact Phase 7 không đáp ứng các điều kiện đó.

## Công việc

### 1.1 Chọn một schema canonical duy nhất

Hiện có hai đường dẫn:

```text
scripts/artifact_schema.json
scripts/schemas/artifact_schema.json
```

Chỉ giữ một source of truth, đề xuất:

```text
scripts/schemas/artifact_protocol_v1.schema.json
```

File còn lại chỉ được:

* xóa; hoặc
* trở thành symlink/copy được generate và kiểm tra hash.

Không được duy trì hai schema thủ công.

### 1.2 Chuẩn hóa hash

Chọn duy nhất một định dạng:

```json
{
  "filename.json": "64_lowercase_hex_characters"
}
```

Không chấp nhận:

```text
sha256:abcd...
abcd1234...
placeholder
```

### 1.3 Giải quyết vòng lặp self-hash

Artifact không nên chứa hash của chính nó vì nội dung thay đổi sau khi thêm hash.

Thiết kế đề xuất:

```text
artifact.json
artifact.json.sha256
```

Hoặc manifest riêng:

```text
artifact_manifest.json
```

với hash của các artifact khác, nhưng không hash chính nó.

### 1.4 Chuẩn hóa command receipt

Mỗi command phải có:

```json
{
  "command": "uv run pytest ...",
  "cwd": ".",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "duration_ms": 1234,
  "exit_code": 0,
  "stdout_tail": "...",
  "stderr_tail": "...",
  "environment": {
    "os": "windows",
    "python": "3.11.x"
  }
}
```

Nên thêm:

* `command_id`
* `expected_exit_codes`
* `result`
* `output_sha256`

### 1.5 Chuẩn hóa warning/failure

Không sử dụng chuỗi đơn:

```json
"warnings": ["something"]
```

Sử dụng object:

```json
{
  "check": "desktop_version",
  "message": "Desktop version differs from product version",
  "severity": "LOW",
  "accepted": true,
  "rationale": "Independent desktop release lifecycle"
}
```

### 1.6 Validator phải hỗ trợ directory/glob

Bổ sung:

```bash
python scripts/validate_artifact_schema.py \
  --directory artifacts/.../phase_07 \
  --recursive
```

Thêm các chế độ:

```text
--schema-only
--semantic
--verify-hashes
--json
--fail-on-warning
```

### 1.7 Không validate chính report đang được ghi

`check_version_consistency.py` hiện ghi trực tiếp report trong quá trình chạy. Nên tách:

```text
run check → return structured result
generate report → separate writer
validate report → separate process
```

## Kiểm thử bắt buộc

* Valid artifact pass.
* Empty commands fail.
* Empty hashes fail.
* Placeholder hash fail.
* Hash prefix fail nếu schema yêu cầu raw hex.
* Self-hash cycle fail.
* Warning sai type fail.
* Receipt thiếu stdout/stderr fail.
* Dirty worktree + PASS fail.
* `verified_sha` không tồn tại trong Git fail.
* `verified_sha` khác HEAD fail khi artifact đánh dấu final.

## Acceptance gate

```text
G1.1 One canonical schema
G1.2 All negative fixtures fail for intended reasons
G1.3 Validator supports production artifact directories
G1.4 Placeholder hashes impossible
G1.5 Self-hash semantics explicitly defined
G1.6 Validator unit tests pass
```

## Verdict Phase 1

```text
ARTIFACT_PROTOCOL_V1_HARDENED
```

---

# Phase 2 — Deterministic Evidence Generation

## Mục tiêu

Loại bỏ artifact và receipt được nhập thủ công. Mọi artifact phải được tạo từ execution thật.

## Công việc

### 2.1 Tạo evidence runner

Đề xuất:

```text
scripts/verification/
├── run_command_receipt.py
├── generate_phase7_evidence.py
├── hash_artifacts.py
├── validate_evidence_bundle.py
└── finalize_verdict.py
```

Ví dụ:

```bash
python scripts/verification/run_command_receipt.py \
  --name full_pytest \
  --cwd . \
  --output artifacts/.../receipts/full_pytest.json \
  -- uv run pytest -q
```

### 2.2 Tạo evidence bundle theo staging directory

Không ghi đè artifact chính ngay trong khi test:

```text
.tmp/phase7-evidence/<run-id>/
```

Luồng:

```text
execute commands
→ capture raw receipts
→ generate reports
→ calculate hashes
→ validate bundle
→ atomically publish final directory
```

Nếu bất kỳ bước nào fail, không cập nhật verdict authoritative.

### 2.3 Capture environment

Mỗi bundle phải có:

```json
{
  "git": {
    "source_sha": "...",
    "verified_sha": "...",
    "branch": "...",
    "worktree_clean": true
  },
  "runtime": {
    "os": "...",
    "python": "...",
    "uv": "...",
    "node": "...",
    "npm": "...",
    "postgres": "..."
  }
}
```

### 2.4 Tạo command registry

Phân loại command theo shell:

```yaml
commands:
  api_dev_windows:
    shell: pwsh
    command:
      - pwsh
      - -NoProfile
      - -File
      - scripts/dev_api.ps1
      - -NoSync
  pytest:
    shell: process
    command:
      - uv
      - run
      - pytest
      - -q
```

Không được chạy PowerShell bằng Python như receipt hiện tại mô tả.

### 2.5 Kiểm tra receipt authenticity

Mỗi receipt cần:

* command canonicalized;
* output hash;
* process exit code;
* timestamp thực;
* environment identity;
* optional nonce/run ID.

### 2.6 Bổ sung unit/integration tests

Test evidence generator với:

* command success;
* command failure;
* timeout;
* interrupted process;
* invalid UTF-8;
* large stdout;
* Windows path;
* command containing secrets;
* output redaction.

## Acceptance gate

```text
G2.1 No Phase 7 artifact is manually authored
G2.2 Every PASS claim traces to command receipt
G2.3 Every receipt traces to captured output
G2.4 Failed run cannot publish final verdict
G2.5 Secrets are redacted before persistence
G2.6 Generated bundle passes schema validation
```

## Verdict Phase 2

```text
DETERMINISTIC_EVIDENCE_PIPELINE_READY
```

---

# Phase 3 — CLI Root Detection and Architecture Integrity

## Mục tiêu

Loại bỏ khả năng CLI trả `PASS` khi checker script không được chạy.

CLI hiện tìm `pyproject.toml` gần nhất, nên có thể dừng tại `apps/cli/pyproject.toml`, rồi bỏ qua checker không tồn tại nhưng vẫn trả thành công.

## Công việc

### 3.1 Tạo root locator dùng chung

Đề xuất:

```text
core/windagent_core/config/repository_root.py
```

API:

```python
def find_repository_root(start: Path | None = None) -> Path:
    ...
```

Root chỉ hợp lệ khi có đầy đủ marker:

```text
pyproject.toml
configs/architecture/scaffold_v2.yaml
scripts/check_architecture_imports.py
```

Hoặc root `pyproject.toml` có:

```toml
[tool.uv.workspace]
```

### 3.2 Fail-closed

`architecture-check` phải fail nếu thiếu bất kỳ checker bắt buộc:

```text
exit 2: repository root not found
exit 3: required checker missing
exit 4: checker execution error
exit 1: architecture violation
exit 0: all required checks executed and passed
```

### 3.3 Structured output

JSON output:

```json
{
  "repository_root": "...",
  "checks": [
    {
      "name": "scaffold",
      "executed": true,
      "exit_code": 0
    },
    {
      "name": "import_boundaries",
      "executed": true,
      "exit_code": 0
    }
  ],
  "all_required_checks_executed": true,
  "verdict": "PASS"
}
```

### 3.4 Sửa test subdirectory

Test phải thực sự đổi `cwd`:

```text
repo root
apps/
apps/cli/
apps/api/windagent_api/
temporary external directory with --root
```

### 3.5 Regression tests

* Missing scaffold script → fail.
* Missing architecture checker → fail.
* Checker crashes → fail.
* Checker times out → fail.
* Invalid root → typed error.
* Run from installed package outside source tree → explicit unsupported/error, không empty PASS.
* Run from symlink path.
* Run from Windows drive.
* Run from path chứa khoảng trắng.

## Acceptance gate

```text
G3.1 Architecture check executes every mandatory checker
G3.2 Missing checker cannot PASS
G3.3 Root detection works from all repository subdirectories
G3.4 Invalid root produces typed non-zero exit
G3.5 JSON output records executed commands
```

## Verdict Phase 3

```text
CLI_ARCHITECTURE_CHECK_FAIL_CLOSED
```

---

# Phase 4 — CLI Runtime Truthfulness

## Mục tiêu

Không để dữ liệu demo được trình bày như trạng thái production thật.

Hiện các command `status`, `task list`, `task inspect`, `replay`, `providers`, `tools` và `eval` chứa nhiều kết quả hard-code.

## Chiến lược

Mỗi command phải thuộc một trong ba loại:

```text
LIVE       Truy vấn runtime/storage thật
OFFLINE    Truy vấn dữ liệu local thật
DEMO       Chỉ chạy khi người dùng truyền --demo
```

Không được ngầm fallback từ LIVE sang DEMO.

## Công việc

### 4.1 `status`

Thay dữ liệu hard-code bằng:

* API health adapter;
* worker status query;
* queue repository;
* lease repository;
* database readiness.

Nếu runtime không chạy:

```text
status: UNAVAILABLE
exit code: 2
```

Không trả `ONLINE`.

### 4.2 `task list`

Truy vấn task repository thật:

```text
--status
--limit
--after
--session-id
```

Không có task thì trả danh sách rỗng.

### 4.3 `task inspect`

* ID không tồn tại → exit 4.
* Không dùng `task_demo_01` làm default.
* `task_id` trở thành argument bắt buộc.

### 4.4 `replay`

Truy vấn trace/event store thật.

Chỉ trả `deterministic_parity=100%` nếu thực sự so sánh:

* event count;
* ordering;
* state hash;
* output hash.

### 4.5 `providers`

Sử dụng kết quả từ canonical registry thật. Không khởi tạo registry rồi bỏ qua.

Phân biệt:

```text
configured
available
healthy
authenticated
rate_limited
```

### 4.6 `tools`

Đọc từ `ToolRegistry` thật và hiển thị permission/risk metadata.

### 4.7 `eval`

Thực thi eval suite hoặc đọc artifact eval đã được verify.

Không được hard-code:

```text
92.5%
100%
PASSED
```

### 4.8 Demo mode

Nếu cần giữ demo:

```bash
windagent task list --demo
windagent eval --demo
```

Output phải có:

```json
{
  "data_source": "DEMO",
  "non_production": true
}
```

## Kiểm thử

Mỗi command cần ít nhất:

* happy path;
* empty state;
* unavailable dependency;
* invalid input;
* timeout;
* JSON schema;
* exit code;
* no hidden demo fallback.

## Acceptance gate

```text
G4.1 No production command returns fabricated runtime data
G4.2 Demo behavior requires explicit --demo
G4.3 Data source appears in JSON output
G4.4 Exit codes distinguish unavailable/not-found/failure
G4.5 CLI integration tests use real temporary storage
```

## Verdict Phase 4

```text
CLI_RUNTIME_SURFACES_TRUTHFUL
```

---

# Phase 5 — GitHub Actions Repair

## Mục tiêu

Tạo CI thực sự chạy được trên branch sửa chữa và kiểm tra đúng các hệ điều hành/database.

## Công việc

### 5.1 Sửa trigger

Hiện workflow không bao phủ `hardening/*`.

Đề xuất:

```yaml
on:
  push:
    branches:
      - main
      - "feat/**"
      - "fix/**"
      - "hardening/**"
  pull_request:
    branches:
      - main
  workflow_dispatch:
```

### 5.2 Tách job theo trách nhiệm

```text
artifact-protocol
version-consistency
architecture-boundaries
python-unit
python-integration-sqlite
python-integration-postgres
runtime-smoke
cli-contract
web-test
web-build
desktop-test
desktop-build
final-evidence
```

### 5.3 Sửa PostgreSQL service

Không đặt `services` bên trong matrix include mà không binding.

Tạo job PostgreSQL riêng:

```yaml
services:
  postgres:
    image: postgres:16-alpine
```

Chỉ chạy trên Ubuntu nếu chưa có nhu cầu PostgreSQL trên Windows.

### 5.4 Sửa shell cross-platform

Không dùng Bash syntax trên Windows runner.

Sử dụng:

```yaml
env:
  WINDAGENT_DATABASE_URL: ...
```

hoặc step riêng theo OS:

```yaml
if: runner.os == 'Windows'
shell: pwsh
```

### 5.5 Desktop lockfile

Chọn một package manager canonical:

```text
npm + package-lock.json
```

Sau đó:

```bash
npm ci
```

Nếu không muốn commit lockfile, dùng `npm install`, nhưng không khuyến nghị cho CI reproducibility.

### 5.6 Validate production artifacts

CI phải chạy:

```bash
uv run python scripts/validate_artifact_schema.py \
  --directory artifacts/architecture_v2_production_hardening/phase_07 \
  --verify-hashes
```

Không chỉ validate fixture.

### 5.7 Version checker

Sửa hard-coded version scan để không bị vô hiệu hóa khi version bằng `0.3.0`.

Worker/API/CLI import failure phải là error trong production CI.

### 5.8 Upload raw receipts

Mỗi CI job upload:

```text
pytest.xml
coverage.xml
command receipts
environment manifest
logs
artifact validation report
```

### 5.9 Required checks

Cấu hình branch protection để ít nhất yêu cầu:

```text
artifact-protocol
version-consistency
architecture-boundaries
python-unit
python-integration-sqlite
python-integration-postgres
runtime-smoke
web-test
desktop-test
final-evidence
```

## Acceptance gate

```text
G5.1 Workflow triggers on repair branch
G5.2 PostgreSQL service starts and health-checks
G5.3 Windows jobs use valid PowerShell commands
G5.4 Desktop npm ci succeeds from committed lockfile
G5.5 Production artifacts are schema-validated
G5.6 No continue-on-error or exit masking on mandatory gates
```

## Verdict Phase 5

```text
CI_MATRIX_FAIL_CLOSED_READY
```

---

# Phase 6 — Complete Verification Matrix

## Mục tiêu

Chạy lại toàn bộ hệ thống trên commit ứng viên cuối cùng và tạo evidence mới.

## Nguyên tắc

* Không tái sử dụng kết quả từ `09ce71b`.
* Không dùng receipt cũ.
* Không sửa code sau khi bắt đầu final verification.
* Nếu cần sửa, tạo commit mới và chạy lại toàn bộ Phase 6.

## Matrix bắt buộc

### Python

| OS      | Database   | Test                                |
| ------- | ---------- | ----------------------------------- |
| Ubuntu  | SQLite     | full unit + integration             |
| Ubuntu  | PostgreSQL | full integration + fencing          |
| Windows | SQLite     | full unit + integration             |
| Windows | PostgreSQL | tùy chọn nếu được hỗ trợ chính thức |

### Frontend

| App     | OS      | Gate                                      |
| ------- | ------- | ----------------------------------------- |
| Web     | Ubuntu  | install, test, coverage, typecheck, build |
| Web     | Windows | install, test, typecheck, build           |
| Desktop | Ubuntu  | install, test, typecheck, build           |
| Desktop | Windows | install, test, typecheck, build           |

### Architecture

```bash
uv run python scripts/scaffold_architecture_v2.py --check
uv run python scripts/check_architecture_imports.py
uv run python scripts/check_no_legacy_orchestration.py
uv run python scripts/check_version_consistency.py
```

### Artifact

```bash
uv run python scripts/validate_artifact_schema.py \
  --directory artifacts/.../phase_07 \
  --verify-hashes
```

### CLI

```text
--version
doctor
architecture-check
status
task list
task inspect <real-id>
replay <real-trace-id>
providers
tools
eval
worker-status
provider-test
```

Các command cần dependency thật phải chạy trên temporary composed runtime, không dùng output giả.

### Runtime smoke

* FastAPI startup/shutdown.
* Internal architecture endpoint.
* API version.
* Worker startup/shutdown.
* Worker lease acquisition/release.
* CLI composition.
* SQLite migration.
* PostgreSQL migration.
* Event replay.
* Session recovery.
* Web API client contract.

### Negative injections

* Package version mismatch.
* Invalid artifact.
* Broken hash.
* Missing architecture checker.
* Dirty worktree.
* API/worker version mismatch.
* PostgreSQL unavailable.
* Desktop lockfile mismatch.
* Demo fallback attempted in production mode.

Mỗi injection phải chứng minh gate fail với exit code khác 0.

## Acceptance gate

```text
G6.1 All mandatory CI jobs green
G6.2 Full pytest has zero failure and zero collection error
G6.3 Architecture violations = 0
G6.4 Production artifact validation = PASS
G6.5 Every negative injection is rejected
G6.6 No unexplained skip
G6.7 No fabricated CLI output
G6.8 Worktree clean at verified SHA
```

Một skip chỉ được chấp nhận khi có:

* test ID;
* lý do;
* owner;
* expiry date;
* xác nhận không phải mandatory gate.

## Verdict Phase 6

```text
PHASE_7_FULL_VERIFICATION_PASSED
```

---

# Phase 7 — Final Evidence and Authoritative Verdict

## Mục tiêu

Xuất bản evidence bundle nhất quán, được tạo từ commit đã chạy CI.

## Quy tắc SHA

Phân biệt:

```text
source_sha
implementation_sha
verification_candidate_sha
verified_sha
evidence_publish_sha
```

Không thể vừa thêm artifact vào commit sau vừa tuyên bố commit trước là final verified state mà không nói rõ.

Thiết kế đề xuất:

1. Commit implementation candidate.
2. CI chạy và verify candidate.
3. CI tạo evidence bundle dưới dạng workflow artifact.
4. Bot hoặc finalization process commit evidence.
5. Evidence ghi:

```json
{
  "verified_sha": "<implementation-candidate>",
  "evidence_publish_sha": "<artifact-only-commit>"
}
```

6. Chạy một lightweight integrity CI trên evidence publish commit.

## Artifact final

```text
artifacts/architecture_v2_production_hardening/phase_07/final/
├── environment_manifest.json
├── version_manifest.json
├── version_consistency_report.json
├── architecture_report.json
├── scaffold_report.json
├── artifact_schema_report.json
├── cli_contract_report.json
├── runtime_smoke_report.json
├── python_test_matrix.json
├── frontend_test_matrix.json
├── database_matrix.json
├── negative_injection_report.json
├── ci_run_manifest.json
├── artifact_manifest.json
├── risk_register.md
└── final_verdict.json
```

## `final_verdict.json`

Chỉ được `PASS` nếu được tính từ gates:

```json
{
  "verdict": "PASS",
  "verdict_name": "PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED",
  "gates": {
    "artifact_protocol": true,
    "version_authority": true,
    "architecture_integrity": true,
    "cli_truthfulness": true,
    "python_matrix": true,
    "frontend_matrix": true,
    "database_matrix": true,
    "negative_injections": true,
    "ci_verified": true
  },
  "manual_override": false
}
```

Không cho phép author nhập trực tiếp verdict `PASS`. Verdict phải được derive từ gate values.

## Acceptance gate

```text
G7.1 All artifacts schema-valid
G7.2 All hashes verified
G7.3 CI run IDs recorded
G7.4 verified_sha matches tested candidate
G7.5 evidence_publish_sha explicitly recorded
G7.6 Final verdict is computed, not manually declared
G7.7 Risk register has no OPEN P0/P1 risks
```

## Verdict Phase 7

```text
PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED
```

---

# Phase 8 — Pull Request and Main Promotion

## Mục tiêu

Đưa toàn bộ Architecture V2 đã sửa vào `main` qua một PR có thể review và rollback.

## Công việc

### 8.1 Rebase/update branch

So sánh với `main` trước khi mở PR:

```bash
git fetch origin
git rebase origin/main
```

Nếu `main` vẫn rất cũ so với branch kiến trúc, nên mở một integration PR riêng, không squash toàn bộ lịch sử mà không review.

### 8.2 Draft PR

Tiêu đề đề xuất:

```text
fix(phase7): harden verification integrity and publish authoritative evidence
```

PR body cần có:

* starting SHA;
* implementation candidate SHA;
* verified SHA;
* evidence publish SHA;
* defects sửa;
* test matrix;
* CI run IDs;
* accepted risks;
* rollback procedure.

### 8.3 Review checklist

Reviewer phải xác nhận:

* không có artifact placeholder;
* không có receipt thủ công;
* không có CLI empty-success;
* không có demo fallback;
* CI chạy trên đúng SHA;
* PostgreSQL service thật sự hoạt động;
* desktop lockfile tồn tại;
* artifact schema gate kiểm tra artifact thật.

### 8.4 Merge strategy

Khuyến nghị:

```text
merge commit
```

thay vì squash nếu cần giữ chuỗi implementation SHA → verified SHA → evidence SHA.

Nếu dùng squash, phải chạy lại required checks trên squash result trước khi coi `main` là verified.

### 8.5 Post-merge smoke

Trên `main`:

```bash
uv sync --all-packages
uv run python scripts/check_version_consistency.py
uv run python scripts/check_architecture_imports.py
uv run python scripts/validate_artifact_schema.py --directory ...
uv run pytest -q
```

Chạy thêm web/desktop build.

### 8.6 Rollback

Tạo rollback receipt:

```text
rollback_target_sha
rollback_commands
database_compatibility
artifact_compatibility
expected_downtime
```

## Acceptance gate

```text
G8.1 PR required checks green
G8.2 No unresolved P0/P1 review thread
G8.3 Merge result receives post-merge verification
G8.4 main contains authoritative verdict
G8.5 Rollback procedure validated
```

## Verdict Phase 8

```text
PHASE_7_PROMOTED_TO_MAIN
```

---

# Dependency và khả năng chạy song song

| Phase | Phụ thuộc     | Có thể chạy song song        |
| ----- | ------------- | ---------------------------- |
| 0     | Không         | Không                        |
| 1     | Phase 0       | Một phần với Phase 3         |
| 2     | Phase 1       | Không                        |
| 3     | Phase 0       | Có thể song song Phase 1     |
| 4     | Phase 3       | Có thể song song đầu Phase 5 |
| 5     | Phase 1, 2, 3 | Một phần với Phase 4         |
| 6     | Phase 1–5     | Không                        |
| 7     | Phase 6       | Không                        |
| 8     | Phase 7       | Không                        |

Critical path:

```text
0 → 1 → 2 → 5 → 6 → 7 → 8
        ↘ 3 → 4 ↗
```

---

# Phân chia commit đề xuất

Không nên thực hiện tất cả trong một commit.

```text
1. docs(phase7): correct provisional verdict and freeze repair baseline
2. fix(artifacts): harden canonical artifact protocol and validator
3. feat(verification): add deterministic command receipt generator
4. fix(cli): make repository root detection fail closed
5. fix(cli): replace fabricated runtime responses with real queries
6. fix(ci): repair workflow triggers and cross-platform matrix
7. test(phase7): add verification integrity regression suite
8. ci(phase7): execute and publish complete verification evidence
9. docs(phase7): publish authoritative final verdict
```

---

# Thứ tự ưu tiên lỗi

## P0 — Phải sửa trước

1. Artifact thật không đạt schema.
2. Placeholder hoặc empty hash.
3. Receipt không phản ánh execution thật.
4. CLI architecture checker false-positive.
5. CI không validate artifact sản xuất.
6. Không có CI run trên verified commit.

## P1 — Phải sửa trước promotion

1. PostgreSQL service CI.
2. Windows shell syntax.
3. Desktop lockfile.
4. CLI trả dữ liệu demo như dữ liệu thật.
5. Version checker bỏ qua hard-coded scan.
6. Import failure chỉ tạo warning.

## P2 — Có thể xử lý sau khi correctness đạt

1. Tối ưu thời gian CI.
2. Chia cache Python/Node.
3. Chuẩn hóa naming artifact.
4. Tự động tạo release notes.
5. Dashboard lịch sử verification.

---

# Final gate toàn chương trình

Chỉ được công bố hoàn thành khi lệnh tổng hợp tương đương sau trả exit code 0:

```bash
uv run python scripts/verification/finalize_phase7.py \
  --verified-sha "$(git rev-parse HEAD)" \
  --require-clean-worktree \
  --require-ci \
  --require-python-matrix \
  --require-frontend-matrix \
  --require-postgresql \
  --require-negative-injections \
  --verify-artifact-hashes \
  --fail-on-open-risk P0 \
  --fail-on-open-risk P1
```

Output hợp lệ cuối cùng:

```text
PHASE_7_VERSION_DOCUMENTATION_VERDICT_CONVERGED
READY_FOR_MAIN_PROMOTION
```

Bất kỳ gate bắt buộc nào không đạt, verdict phải tự động hạ thành:

```text
BLOCKED
```

Không được dùng `PASS` kèm warning để che một gate chưa chạy.
