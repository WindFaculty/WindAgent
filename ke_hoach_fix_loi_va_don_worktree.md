# KẾ HOẠCH FIX LỖI VÀ DỌN WORKTREE

## 1. Mục tiêu

Đưa nhánh `fix/architecture-v2-runtime-cutover` từ trạng thái audit chưa đạt về trạng thái có thể phát hành:

1. Full Python regression không còn failure hoặc error.
2. Architecture, package isolation và two-process E2E đều PASS.
3. Web và Desktop đều test/type-check/build thành công.
4. Chỉ giữ một bản canonical cho mỗi artifact.
5. Loại bỏ script/probe và output tạm sau khi đã lưu bằng chứng cần thiết.
6. Worktree sạch, lịch sử commit tách theo đúng workstream.
7. Chỉ publish sau khi clean-clone verification PASS và người dùng cho phép push.

Final gate:

```text
ARCHITECTURE_V2_RUNTIME_CUTOVER_COMPLETE
```

## 2. Baseline hiện tại

```text
Branch:    fix/architecture-v2-runtime-cutover
Local SHA: 628385eae59e311670c08d5e08904b34d23749ad
Remote:    chưa có refs/heads/fix/architecture-v2-runtime-cutover
```

### Test baseline

| Gate | Kết quả |
|---|---:|
| Focused runtime Phase 1–11 | 51 passed |
| Full pytest | 58 failed / 667 passed / 2 skipped |
| Architecture checkers | 4/4 PASS |
| API package isolation | PASS |
| Worker package isolation | PASS |
| Two-process E2E | PASS |
| Phase 12 CLI doctor | 4 failed / 4 passed |
| Web test | Không chạy được vì thiếu `vitest` |
| Web build | PASS |
| Desktop test | 4 failed / 85 passed |
| Desktop type-check/build | PASS |

### Phân bổ 58 Python failures

| Workstream | Số failure |
|---|---:|
| Migration Phase 9 | 21 |
| Architecture/test-policy drift | 16 |
| CLI, Health và API readiness | 15 |
| Legacy integration endpoints | 6 |
| **Tổng** | **58** |

## 3. Nguyên tắc bảo vệ dữ liệu

1. Không dùng `git reset --hard`.
2. Không dùng `git clean -fd` hoặc xóa theo glob.
3. Không restore một file dirty trước khi so sánh worktree hash với index hash.
4. Trước khi xóa file untracked phải có inventory, SHA-256 và quyết định giữ/xóa rõ ràng.
5. Không sửa test chỉ để hợp thức hóa implementation sai.
6. Test baseline cũ đang khẳng định một defect phải tồn tại phải được thay bằng positive regression test, không được xóa im lặng.
7. Mỗi workstream có commit riêng và gate riêng.
8. Không push khi full gate chưa xanh hoặc worktree chưa sạch.

## 4. Phân loại worktree hiện tại

### 4.1 Stat-only/line-ending noise

Ba file sau có worktree hash bằng index hash; không có thay đổi nội dung:

```text
apps/web/package-lock.json
tests/architecture/test_phase00_runtime_cutover_defects.py
tests/integration/test_phase14_two_process_e2e.py
```

Xử lý:

1. Lưu hash hiện tại.
2. Chạy refresh index có giới hạn đúng ba file.
3. Xác nhận `git diff -- <file>` rỗng.
4. Không checkout/restore nội dung.

Lệnh dự kiến:

```powershell
git add --refresh -- `
  apps/web/package-lock.json `
  tests/architecture/test_phase00_runtime_cutover_defects.py `
  tests/integration/test_phase14_two_process_e2e.py
