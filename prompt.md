Bạn đang tiếp tục chương trình **WindAgent Core Canonical Full Adoption — Phase 14 Completion** trong repository:

```text
WindFaculty/WindAgent
```

## Mục tiêu cuối

Hoàn thiện Phase 14 từ trạng thái:

```text
CORE_CANONICAL_VERIFIED_READY_FOR_STAGING
```

lên:

```text
CORE_CANONICAL_FULL_ADOPTION_VERIFIED
```

Chỉ được phát hành verdict cuối khi toàn bộ backend test, clean-clone verification, multi-replica fencing và rollback rehearsal thực sự đạt yêu cầu.

Không được đổi verdict bằng cách bỏ qua test, hạ acceptance gate, thêm `xfail`, thêm `skip`, mock sai bản chất distributed test hoặc ghi nhận kết quả chưa chạy là PASS.

---

# 1. Xác minh điểm bắt đầu

Trước khi sửa code:

1. Xác định repository root.
2. Ghi nhận:

   * current branch;
   * current HEAD SHA;
   * upstream branch;
   * worktree status;
   * stash list;
   * Python và `uv` version;
   * Docker availability;
   * GitHub CLI authentication;
   * các artifact Phase 14 hiện có.
3. Tìm chính xác:

   * nhánh chứa `artifacts/core_canonical/phase_14/final/`;
   * commit đã sinh `final_verdict.json`;
   * test command đã tạo `backend_pytest_passed: false`.
4. Không mặc định `main` hoặc một SHA từ báo cáo cũ là execution base.
5. Không làm mất thay đổi chưa commit và không xóa stash.
6. Nếu worktree không sạch, tạo backup patch hoặc stash có tên rõ ràng trước khi tiếp tục.
7. Tạo nhánh continuation từ đúng Phase 14 HEAD:

```text
fix/core-canonical-phase-14-full-adoption
```

Nếu nhánh này đã tồn tại, xác minh lịch sử rồi tiếp tục trên nhánh đó, không force-reset và không rewrite commit đã push.

Tạo:

```text
artifacts/core_canonical/phase_14_completion/baseline/
├── repository_state.json
├── environment_manifest.json
├── git_status.txt
├── git_log.txt
├── existing_phase_14_artifacts.json
└── starting_verdict.json
```

---

# 2. Nguyên tắc thực hiện

* Fail closed.
* Không sửa acceptance criteria để hợp thức hóa kết quả.
* Không tuyên bố lỗi backend “không liên quan core” rồi bỏ qua.
* Phân biệt rõ:

  * canonical domain correctness;
  * backend runtime adoption;
  * distributed safety;
  * rollback safety.
* Ưu tiên sửa root cause thay vì vá test.
* Không thay đổi public API nếu không bắt buộc.
* Không làm mất backward compatibility nếu chưa có migration plan.
* Không đưa secret hoặc API key plaintext vào source, log hay artifact.
* Không merge vào `main`.
* Không đánh dấu PR ready.
* Commit theo từng phase logic.
* Push branch và mở hoặc cập nhật draft PR sau khi hoàn tất.
* Mọi artifact phải chứa execution SHA, timestamp, command, exit code và SHA-256 khi phù hợp.

---

# 3. Phase 14A — Reconcile root/backend test gates

Điều tra sự không nhất quán:

```text
top-level pytest passed
backend_pytest_passed: false
```

Chạy riêng biệt, lưu đầy đủ stdout, stderr và exit code:

```bash
uv run pytest --collect-only -q
uv run pytest apps/backend/tests --collect-only -q
uv run pytest -q
uv run pytest apps/backend/tests -q
```

Nếu repository yêu cầu chạy từ `apps/backend`, chạy thêm:

```bash
cd apps/backend
uv run pytest --collect-only -q
uv run pytest -q
```

Không dừng ở failure đầu tiên. Thu thập toàn bộ failure và phân loại theo taxonomy:

```text
MISSING_APP_STATE
WRONG_SERVICE_TYPE
LIFESPAN_NOT_STARTED
STALE_LEGACY_IMPORT
DEPENDENCY_OVERRIDE_MISMATCH
DATABASE_LIFECYCLE
CROSS_TEST_STATE_LEAK
IMPORT_TIME_CONFIGURATION
OPTIONAL_SERVICE_NOT_AVAILABLE
COLLECTION_SCOPE_MISMATCH
PYTEST_CONFIG_MISMATCH
UNKNOWN
```