```

### 4.2 Diff thật cần giữ và hoàn thiện

```text
configs/architecture/scaffold_v2.yaml
observability/windagent_observability/health/contracts.py
scripts/check_architecture_imports.py
tests/architecture/test_phase13_regression.py
tests/unit/cli/test_phase12_cli_doctor.py
```

Hướng xử lý:

- Architecture policy/checker/test phải đi cùng một commit.
- Health contract, CLI composer và CLI tests phải đi cùng workstream Health/CLI.
- Không commit một contract mới trong khi implementation và test vẫn đỏ.

### 4.3 Artifact cần giữ

```text
artifacts/architecture_v2_runtime_cutover/phase_12/
artifacts/architecture_v2_runtime_cutover/phase_13/
artifacts/architecture_v2_runtime_cutover/phase_16/
artifacts/architecture_v2_runtime_cutover/final/
```

Artifact Phase 16 hiện là bằng chứng `NOT_COMPLETE`; sau khi remediation PASS phải tạo một final rerun mới, không sửa lịch sử kết quả đỏ thành xanh.

### 4.4 Output sinh trùng cần hợp nhất

Các cặp đã xác nhận trùng hash:

```text
artifacts/import_graph.json
artifacts/architecture_v2_completion/phase_16/import_graph.json

artifacts/dependency_boundary_report_current.json
artifacts/architecture_v2_runtime_cutover/phase_13/dependency_boundary_report.json
```

Canonical đề xuất:

```text
artifacts/architecture_v2_runtime_cutover/phase_13/import_graph.json
artifacts/architecture_v2_runtime_cutover/phase_13/dependency_boundary_report.json
```

Trước khi xóa bản trùng:

1. So sánh schema và hash.
2. Xác nhận checker đã ghi trực tiếp vào canonical path.
3. Rerun checker.
4. Chỉ xóa từng path exact sau khi được duyệt.

File tracked cũ:

```text
artifacts/architecture_v2_completion/phase_16/import_graph.json
```

phải được restore về HEAD hoặc thay đổi có chủ đích trong commit cleanup; không để một generated diff không có owner.

### 4.5 Probe/debug tạm

```text
check_tables.py
debug_tables.py
probe_claim.py
probe_e2e2.py
probe_health.py
```

Các script này đã được thay thế bởi test tự động. Đề xuất:

- Chuyển logic còn giá trị vào test/harness chính thức.
- Xác nhận không có import/caller.
- Xóa từng file exact ở phase cleanup cuối.
- Bổ sung ignore rule cho thư mục dữ liệu probe nếu hiện chưa có.

### 4.6 Test fake chưa được dùng

```text
tests/fakes/in_memory_lease.py
```

Knowledge graph không tìm thấy consumer. Chọn một trong hai:

1. Dùng fake này trong unit tests và commit cùng test; hoặc
2. Xóa để tránh dead test code.

Không giữ chỉ để architecture checker thấy `_fallback_*` nằm dưới `tests/`.

## 5. Thứ tự remediation

## PHASE R0 — Safety snapshot và worktree manifest

### Công việc

1. Ghi:
   - branch/SHA;
   - `git status --porcelain=v2`;
   - tracked diff;
   - untracked inventory;
   - SHA-256 từng file untracked.
2. Tạo recovery patch cho tracked changes.
3. Đóng gói untracked files cần giữ vào backup riêng.
4. Refresh ba stat-only entries.
5. Tạo `worktree_classification.json` với action:
   - `KEEP_AND_COMMIT`;
   - `GENERATED_CANONICAL`;
   - `DUPLICATE_REMOVE_AFTER_VERIFY`;
   - `TEMP_REMOVE_AFTER_VERIFY`;
   - `NEEDS_OWNER_DECISION`.

### Gate

```text
WORKTREE_SNAPSHOT_RECOVERABLE
```

### Điều kiện PASS

- Có thể khôi phục mọi thay đổi trước cleanup.
- Không còn stat-only false dirty entries.
- Chưa xóa file nào chưa phân loại.

## PHASE R1 — Làm test architecture phản ánh kiến trúc hiện tại

### Phạm vi

Giải quyết 16 failures thuộc architecture/test-policy drift.

### Công việc

1. Thay các Phase 0 reproduction tests đang assert defect phải xuất hiện bằng positive regression tests:
   - registry `close()` tồn tại và chạy được;
   - Worker composition import thành công;
   - API không sở hữu publisher;
   - production thiếu outbox trả `DOWN`;
   - architecture checker trả zero trên repository hợp lệ.
2. Giữ baseline reproduction cũ dưới dạng immutable artifact, không để nó chạy trong full suite.
3. Đồng bộ minimal fixture với machine-readable policy:
   - khai báo `legacy_source`; hoặc
   - thêm policy flag rõ ràng và để fixture đọc cùng policy.
4. Sửa scaffold tests:
   - readiness thiếu required dependency phải là `503/DOWN`;
   - test cần xanh phải inject explicit fake bundle;
   - README scaffold mismatch phải được regenerate hoặc policy cập nhật có chủ đích.
5. Sửa Phase 7 composition test để assert publisher chỉ thuộc Worker, không yêu cầu `OutboxEventPublisher` trong API.
6. Thay test startup recovery dựa trên string của legacy backend bằng behavioral test trên Worker recovery.
7. Rà soát ba test boundary cũ:
   - old Core packages;
   - Intelligence forbidden imports;
   - legacy compatibility shim.
   Quyết định theo canonical policy trước khi sửa assertion.

### Test gate

```powershell
python -m pytest -q tests/architecture tests/regression `
  tests/unit/core/test_phase5_canonical_contracts.py `
  tests/unit/intelligence/test_intelligence_system.py `
  tests/unit/migration/test_legacy_cutover.py `
  tests/unit/test_phase7_composition.py
```

Sau đó:

```powershell
python scripts/check_architecture_imports.py
python scripts/check_duplicate_canonical_models.py
python scripts/check_no_legacy_orchestration.py
python scripts/check_event_taxonomy.py
```

### Gate

```text
ARCHITECTURE_TEST_POLICY_CONSISTENT
```

## PHASE R2 — Sửa migration, backup và rollback

### Phạm vi

Giải quyết 21 failures trong:

```text
tests/unit/storage/migrations/test_phase9_migrations.py
```

### Work package R2.1 — Schema checksum

Defect:

```text
TypeError khi sort constraint có name=None
```

Sửa:

- Chuẩn hóa unnamed constraint bằng stable key `(name or "", type)`.
- Không dùng string representation chứa địa chỉ memory.
- Thêm test checksum ổn định qua hai process.

### Work package R2.2 — Migration lock

Defect:

```text
datetime.replace(second=current.second + timeout)
```

Sửa:

```python
expires_at = acquired_at + timedelta(seconds=lock_timeout)
```

Đồng thời:

- ensure lock table trước mọi operation;
- dùng UTC;
- test timeout qua phút/giờ/ngày;
- cleanup expired lock trong transaction.

### Work package R2.3 — Migration registry

Defect:

```text
Registry không discover 001_initial và 002_legacy_data
```

Sửa:

- registration deterministic;
- validate unique revision;
- validate upgrade/downgrade callable;
- fail closed khi thiếu revision.

### Work package R2.4 — Legacy schema và data integrity

Defect:

```text
Migration tests seed vào canonical chat_sessions đang có cột NOT NULL mới
```

Sửa đúng hướng:

- Fixture source phải tạo legacy source table độc lập.
- Target phải là canonical V2 table độc lập.
- Không dùng `BaseORM.metadata.create_all()` để giả lập legacy source.
- Mapping phải đi qua migration adapter.
- Assert row count, ID, timestamp và payload hash.

### Work package R2.5 — Backup/restore

- Backup chỉ được PASS sau checksum verification.
- Restore vào DB mới rồi so schema/data checksum.
- Tampered/missing backup phải fail closed.

### Test gate

```powershell
python -m pytest -q `
  tests/unit/storage/migrations/test_phase7_schema_mapping.py `
  tests/unit/storage/migrations/test_phase8_data_migration.py `
  tests/unit/storage/migrations/test_phase9_migrations.py `
  tests/unit/storage/migrations/test_phase9_rollback_rehearsal.py