So sánh:

* số test collected;
* test ID khác nhau;
* marker;
* skip và xfail;
* pytest config được load;
* working directory;
* `sys.path`;
* environment variables;
* plugin;
* dependency version;
* test discovery pattern;
* warning có thể ảnh hưởng kết quả.

Tạo:

```text
artifacts/core_canonical/phase_14_completion/test_reconciliation/
├── root_collection.txt
├── backend_collection.txt
├── root_test_result.txt
├── backend_test_result.txt
├── backend_cwd_test_result.txt
├── test_scope_diff.json
├── pytest_config_manifest.json
├── environment_diff.json
├── failing_test_inventory.json
└── root_cause_report.md
```

Acceptance gate:

```json
{
  "root_backend_collection_difference_explained": true,
  "all_backend_failures_classified": true,
  "unknown_failures": 0
}
```

Commit:

```text
test(core): reconcile Phase 14 backend and root test gates
```

---

# 4. Phase 14B — Repair backend composition root

Phân tích app-state wiring hiện tại, đặc biệt:

* service được khởi tạo trực tiếp trong FastAPI lifespan;
* service được gắn rời rạc lên `app.state`;
* router đọc trực tiếp nhiều thuộc tính `request.app.state.*`;
* test import singleton global app;
* test sửa global config hoặc environment sau import;
* state có khả năng bị chia sẻ giữa các test;
* optional service có thể không được inject nhất quán.

Thiết kế composition root rõ ràng, ưu tiên cấu trúc tương đương:

```text
apps/backend/bootstrap/
├── application.py
├── container.py
├── dependencies.py
├── lifecycle.py
└── validation.py
```

Tạo typed application container chứa các dependency bắt buộc. Ví dụ:

```python
@dataclass
class ApplicationContainer:
    db: DatabasePort
    event_bus: EventBusPort
    session_service: SessionServicePort
    workflow_service: WorkflowServicePort
    route_lock_service: RouteLockPort
    execution_runtime: ExecutionRuntimePort
    recovery_service: RecoveryPort
```

Yêu cầu:

1. Có `create_app(...)` hoặc app factory tương đương.
2. Cấu hình runtime được resolve khi tạo app, không phụ thuộc vào mutable import-time globals.
3. Mỗi test có thể tạo application instance độc lập.
4. Không sửa trực tiếp `main.DB_URL` trong test.
5. Các router ưu tiên dependency injection hoặc typed container accessor.
6. Startup validation phải phát hiện dependency bắt buộc bị thiếu.
7. Optional integration phải có explicit optional port, null adapter hoặc disabled state rõ ràng.
8. Canonical contracts trong `core/contracts` phải là boundary chính thức.
9. Không tạo duplicate domain models trong bootstrap.
10. Nếu cần compatibility aliases trên `app.state`, aliases phải trỏ đến cùng canonical instance và được đánh dấu deprecated.
11. Shutdown phải đóng resource đúng thứ tự và không để background task, DB handle hoặc file handle rò rỉ.
12. Không phá API contract hiện tại.

Không thực hiện một refactor khổng lồ không liên quan. Chỉ thay đổi đủ để backend adoption ổn định và kiểm thử được.

Tạo test:

* container completeness;
* startup validation;
* canonical service identity;
* two-app isolation;
* DB isolation;
* event bus isolation;
* feature flag isolation;
* optional integration matrix;
* clean shutdown;
* compatibility state alias identity.

Acceptance gate:

```json
{
  "typed_container_implemented": true,
  "app_factory_available": true,
  "required_dependencies_validated": true,
  "mutable_import_time_test_config_removed": true,
  "canonical_runtime_identity_verified": true,
  "fresh_app_isolation_verified": true,
  "public_api_regression_detected": false
}
```

Commit:

```text
fix(backend): replace fragile app-state wiring with canonical composition root
```

---

# 5. Phase 14C — Make backend adoption fully green