```

### Gate

```text
MIGRATION_BACKUP_ROLLBACK_REGRESSION_PASS
```

## PHASE R3 — Hợp nhất API health và CLI doctor

### Phạm vi

Giải quyết 15 failures thuộc CLI, Health và API readiness.

### Công việc

1. Tạo một `HealthDependencyBundleFactory` dùng chung cho API và CLI.
2. `DoctorCommandComposer` nhận:
   - `profile`;
   - dependency bundle;
   - component filter.
3. `doctor()` hỗ trợ:

```text
--json
--profile
--component
```

4. Chuẩn hóa exit code:

```text
0 = UP
1 = DEGRADED
2 = DOWN
3 = invalid invocation/config
```

5. Bắt lỗi argparse trong `main()` và return `3`, không để `SystemExit(2)` thoát ra test.
6. API và CLI phải serialize cùng:
   - status;
   - required;
   - latency;
   - message/details;
   - suggested action.
7. Sửa typed registry health ports để sync/async behavior rõ ràng; không phụ thuộc `MagicMock` tình cờ await được.
8. Development profile không được tạo runtime giả để trả xanh.
9. Secret masking phải chạy trên cả message, details và suggested action.

### Test gate

```powershell
python -m pytest -q `
  tests/unit/observability `
  tests/unit/cli `
  tests/unit/api/test_phase11_api_worker_cli_websocket.py `
  tests/unit/api/test_phase25_api_cutover.py
```

### Gate

```text
API_CLI_HEALTH_DIAGNOSTICS_CONSISTENT
```

## PHASE R4 — Legacy endpoint và compatibility policy

### Phạm vi

Giải quyết 6 integration failures đang nhận HTTP `410`.

### Quyết định bắt buộc

Đối chiếu policy trước khi sửa:

1. Nếu endpoint legacy đã decommission chính thức:
   - giữ `410`;
   - test phải kiểm tra deprecation receipt;
   - thêm E2E cho V2 successor endpoint;
   - tài liệu migration phải chỉ đường thay thế.
2. Nếu compatibility window vẫn còn hiệu lực:
   - khôi phục adapter;
   - không khôi phục legacy process-local state;
   - adapter phải dùng durable V2 services.

Không đổi assertion `200/202` thành `410` nếu chưa có policy/deprecation evidence.

### Test gate

```powershell
python -m pytest -q `
  tests/integration/test_phase5_execute_endpoint.py `
  tests/integration/test_phase6_workflow_control_surface.py
```

### Gate

```text
LEGACY_COMPATIBILITY_POLICY_ENFORCED
```

## PHASE R5 — Frontend regression

### Web

1. Khai báo `vitest` trong `devDependencies`.
2. Regenerate lockfile bằng đúng npm version.
3. Thêm ít nhất:
   - app smoke test;
   - API client error test;
   - health status render test.
4. Không dùng `--passWithNoTests` để tạo false green.

### Desktop

Sửa bốn defect:

1. `lastEventSequence` phải monotonic:

```text
next = max(current, incoming)
```

2. Permission queue deduplicate theo `request_id`.
3. Switch session giữ nguyên messages và drafts của từng session.
4. Recovery hook phải gọi snapshot + cursor event replay; async state update trong test phải được bọc `act`.

### Test gate

```powershell
Push-Location apps/web
npm.cmd ci
npm.cmd test
npm.cmd run build
Pop-Location