Sửa toàn bộ backend unit và integration failures dựa trên root-cause inventory.

Không được:

* chỉ sửa expected value để test pass;
* thêm blanket exception handling;
* nuốt lỗi bằng `except Exception: pass`;
* thay production adapter bằng mock ngoài test;
* bỏ test khỏi discovery;
* giảm số test;
* đổi integration test thành unit test giả;
* xóa assertion quan trọng.

Chạy:

```bash
uv run pytest apps/backend/tests -q
uv run pytest tests -q
uv run pytest -q
```

Chạy thêm từng nhóm test liên quan tối thiểu:

```text
core/domain
core/contracts
core/events
core/errors
core/config
core/security
backend startup/lifespan
sessions
workflow
orchestration
route lock
recovery
events
providers
migrations
security
```

Chạy kiểm tra thứ tự và isolation nếu có plugin phù hợp. Nếu không, chạy suite theo nhiều thứ tự hoặc seed deterministic riêng.

Thực hiện clean-clone verification trong thư mục tạm:

1. Clone branch hiện tại.
2. Cài dependency từ lockfile.
3. Không dùng file local ngoài repository.
4. Chạy migration/setup cần thiết.
5. Chạy backend suite.
6. Chạy top-level suite.
7. Xác minh artifact generator chạy được từ clean clone.

Tạo:

```text
artifacts/core_canonical/phase_14_completion/backend_adoption/
├── focused_test_results/
├── backend_full_test.txt
├── top_level_test.txt
├── clean_clone_commands.txt
├── clean_clone_test_result.txt
├── test_summary.json
├── canonical_identity_report.json
├── app_isolation_report.json
└── backend_adoption_receipt.json
```

Gate bắt buộc:

```json
{
  "backend_pytest_passed": true,
  "backend_tests_failed": 0,
  "top_level_pytest_passed": true,
  "clean_clone_verified": true,
  "unexplained_skips": 0,
  "unexpected_xfails": 0,
  "canonical_runtime_identity_verified": true,
  "fresh_app_isolation_verified": true
}
```

Nếu backend suite chưa xanh, dừng promotion và giữ verdict fail-closed.

Commit:

```text
fix(core): complete backend adoption of canonical contracts
```

---

# 6. Phase 14D — Multi-replica fencing verification

Mục tiêu là chứng minh fencing trong môi trường dùng shared database thực, không chỉ SQLite hoặc in-memory lock.

Ưu tiên tạo reproducible staging harness bằng Docker Compose:

```text
artifacts hoặc infra test harness:
- PostgreSQL
- 3 backend/worker replicas
- shared queue/cache nếu production cần
- migration/init job
- test driver
```

Không dùng SQLite để tuyên bố distributed fencing đã pass.

Kịch bản bắt buộc:

1. Hai replica đồng thời acquire cùng lease.

   * Chính xác một replica thắng.

2. Replica dùng stale fencing token ghi state.

   * Write phải bị từ chối.

3. Lease hết hạn rồi được replica khác takeover.

   * `lease_generation` hoặc fencing token phải tăng đơn điệu.

4. Kill replica đang giữ lease giữa execution.

   * Replica khác takeover an toàn.

5. Replica cũ quay lại sau network delay.

   * Không được ghi đè state mới.

6. Hai worker đồng thời hoàn thành cùng task.

   * Chỉ một terminal transition được chấp nhận.

7. Retry sau timeout.

   * Không sinh duplicate side effect hoặc duplicate terminal event.

8. Restart toàn bộ cluster.

   * Recovery phải hội tụ về một trạng thái duy nhất.

9. Chạy tải cạnh tranh nhiều task.

   * Không split brain.
   * Không duplicate ownership.
   * Không stale write accepted.

10. Xác minh audit event có:

    * replica ID;
    * task/run ID;
    * lease owner;
    * fencing token;
    * lease generation;
    * transition result;
    * rejection reason.

Nếu Docker có sẵn, chạy harness local.

Nếu Docker không có hoặc staging cluster không truy cập được:

* vẫn phải tạo đầy đủ reproducible harness;
* thêm GitHub Actions workflow chạy PostgreSQL và multi-replica test;
* kiểm tra syntax/config local;
* không tuyên bố multi-replica PASS;
* verdict phải giữ ở mức staging pending cho đến khi CI thực sự chạy xanh.

Tạo:

```text
artifacts/core_canonical/phase_14_completion/fencing/
├── environment.json
├── compose_config.txt
├── migration_log.txt
├── replica_logs/
├── lease_transition_trace.jsonl
├── stale_write_rejections.json
├── duplicate_execution_audit.json
├── recovery_convergence_report.json
├── load_test_summary.json
└── fencing_receipt.json
```

Gate:

```json
{
  "production_equivalent_shared_db_used": true,
  "replica_count": 3,
  "multi_replica_fencing_passed": true,
  "stale_token_writes_accepted": 0,
  "duplicate_terminal_transitions": 0,
  "duplicate_side_effects": 0,
  "split_brain_detected": false,
  "recovery_converged": true
}
```

Commit:

```text
test(core): verify multi-replica lease fencing and recovery
```

---

# 7. Phase 14E — Rollback rehearsal

Thực hiện rehearsal theo chu trình release thực:

```text
N-1 deploy
→ migrate/deploy canonical-core N
→ create and mutate representative data
→ disable v2 feature flags where supported
→ rollback application to N-1
→ verify compatibility and data integrity
→ forward deploy N again
→ verify recovery
```

Phải kiểm tra:

* migration upgrade;
* migration downgrade nếu được hỗ trợ;
* backward-compatible schema;
* release N-1 đọc được dữ liệu sau khi N chạy;
* consumer cũ xử lý hoặc bỏ qua event mới an toàn;
* session/task/workflow/event/audit data không mất;
* secrets vẫn mã hóa;
* rollback không tạo plaintext secrets;
* feature flag rollback thực sự chuyển runtime;
* recovery sau rollback;
* forward deploy lại;
* migration idempotency;
* no destructive change trong adoption release nếu chưa qua expand/contract.

Nếu migration không downgrade an toàn, phải chứng minh operational rollback bằng backward-compatible expand migration và app rollback. Không giả tạo downgrade chỉ để đạt gate.

Dữ liệu rehearsal tối thiểu:

* canonical domain objects;
* workflow/task đang chạy;
* completed task;
* failed/retry task;
* route lock/lease;
* execution events;
* provider configuration với encrypted secret;
* feature flags;
* recovery state.

Tạo:

```text
artifacts/core_canonical/phase_14_completion/rollback/
├── n_minus_1_manifest.json
├── release_n_manifest.json
├── migration_upgrade_log.txt
├── pre_rollback_state.json
├── rollback_log.txt
├── post_rollback_state.json
├── forward_deploy_log.txt
├── final_state.json
├── data_integrity_diff.json
├── secret_scan_result.json
└── rollback_receipt.json
```

Gate:

```json
{
  "rollback_rehearsal_passed": true,
  "data_loss_detected": false,
  "schema_incompatibility_detected": false,
  "plaintext_secret_detected": false,
  "recovery_after_rollback_passed": true,
  "forward_deploy_after_rollback_passed": true
}
```

Commit:

```text
test(core): rehearse canonical adoption rollback and forward recovery
```

---

# 8. Phase 14F — Full regression and security verification

Chạy lại toàn bộ existing canonical gates:

* zero duplicate models;
* zero forbidden imports;
* core dependency direction;
* event taxonomy;
* config/domain separation;
* plaintext secret scan;
* migration verification;
* feature flags;
* backend tests;
* top-level tests;
* clean clone;
* fencing;
* rollback.

Kiểm tra thêm:

```text
core/domain không import config, framework, ORM hoặc provider
core/contracts không phụ thuộc app implementation
core/events dùng taxonomy canonical
core/security không log secret
backend adapter tuân thủ canonical contracts
legacy compatibility layer không tạo model duplicate
```

Không xóa compatibility layer chỉ để đạt zero forbidden imports nếu runtime cũ vẫn cần nó. Thay vào đó, cô lập adapter đúng boundary và ghi nhận removal plan.

Tạo:

```text
artifacts/core_canonical/phase_14_completion/final/
├── commands.log
├── test_matrix.json
├── security_scan.json
├── dependency_validation.json
├── migration_validation.json
├── fencing_receipt.json
├── rollback_receipt.json
├── artifact_manifest.json
├── artifact_hashes.sha256
├── final_report.md
└── final_verdict.json
```

---

# 9. Quy tắc final verdict

Chỉ phát hành:

```text
CORE_CANONICAL_FULL_ADOPTION_VERIFIED
```

khi tất cả đều đúng:

```json
{
  "zero_duplicate_models": true,
  "zero_forbidden_imports": true,
  "zero_plaintext_secrets": true,
  "event_taxonomy_clean": true,
  "core_dependencies_valid": true,
  "migration_verified": true,
  "feature_flags_v2_enabled": true,
  "backend_pytest_passed": true,
  "top_level_pytest_passed": true,
  "clean_clone_verified": true,
  "canonical_runtime_identity_verified": true,
  "fresh_app_isolation_verified": true,
  "multi_replica_fencing_passed": true,
  "rollback_rehearsal_passed": true,
  "artifact_integrity_verified": true
}
```

Nếu backend đã xanh nhưng distributed gates chưa chạy:

```text
CORE_CANONICAL_BACKEND_ADOPTION_VERIFIED_READY_FOR_STAGING
```

Nếu fencing xanh nhưng rollback chưa xanh:

```text
CORE_CANONICAL_STAGING_SAFETY_VERIFIED_ROLLBACK_PENDING
```

Nếu một gate bắt buộc fail:

```text
CORE_CANONICAL_FULL_ADOPTION_NOT_VERIFIED
```

Trong `final_verdict.json`, liệt kê rõ từng gate, evidence path, execution SHA và lý do blocker. Không được dùng câu “unrelated to core canonicalization” để bỏ qua backend runtime failure.

---

# 10. Commit, push và draft PR

Sau khi hoàn tất:

1. Xác minh worktree.
2. Commit các artifact cuối.
3. Push branch.
4. Mở hoặc cập nhật draft PR.
5. Không merge.
6. Không mark ready.
7. Không xóa stash có trước chương trình.
8. PR body phải có:

   * starting branch/SHA;
   * final branch/SHA;
   * execution SHA;
   * root causes;
   * code changes;
   * test totals;
   * fencing result;
   * rollback result;
   * artifact paths;
   * final verdict;
   * unresolved blockers.

Commit cuối:

```text
docs(core): publish Phase 14 full-adoption verification
```

---

# 11. Báo cáo cuối bắt buộc

Xuất báo cáo theo mẫu:

```text
FINAL VERDICT:
REPOSITORY:
STARTING BRANCH:
STARTING SHA:
FINAL BRANCH:
FINAL SHA:
EXECUTION SHA:
REMOTE SHA == LOCAL:
WORKTREE CLEAN:
STASH PRESERVED:
DRAFT PR:

ROOT TESTS:
BACKEND TESTS:
CLEAN-CLONE TESTS:
SKIPPED:
XFAILED:

BACKEND WIRING ROOT CAUSES:
COMPOSITION ROOT STATUS:
CANONICAL RUNTIME IDENTITY:
APP ISOLATION:

MULTI-REPLICA ENVIRONMENT:
REPLICAS:
DATABASE:
FENCING RESULT:
STALE WRITES ACCEPTED:
DUPLICATE TERMINAL TRANSITIONS:
SPLIT BRAIN:
RECOVERY CONVERGENCE:

ROLLBACK RESULT:
DATA LOSS:
SCHEMA COMPATIBILITY:
FORWARD DEPLOY RESULT:

SECURITY:
DUPLICATE MODELS:
FORBIDDEN IMPORTS:
EVENT TAXONOMY:
MIGRATION:
FEATURE FLAGS:

COMMITS CREATED:
FILES CHANGED:
ARTIFACT ROOT:
ARTIFACT MANIFEST SHA-256:

REMAINING BLOCKERS:
NEXT REQUIRED ACTION:
```

Bắt đầu bằng baseline verification. Sau đó thực hiện tuần tự Phase 14A → 14F. Không dừng sau khi chỉ phân tích failure; sửa, kiểm thử, tạo evidence, commit và push toàn bộ phần có thể thực hiện trong môi trường hiện tại.