Push-Location apps/desktop
npm.cmd ci
npm.cmd run type-check
npm.cmd test
npm.cmd run build
Pop-Location
```

### Gate

```text
FRONTEND_REGRESSION_PASS
```

## PHASE R6 — Hợp nhất artifact và xóa file tạm

### Công việc

1. Regenerate architecture reports vào canonical Phase 13 path.
2. So hash trước khi xóa duplicate top-level/legacy artifact.
3. Chuyển hoặc xóa năm root probe scripts sau khi coverage đã nằm trong tests.
4. Quyết định giữ/xóa `tests/fakes/in_memory_lease.py`.
5. Xóa các scratch directories bằng exact literal path, không dùng wildcard.
6. Cập nhật `.gitignore` cho output thật sự generated.
7. Tạo file hash manifest mới.
8. Xác nhận không có secret/token trong artifact.

### Gate

```text
ARTIFACTS_CANONICAL_AND_WORKTREE_CURATED
```

## PHASE R7 — Full regression và clean-clone

### Local verification

```powershell
python -m pytest -q -p no:cacheprovider
python scripts/check_architecture_imports.py
python scripts/check_duplicate_canonical_models.py
python scripts/check_no_legacy_orchestration.py
python scripts/check_event_taxonomy.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_api_isolation.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_worker_isolation.ps1
python -m pytest -q tests/integration/test_phase14_two_process_e2e.py
```

Package-isolation scripts phải được sửa để kiểm tra `$LASTEXITCODE` sau từng native command. Một lệnh install/import fail phải làm script exit non-zero.

### Clean-clone verification

Chỉ chạy sau khi local gate PASS:

1. Commit toàn bộ workstream.
2. Tạo clean clone/worktree từ đúng commit.
3. Cài dependency từ lockfiles.
4. Chạy toàn bộ Windows jobs.
5. So local SHA với SHA trong clean clone.
6. Lưu execution logs và file hashes.

### Gate

```text
WINDOWS_CLEAN_CLONE_RUNTIME_PASS
```

## PHASE R8 — Commit, clean worktree và publication

### Commit đề xuất

```text
test(architecture): replace defect baselines with positive regressions
fix(architecture): align checker policy fixtures and canonical reports
fix(migrations): repair checksum locking registry and legacy mapping
fix(health): unify api and cli diagnostic contracts
test(cutover): align compatibility and worker recovery coverage
fix(frontend): restore web and desktop regression gates
chore(worktree): remove verified duplicate and diagnostic outputs
docs(audit): publish remediation and final verification receipts
```

Mỗi commit:

- chỉ chứa file của một workstream;
- có focused tests PASS;
- không stage generated output ngoài canonical path.

### Final checks

```powershell
git status --short
git diff --check
git log --oneline --decorate -10
```

Điều kiện:

```text
git status --short => không có output
```

Publication chỉ thực hiện sau khi người dùng xác nhận push:

```powershell
git push -u origin fix/architecture-v2-runtime-cutover
git ls-remote --heads origin refs/heads/fix/architecture-v2-runtime-cutover
```

Local SHA phải bằng remote SHA.

## 6. Definition of Done

Phase remediation chỉ hoàn tất khi:

- [ ] Full pytest có 0 failed, 0 errors.
- [ ] Không có skipped bootstrap test.
- [ ] CLI architecture test không còn skip do entrypoint.
- [ ] Architecture checkers 4/4 PASS.
- [ ] API/Worker isolation PASS và harness fail closed.
- [ ] Migration/backup/rollback/restore/rerun PASS.
- [ ] API và CLI health parity PASS.
- [ ] Two-process E2E PASS không cần ad-hoc repository-wide `PYTHONPATH`.
- [ ] Web test/build PASS.
- [ ] Desktop type-check/test/build PASS.
- [ ] Artifact chỉ tồn tại ở canonical paths.
- [ ] Root không còn probe/debug script tạm.
- [ ] Worktree sạch.
- [ ] Clean-clone Windows gate PASS.
- [ ] Remote SHA bằng local SHA sau khi được phép publish.

Chỉ khi toàn bộ checklist đạt mới được ghi:

```text
FINAL VERDICT: ARCHITECTURE_V2_RUNTIME_CUTOVER_COMPLETE
```
