# KẾ HOẠCH SỬA ARCHITECTURE V2 RUNTIME CUTOVER

## 1. Phạm vi thực hiện

### Repository

```text
Repository: WindFaculty/WindAgent
Starting commit: 5b26ed67e5550b97b86b83a21c836ff96bd049a6
Branch đề xuất: fix/architecture-v2-runtime-cutover
```

Không sửa trực tiếp nhánh hiện tại. Tạo nhánh mới từ đúng starting commit:

```powershell
git switch --detach 5b26ed67e5550b97b86b83a21c836ff96bd049a6
git switch -c fix/architecture-v2-runtime-cutover
```

### Năm nhóm cần hoàn thiện

1. Khôi phục runtime cơ bản và package isolation.
2. Hoàn thiện Worker durable queue, lease, heartbeat và recovery.
3. Sửa transactional outbox và event publication.
4. Viết lại migration dữ liệu và chứng minh rollback.
5. Làm readiness, liveness và diagnostics đáng tin cậy.

### Nguyên tắc bắt buộc

* Không tuyên bố `PASS` khi full gate chưa đạt.
* Không bỏ qua bootstrap, shutdown hoặc process integration tests.
* Không dùng in-memory fallback trong production profile.
* Không để API và Worker chia sẻ process-local state.
* Không giữ placeholder production implementation.
* Không sửa test chỉ để hợp thức hóa implementation sai.
* Mỗi phase phải có commit riêng.
* Mỗi phase phải tạo artifact kiểm chứng.
* Mọi blocker phải được ghi rõ là baseline, implementation defect hoặc environment blocker.

---

# 2. Cấu trúc artifact

Mỗi phase tạo:

```text
artifacts/architecture_v2_runtime_cutover/
├── phase_00/
├── phase_01/
├── phase_02/
├── ...
└── final/
```

Mỗi thư mục phase tối thiểu có:

```text
execution_receipt.json
changed_files.txt
test_results.json
risk_register.md
phase_verdict.md
```

Các phase liên quan process hoặc database phải bổ sung log thực thi đầy đủ.

Verdict hợp lệ:

```text
PASS
BLOCKED
FAILED
INVALID_RUN
```

Không sử dụng:

```text
MOSTLY_PASS
PASS_WITH_KNOWN_ISSUES
TEMPORARY_PASS
```

---

# 3. PHASE 0 — Khóa baseline và tái lập lỗi

## Mục tiêu

Xác nhận chính xác tình trạng tại commit bắt đầu trước khi sửa code.

## Công việc

1. Xác nhận:

   * Current branch.
   * Local SHA.
   * Remote SHA.
   * Worktree status.
   * Untracked files.
   * Existing stashes.

2. Chạy lại:

   * Architecture checker.
   * Duplicate canonical model checker.
   * Full Python test suite.
   * API focused tests.
   * Worker focused tests.
   * Storage và migration tests.
   * Observability tests.
   * Desktop type-check và build.
   * Web type-check và build.

3. Tạo focused reproduction cho các lỗi đã phát hiện:

   * API lifespan truy cập `container.orchestration_container`.
   * API shutdown gọi `PluginRegistry.close()`.
   * API shutdown gọi `SkillRegistry.close()`.
   * Worker không claim được task trong SQL.
   * Outbox repository nhận sai kiểu dependency.
   * Outbox publisher không được start.
   * Migration 002 tự đọc và ghi cùng bảng.
   * Health outbox bị `NOT_REQUIRED`.
   * Architecture checker bỏ sót undeclared dependencies.

4. Không sửa code trong phase này.

## Test bắt buộc

Các reproduction test phải fail tại starting commit.

Ví dụ:

```text
test_api_lifespan_bootstrap_real
test_api_shutdown_real
test_worker_claims_sql_task
test_worker_publishes_pending_outbox
test_api_package_installs_in_isolation
test_worker_package_installs_in_isolation
test_legacy_data_reaches_distinct_v2_table
test_production_health_requires_outbox
```

## Gate

```text
RUNTIME_DEFECT_BASELINE_REPRODUCED
```

## Điều kiện PASS

* Mỗi P0 defect có reproduction test.
* Full test baseline được lưu.
* Không có thay đổi production code.
* Worktree sạch sau khi commit artifact và test reproduction.

## Commit

```text
test(architecture): reproduce runtime cutover defects
```

---

# NHÓM 1 — KHÔI PHỤC RUNTIME CƠ BẢN

# 4. PHASE 1 — Sửa API composition và lifecycle

## Mục tiêu

API phải startup và shutdown thành công bằng composition root thật.

## Công việc

### 4.1 Sửa lifespan

Loại bỏ mọi truy cập tới thuộc tính không tồn tại:

```python
container.orchestration_container
```

`app.state` chỉ được chứa các dependency thực sự do `ApplicationContainer` sở hữu.

Đề xuất:

```python
app.state.container = container
app.state.db = container.db
app.state.task_manager = container.task_manager
app.state.provider_registry = container.provider_registry
app.state.tool_registry = container.tool_registry
app.state.worker_status_query = container.worker_status_query
app.state.event_dispatcher = container.event_dispatcher
```

Không tạo alias state không còn được router hoặc dependency sử dụng.

### 4.2 Chuẩn hóa lifecycle contract

Chọn một trong hai cách:

* Mọi service lifecycle đều implement `AsyncCloseablePort`.
* Composition root chỉ gọi `close()` khi service thực sự có lifecycle.

Không dùng `hasattr()` để che giấu contract sai trong production composition.

Đề xuất Core contract:

```python
class AsyncCloseablePort(Protocol):
    async def close(self) -> None: ...
```

### 4.3 Sửa PluginRegistry và SkillRegistry

Nếu registry sở hữu resource cần cleanup:

```python
async def close(self) -> None:
    await self._loader.close()
```

Nếu registry không sở hữu resource:

```python
async def close(self) -> None:
    return None
```

No-op chỉ được chấp nhận khi được định nghĩa là lifecycle contract chính thức, có test và lý do rõ ràng. Không để method placeholder không có contract.

### 4.4 Context và Memory service

Xác định resource ownership thực tế.

Nếu service chỉ là facade stateless:

* Không đưa vào shutdown list.
* Không cần method `close()`.

Nếu service sở hữu database, client hoặc background task:

* Implement cleanup thật.
* Có idempotent shutdown.

### 4.5 Thứ tự shutdown

Thứ tự đề xuất:

1. Dừng nhận request mới.
2. Dừng background task thuộc API.
3. Flush submission buffer nếu có.
4. Đóng registries có resource.
5. Đóng database cuối cùng.

## Test bắt buộc

* API startup với SQLite tạm.
* API shutdown không exception.
* Startup hai lần không tạo duplicate resource.
* Shutdown hai lần không exception.
* Startup failure phải cleanup resource đã tạo.
* Lifespan không import hoặc truy cập Worker implementation.
* Không còn skipped bootstrap test.

## Gate

```text
API_LIFECYCLE_OPERATIONAL
```

## Commit

```text
fix(api): repair composition lifecycle and shutdown
```

---

# 5. PHASE 2 — Sửa package metadata và chứng minh package isolation

## Mục tiêu

API và Worker phải cài đặt, import và khởi động độc lập trong môi trường sạch.

## Công việc

### 5.1 Cập nhật API dependencies

Đối chiếu toàn bộ import của:

```text
apps/api/windagent_api/
```

Bổ sung các workspace dependency thực sự được sử dụng, dự kiến gồm:

```text
windagent-workflows
windagent-verification
windagent-context
windagent-memory
windagent-plugins
windagent-skills
```

Loại bỏ dependency không còn sử dụng.

### 5.2 Cập nhật Worker dependencies

Bổ sung dependency tương ứng với Worker composition:

```text
windagent-providers
windagent-tools
windagent-intelligence
windagent-context
windagent-memory
windagent-workflows
windagent-verification
```

### 5.3 Đồng bộ architecture policy

`configs/architecture/scaffold_v2.yaml` phải khớp với dependency thực tế.

Không được chỉ sửa checker để bỏ qua lỗi.

### 5.4 Tạo package isolation harness

Tạo script:

```text
scripts/test_api_isolation.ps1
scripts/test_worker_isolation.ps1
```

Mỗi script phải:

1. Tạo virtual environment mới.
2. Cài đúng package mục tiêu.
3. Không thêm toàn repository vào `PYTHONPATH`.
4. Import package.
5. Startup process.
6. Chạy smoke command.
7. Shutdown.
8. Xóa environment.

### 5.5 Chặn undeclared dependency

Architecture checker phải fail nếu source import một workspace package không nằm trong `pyproject.toml`.

## Test bắt buộc

### API isolation

* Import `windagent_api`.
* Startup API.
* `/health/live`.
* Shutdown.
* Không cài `windagent-worker`.

### Worker isolation

* Import `windagent_worker`.
* Bootstrap WorkerContainer.
* Start và stop Worker.
* Không cài `windagent-api`.

### Negative fixtures

* API import package chưa khai báo.
* Worker import package chưa khai báo.
* Package metadata thiếu `[tool.uv.sources]`.
* Namespace tồn tại trong `PYTHONPATH` nhưng không nằm trong package dependency.

## Gate

```text
PACKAGE_ISOLATION_AND_METADATA_VALID
```

## Commit

```text
fix(packaging): declare complete api and worker dependencies
```

---

# NHÓM 2 — WORKER DURABLE QUEUE, LEASE VÀ RECOVERY

# 6. PHASE 3 — Xây dựng durable task submission và atomic claim

## Mục tiêu

Task do API submit vào SQL phải được Worker process độc lập claim và thực thi.

## Công việc

### 6.1 Định nghĩa queue contract trong Core

```text
core/windagent_core/contracts/workers/
├── submission.py
├── queue.py
├── leases.py
└── heartbeat.py
```

Các port tối thiểu:

```python
class WorkSubmissionPort(Protocol):
    async def submit(self, request: WorkSubmission) -> TaskId: ...

class DurableTaskQueuePort(Protocol):
    async def claim_next(
        self,
        worker_id: WorkerId,
        lease_ttl_seconds: int,
    ) -> ClaimedTask | None: ...

class TaskLeasePort(Protocol):
    async def renew(...): ...
    async def release(...): ...
    async def fail(...): ...
```

### 6.2 Tạo SQL adapter

SQL adapter phải thực hiện claim atomically.

Yêu cầu:

* Chỉ claim task ở trạng thái hợp lệ.
* Kiểm tra lease hết hạn.
* Tăng `lease_generation`.
* Sinh fencing token mới.
* Ghi worker ID.
* Ghi lease expiry.
* Commit trong một transaction.
* Hai Worker không thể claim cùng một task.

Không dùng:

```python
_fallback_pending
_fallback_leases
```

trong production path.

### 6.3 Tách in-memory adapter

In-memory queue chỉ được đặt trong:

```text
tests/fakes/
```

hoặc package adapter test rõ ràng.

Không tự fallback sang memory khi SQL dependency bị thiếu.

Production bootstrap thiếu durable queue phải fail-closed.

### 6.4 Sửa ProductionWorker

`poll_and_execute_tick()` phải dùng async queue port:

```python
claimed_task = await self.task_queue.claim_next(...)
```

Không gọi synchronous test-compatible method.

### 6.5 API task submission

API phải submit task qua `WorkSubmissionPort`.

Task submission và outbox event `TaskSubmitted` phải nằm trong cùng transaction.

## Test bắt buộc

* API submit task, SQL có một queue record.
* Worker claim task đó.
* Hai Worker cạnh tranh chỉ một Worker thắng.
* Task không bị claim lại trước lease expiry.
* Task được reclaim sau lease expiry.
* Fencing token thay đổi sau reclaim.
* Stale Worker không được complete task.
* Transaction rollback không tạo orphan queue record.
* Không có production reference tới `_fallback_pending`.

## Gate

```text
DURABLE_TASK_QUEUE_OPERATIONAL
```

## Commit

```text
feat(worker): implement atomic durable task claiming
```

---

# 7. PHASE 4 — Worker registration, heartbeat, lease renewal và recovery

## Mục tiêu

Worker phải có identity bền vững, heartbeat thật và recovery path xác định.

## Công việc

### 7.1 Worker registration

Khi Worker startup:

* Sinh `runtime_run_id`.
* Register worker vào SQL.
* Ghi runtime type.
* Ghi process ID.
* Ghi version.
* Ghi capability summary.
* Ghi started timestamp.

### 7.2 Heartbeat loop

Tạo background task riêng:

```python
async def heartbeat_loop()
```

Heartbeat phải cập nhật:

* `last_heartbeat_at`.
* Worker health.
* Active leases.
* Current task ID.
* Runtime metadata.

Heartbeat interval phải nhỏ hơn stale threshold.

### 7.3 Lease renewal loop

Task dài phải renew lease định kỳ.

Nếu renew thất bại:

* Gửi cancellation tới runtime.
* Không commit terminal result.
* Không phát `TaskCompleted`.
* Ghi fencing violation hoặc lease lost event.

### 7.4 Graceful shutdown

Worker shutdown phải:

1. Ngừng claim task mới.
2. Chờ current task tới safe checkpoint hoặc timeout.
3. Dừng lease renewal.
4. Release hoặc abandon lease theo policy.
5. Ghi final heartbeat.
6. Dừng outbox publisher.
7. Đóng execution runtime.
8. Đóng database.

### 7.5 Startup recovery

Khi Worker startup:

* Reclaim expired leases.
* Phân loại task:

  * Retry-safe.
  * Requires manual review.
  * Terminal.
  * Orphaned.
* Không chạy lại destructive tool nếu chưa có idempotency evidence.
* Không double-complete task.

## Test bắt buộc

* Worker registration xuất hiện trong SQL.
* Heartbeat timestamp tăng theo thời gian.
* Readiness phát hiện stale worker.
* Task dài renew lease nhiều lần.
* Lease lost làm kết quả bị reject.
* Worker crash rồi Worker mới reclaim task.
* Restart API không ảnh hưởng Worker.
* Restart Worker không làm API crash.
* Hai Worker không xử lý cùng lease generation.
* Cancellation propagation khi lease mất.

## Gate

```text
WORKER_HEARTBEAT_LEASE_AND_RECOVERY_PROVEN
```

## Commit

```text
feat(worker): add durable heartbeat lease renewal and recovery
```

---

# NHÓM 3 — TRANSACTIONAL OUTBOX

# 8. PHASE 5 — Sửa OutboxRepository contract và transaction ownership

## Mục tiêu

Outbox record phải được ghi và cập nhật bằng transaction đúng kiểu, không truyền session factory vào repository yêu cầu session.

## Công việc

### 8.1 Chọn repository lifecycle rõ ràng

Khuyến nghị:

```python
class SqlOutboxRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
```

Repository được tạo bên trong Unit of Work:

```python
async with uow:
    repo = SqlOutboxRepository(uow.session)
```

Đối với publisher polling, tạo repository factory:

```python
class SqlOutboxRepositoryFactory:
    async def create(self) -> AsyncIterator[SqlOutboxRepository]:
        async with session_factory() as session:
            yield SqlOutboxRepository(session)
```

Không dùng một session lâu dài cho polling loop.

### 8.2 Transaction handling

Các method thay đổi trạng thái phải commit hoặc chạy trong UoW rõ ràng:

* `mark_published`.
* `mark_failed`.
* `mark_dead_letter`.
* Claim batch.

Không để update nằm trong session rồi đóng mà không commit.

### 8.3 Claim semantics

Publisher phải claim record atomically:

```text
pending → publishing
```

Record cần thêm nếu chưa có:

```text
claimed_by
claim_token
claim_expires_at
```

Sau crash:

```text
publishing + expired claim → pending
```

### 8.4 Idempotency

* Unique index cho `deduplication_key`.
* Dispatcher consumer phải xử lý duplicate an toàn.
* Mark published chỉ hợp lệ với đúng claim token.
* Late publisher không được overwrite trạng thái mới hơn.

### 8.5 Ordering

Ordering cần theo:

```text
aggregate_id + sequence_number
```

Không chỉ sort toàn cục theo `sequence_number`.

## Test bắt buộc

* Repository nhận đúng `AsyncSession`.
* Update được commit.
* Rollback giữ record ở trạng thái trước đó.
* Concurrent publishers không claim cùng record.
* Expired claim được recover.
* Duplicate deduplication key bị chặn.
* Ordering đúng cho cùng aggregate.
* Hai aggregate có thể publish song song.

## Gate

```text
OUTBOX_TRANSACTION_AND_CLAIM_MODEL_VALID
```

## Commit

```text
fix(outbox): enforce transactional repository and claim ownership
```

---

# 9. PHASE 6 — Khởi động publisher, retry, replay và shutdown drain

## Mục tiêu

Worker thực sự chạy outbox publisher trong runtime.

## Công việc

### 9.1 Worker owns publisher

Chỉ Worker composition được compose publisher loop.

API chỉ được compose:

```text
OutboxSubmissionPort
```

hoặc Unit of Work có khả năng ghi outbox.

Xóa publisher khỏi API composition root.

### 9.2 Start và stop publisher

Worker bootstrap:

```python
await outbox_publisher.start()
```

Worker shutdown:

```python
await outbox_publisher.stop(drain=True)
```

Publisher start phải hoàn thành trước khi Worker báo ready.

### 9.3 Retry policy

Retry phải có:

* Exponential backoff.
* Jitter.
* Maximum attempts.
* Retryable error classification.
* Non-retryable error classification.
* Dead-letter transition.

### 9.4 Dead-letter replay

Tạo service và CLI command:

```text
windagent outbox list-dead-letter
windagent outbox replay <event-id>
```

Replay phải:

* Giữ original event ID.
* Tạo replay attempt ID.
* Ghi audit trail.
* Không reset attempt history âm thầm.

### 9.5 Publisher heartbeat

Publisher phải ghi:

* Last poll timestamp.
* Last successful publication.
* Current state.
* Pending count.
* Failed count.
* Dead-letter count.

Health checker đọc heartbeat này, không chỉ kiểm tra object tồn tại.

## Test bắt buộc

* Worker startup làm publisher running.
* Pending event được publish.
* Publish failure giữ event để retry.
* Restart Worker tiếp tục publish event cũ.
* Crash giữa dispatch và mark-published không mất event.
* Duplicate dispatch được consumer deduplicate.
* Poison event chuyển dead-letter.
* Replay dead-letter thành công.
* Shutdown drain publish hết batch đang claim.
* API process không chạy publisher.

## Gate

```text
DURABLE_EVENT_PUBLICATION_OPERATIONAL
```

## Commit

```text
feat(outbox): run publisher with retry replay and shutdown drain
```

---

# NHÓM 4 — DATA MIGRATION VÀ ROLLBACK

# 10. PHASE 7 — Kiểm kê schema và thiết kế lại source-to-target mapping

## Mục tiêu

Xây dựng migration dựa trên schema thực tế, không self-copy và không giả định bảng nguồn trùng bảng đích.

## Công việc

### 10.1 Chụp schema thực tế

Xuất:

```text
legacy_schema_snapshot.json
canonical_schema_snapshot.json
table_inventory.csv
foreign_key_inventory.csv
index_inventory.csv
```

### 10.2 Phân loại bảng

Mỗi bảng phải thuộc một nhóm:

```text
legacy_only
canonical_only
shared_name_compatible
shared_name_incompatible
deprecated
unknown
```

### 10.3 Giải quyết bảng trùng tên

Với `chat_sessions` và `execution_events`, không được dùng:

```sql
INSERT INTO table SELECT FROM table
```

Chọn một chiến lược:

* Rename legacy table trước migration.
* Copy sang staging table.
* Dùng attached legacy database.
* Dùng explicit schema namespace nếu database hỗ trợ.

Ví dụ SQLite:

```text
chat_sessions
→ legacy_chat_sessions_snapshot

execution_events
→ legacy_execution_events_snapshot
```

Sau đó mới tạo canonical table.

### 10.4 Source-to-target map

Mỗi mapping phải mô tả:

```text
source_table
source_column
target_table
target_column
transformation
null_policy
enum_mapping
default_policy
validation_rule
rollback_strategy
```

### 10.5 Preflight validator

Migration phải dừng trước khi thay đổi dữ liệu nếu:

* Thiếu source column.
* Có enum không ánh xạ được.
* Có orphan foreign key.
* Có duplicate ID.
* Có invalid JSON.
* Có timestamp không parse được.
* Có target conflict chưa có policy.

Verdict:

```text
BLOCKED_DATA_MIGRATION
```

## Test bắt buộc

* Self-copy SQL bị static checker từ chối.
* Shared-name table được rename hoặc stage đúng.
* Missing source column làm preflight fail.
* Unknown enum làm preflight fail.
* Orphan relation làm preflight fail.
* Empty legacy database vẫn migrate hợp lệ.
* Existing canonical database không bị overwrite.

## Gate

```text
DATA_MIGRATION_MAPPING_VALIDATED
```

## Commit

```text
refactor(migration): define explicit legacy to canonical mapping
```

---

# 11. PHASE 8 — Implement migration thật và integrity verification

## Mục tiêu

Dữ liệu phải chuyển từ legacy source sang canonical target và được kiểm tra độc lập.

## Công việc

### 11.1 Migration transaction

Mỗi migration phải:

1. Acquire migration lock.
2. Chụp backup.
3. Chạy preflight.
4. Bắt đầu transaction.
5. Tạo canonical schema.
6. Copy và transform dữ liệu.
7. Verify.
8. Ghi migration history.
9. Commit.

Nếu verify thất bại:

```text
rollback transaction
mark migration failed
do not report completed
```

### 11.2 Integrity verification

Kiểm tra tối thiểu:

* Source row count → target row count.
* Primary key preservation.
* Foreign key preservation.
* Timestamp preservation.
* Enum mapping.
* JSON canonical hash.
* Required field completeness.
* Duplicate detection.
* Aggregate sequence continuity.
* Artifact URI preservation.
* Provider secret non-exposure.

Mapping count phải explicit:

```python
{
    "parent_tasks": "v2_tasks",
    "workflows": "v2_workflow_runs",
    "workflow_steps": "v2_workflow_steps",
    "task_artifacts": "v2_artifacts",
}
```

### 11.3 Timestamp

Không ghi literal:

```text
NOW()
```

vào parameter.

Phải dùng timestamp UTC thực hoặc database function đúng dialect.

### 11.4 Migration history

Ghi:

* Revision.
* Checksum migration code.
* Source schema checksum.
* Target schema checksum.
* Source data checksum.
* Target data checksum.
* Started time.
* Completed time.
* Status.
* Backup ID.

## Test bắt buộc

* Dữ liệu legacy nằm trong target table khác biệt.
* Source và target count khớp.
* Mỗi ID kiểm tra được ở target.
* Relationship được giữ.
* Invalid row làm toàn transaction rollback.
* Migration chạy lần hai là idempotent hoặc bị chặn rõ ràng.
* Migration không báo completed khi integrity fail.
* Test dùng database copy gần giống production.

## Gate

```text
LEGACY_DATA_MIGRATION_PROVEN
```

## Commit

```text
feat(migration): implement verified legacy data transfer
```

---

# 12. PHASE 9 — Rollback và backup restoration rehearsal

## Mục tiêu

Chứng minh có thể quay lại trạng thái trước migration.

## Công việc

### 12.1 Rollback definition

Không coi việc đổi `migration_history.status` là rollback.

Rollback hợp lệ phải đạt một trong hai:

* Downgrade phục hồi schema và data.
* Restore verified backup.

### 12.2 Backup verification

Backup phải chứa:

* Database file hoặc dump.
* Schema checksum.
* Row count per table.
* File checksum.
* Backup timestamp.
* Migration revision.
* Application version.

### 12.3 Restore procedure

1. Stop API.
2. Stop Worker.
3. Acquire restore lock.
4. Verify backup checksum.
5. Restore database.
6. Verify schema checksum.
7. Verify row counts.
8. Start API.
9. Start Worker.
10. Run smoke test.

### 12.4 Rollback rehearsal

Chạy sequence thật:

```text
legacy database
→ backup
→ migrate
→ validate canonical
→ rollback/restore
→ validate legacy state
→ migrate lần hai
→ validate canonical lần hai
```

### 12.5 Failure injection

* Backup bị thiếu.
* Backup checksum sai.
* Disk full trong migration.
* Process crash giữa migration.
* Restore bị gián đoạn.
* Schema drift trước rollback.

## Test bắt buộc

* Restore trả row count về baseline.
* Restore trả schema checksum về baseline.
* Không còn canonical partial state sau restore.
* Migration có thể chạy lại sau restore.
* Corrupt backup bị từ chối.
* API và Worker không chạy trong lúc restore.

## Gate

```text
MIGRATION_ROLLBACK_AND_RESTORE_PROVEN
```

## Commit

```text
test(migration): prove backup restoration and rollback
```

---

# NHÓM 5 — HEALTH VÀ DIAGNOSTICS

# 13. PHASE 10 — Viết lại health dependency wiring

## Mục tiêu

HealthChecker phải nhận đủ dependency thật từ composition root.

## Công việc

### 13.1 Tạo HealthDependencyBundle

Thay vì tự lấy nhiều thuộc tính từ `app.state`, tạo bundle typed:

```python
@dataclass(frozen=True)
class HealthDependencyBundle:
    database: DatabaseHealthPort
    schema: SchemaHealthPort
    outbox: OutboxHealthPort
    queue: QueueHealthPort
    worker: WorkerHealthPort
    providers: RegistryHealthPort
    tools: RegistryHealthPort
    plugins: RegistryHealthPort
    skills: RegistryHealthPort
    workflows: RegistryHealthPort
    events: EventHealthPort
    configuration: ConfigurationHealthPort
    filesystem: FilesystemHealthPort
```

ApplicationContainer tạo bundle sau bootstrap.

### 13.2 Không mutate private field

Xóa:

```python
checker._profile = profile
```

Profile phải truyền qua constructor hoặc public method.

### 13.3 Production fail-closed

Trong production, dependency bắt buộc bị thiếu phải trả:

```text
DOWN
```

Không trả:

```text
NOT_REQUIRED
```

cho:

* Database.
* Schema.
* Durable queue.
* Outbox.
* Worker.
* Required registries.
* Event pipeline.
* Configuration.

### 13.4 Test profile

In-memory adapter chỉ được chấp nhận khi:

* Được inject rõ ràng.
* Profile là test.
* Response ghi rõ adapter type.
* Không tự fallback.

## Test bắt buộc

* Production thiếu outbox → DOWN.
* Production thiếu worker query → DOWN.
* Production thiếu queue → DOWN.
* Test profile với fake explicit → DEGRADED hoặc UP theo policy.
* HealthChecker không truy cập private state.
* API và CLI sử dụng cùng bundle factory.

## Gate

```text
HEALTH_DEPENDENCY_WIRING_VALID
```

## Commit

```text
refactor(health): inject typed runtime health dependencies
```

---

# 14. PHASE 11 — Implement real readiness checks

## Mục tiêu

Mỗi readiness check phải xác minh một capability runtime thực tế.

## Công việc

### Database

* `SELECT 1`.
* Timeout.
* Connection pool status nếu có.

### Schema

* Current revision phải bằng expected head.
* Detect dirty migration.
* Detect schema checksum drift.

Không chỉ kiểm tra `MAX(revision)` tồn tại.

### Queue

* Thực hiện repository-level read.
* Có thể chạy transaction no-op.
* Trả queue depth và oldest task age.

Không hardcode tên bảng trong HealthChecker nếu queue adapter đã có port.

### Worker

* Active heartbeat count.
* Latest heartbeat age.
* Worker version.
* Active leases.
* Worker health state.

### Outbox

* Publisher heartbeat.
* Publisher running state.
* Pending event count.
* Oldest pending age.
* Failed count.
* Dead-letter count.

Object publisher tồn tại không đủ để trả `UP`.

### Event dispatcher

Cần xác minh:

* Dispatcher started.
* Required handlers registered.
* Dispatch loop active.
* Last successful dispatch.
* Không có fatal background task failure.

### Registries

Registry `UP` khi:

* Load hoàn tất.
* Required built-in entries có mặt.
* Không có initialization error.

Số lượng bằng zero không mặc nhiên là `UP` nếu production yêu cầu built-in capability.

### Configuration

Validate:

* Environment enum.
* Database URL.
* Required filesystem paths.
* Secret provider.
* Encryption key availability.
* Allowed origins.
* Runtime timeouts.
* Worker lease configuration.
* Outbox retry configuration.
* Production debug disabled.

### Filesystem

Dùng absolute paths từ resolved config, không phụ thuộc current working directory.

## Status policy

```text
UP:
  Tất cả required capability hoạt động.

DEGRADED:
  Capability optional lỗi hoặc backlog vượt warning threshold.

DOWN:
  Required capability thiếu, stale hoặc không hoạt động.

NOT_REQUIRED:
  Chỉ dùng cho capability thật sự không cần trong profile hiện tại.
```

## Test bắt buộc

* Publisher object tồn tại nhưng task chưa start → DOWN.
* Worker heartbeat stale → DOWN.
* Migration revision cũ → DOWN.
* Schema drift → DOWN.
* Invalid environment → DOWN.
* Missing production secret → DOWN.
* Queue backlog warning → DEGRADED.
* Dead-letter vượt threshold → DEGRADED hoặc DOWN theo policy.
* Required handler thiếu → DOWN.
* Health check timeout không treo endpoint.

## Gate

```text
RUNTIME_READINESS_TRUSTWORTHY
```

## Commit

```text
feat(health): implement capability based readiness checks
```

---

# 15. PHASE 12 — CLI doctor và operational diagnostics

## Mục tiêu

`windagent doctor` phải sử dụng cùng health infrastructure với API và cung cấp thông tin sửa lỗi có thể hành động.

## Công việc

CLI doctor phải hiển thị:

```text
Component
Status
Required
Latency
Message
Details
Suggested action
```

Các mode:

```powershell
windagent doctor
windagent doctor --json
windagent doctor --profile production
windagent doctor --component worker
windagent doctor --component outbox
```

Exit code:

```text
0 = UP
1 = DEGRADED
2 = DOWN
3 = invalid invocation/config
```

Không khởi tạo một runtime giả chỉ để doctor trả xanh.

## Test bắt buộc

* API và CLI cho cùng status trên cùng dependency bundle.
* JSON output ổn định.
* Exit code đúng.
* Không lộ secret.
* Error message có remediation.
* Doctor chạy được khi API process không chạy.
* Doctor phát hiện Worker stale.
* Doctor phát hiện outbox publisher stopped.

## Gate

```text
OPERATIONAL_DIAGNOSTICS_CONSISTENT
```

## Commit

```text
feat(cli): align doctor with runtime health providers
```

---

# 16. PHASE 13 — Đồng bộ architecture checker và regression policy

## Mục tiêu

Architecture checker phải phát hiện đúng các lỗi mà runtime và regression tests đang phát hiện.

## Công việc

### 16.1 Một nguồn policy duy nhất

Mọi test architecture phải đọc cùng một machine-readable policy.

Không duy trì:

* Một policy trong YAML.
* Một policy khác hardcode trong pytest.

### 16.2 Namespace resolution

Checker phải map chính xác:

```text
windagent_core → core
windagent_orchestration → orchestration
windagent_intelligence → intelligence
...
```

### 16.3 Kiểm tra đầy đủ

* Forbidden imports.
* Undeclared dependencies.
* Cross-app imports.
* Core framework imports.
* Circular dependency.
* Public API leakage.
* Duplicate canonical model.
* Workspace membership.
* Package source declaration.
* Legacy backend imports.
* Production references tới test fallback.

### 16.4 Sửa intelligence boundary

Giải quyết 43 import từ Intelligence sang Orchestration bằng một trong hai hướng:

* Chuyển shared types về Core contracts.
* Tạo orchestration port trong Core.
* Di chuyển implementation về đúng application service.

Không whitelist toàn bộ edge nếu nó trái dependency direction đã khóa.

## Test bắt buộc

* Mọi negative fixture trả non-zero.
* Regression test và checker cùng báo một violation set.
* API undeclared dependency bị bắt.
* Worker undeclared dependency bị bắt.
* Intelligence forbidden import bị bắt.
* Clean repository trả zero violations.

## Gate

```text
ARCHITECTURE_POLICY_AND_RUNTIME_ALIGNED
```

## Commit

```text
fix(architecture): unify dependency policy and regression checks
```

---

# 17. PHASE 14 — API và Worker two-process integration

## Mục tiêu

Chứng minh toàn bộ đường chạy chính hoạt động qua hai process độc lập.

## Kịch bản E2E bắt buộc

1. Tạo database trống.
2. Chạy migrations.
3. Start API process.
4. Start Worker process.
5. Chờ API readiness `UP`.
6. Chờ Worker heartbeat active.
7. Tạo session.
8. Submit task.
9. Xác nhận task được ghi vào durable queue.
10. Worker claim task.
11. Worker renew lease.
12. Execution runtime xử lý mock-safe task.
13. Worker commit terminal state.
14. Outbox publisher phát event.
15. API query thấy result.
16. Stop API.
17. Worker tiếp tục tồn tại.
18. Start lại API.
19. Result vẫn query được.
20. Stop Worker.
21. API readiness phản ánh Worker down.
22. Graceful shutdown.

## Failure scenarios

* API crash sau task submission.
* Worker crash sau claim.
* Worker crash sau execution trước completion commit.
* Publisher crash sau dispatch trước mark-published.
* Database lock tạm thời.
* Stale fencing token.
* Duplicate Worker startup.
* Duplicate event.
* Corrupt event payload.

## Assertions

* Không mất task.
* Không double-complete.
* Không hai Worker cùng xử lý task.
* Không mất terminal result.
* Không phát event sai sequence.
* API restart không làm mất task.
* Worker restart có recovery.
* Health phản ánh đúng trạng thái.

## Gate

```text
API_WORKER_DURABLE_RUNTIME_PROVEN
```

## Commit

```text
test(e2e): prove independent api worker durable runtime
```

---

# 18. PHASE 15 — Full regression và clean-clone verification

## Mục tiêu

Xác minh toàn repository trong môi trường sạch.

## Windows clean-clone workflow

### Job 1 — Architecture

```text
architecture checker
dependency graph
cycle checker
duplicate model checker
workspace dependency checker
legacy import checker
```

### Job 2 — Package isolation

```text
API isolated install
Worker isolated install
CLI isolated install
Core isolated install
Storage isolated install
Providers isolated install
```

### Job 3 — Unit tests

Chạy theo package.

### Job 4 — Integration tests

```text
API + SQLite
Worker + SQLite
API + Worker
Queue
Lease
Heartbeat
Outbox
Migration
Rollback
Health
```

### Job 5 — Frontend

```text
web type-check
web unit tests
web build
desktop frontend type-check
desktop frontend tests
desktop build
```

### Job 6 — E2E

Chạy kịch bản Phase 14 từ clean clone.

## Gate

```text
WINDOWS_CLEAN_CLONE_RUNTIME_PASS
```

## Commit

```text
ci(windows): verify architecture v2 runtime cutover
```

---

# 19. PHASE 16 — Final audit

## Acceptance checklist

### Runtime cơ bản

* [ ] API startup pass.
* [ ] API shutdown pass.
* [ ] Không còn invalid app state wiring.
* [ ] Không còn skipped bootstrap test.
* [ ] API package isolation pass.
* [ ] Worker package isolation pass.

### Worker

* [ ] API submit task vào SQL.
* [ ] Worker claim từ SQL.
* [ ] Atomic lease hoạt động.
* [ ] Fencing token hoạt động.
* [ ] Heartbeat hoạt động.
* [ ] Recovery hoạt động.
* [ ] Không còn production in-memory fallback.

### Outbox

* [x] Repository session ownership đúng.
* [x] Publisher được start.
* [x] Publisher được stop và drain.
* [x] Retry hoạt động.
* [x] Dead-letter hoạt động.
* [x] Replay hoạt động.
* [x] Crash recovery hoạt động.
* [x] Ordering và idempotency hoạt động.

### Migration

* [x] Không còn self-copy SQL.
* [x] Source và target độc lập.
* [x] Integrity verification fail-closed.
* [x] Backup verified.
* [x] Rollback rehearsal pass.
* [x] Restore rehearsal pass.
* [x] Migration rerun pass.

### Health

* [x] Production thiếu required dependency trả DOWN.
* [x] Worker heartbeat thật.
* [x] Publisher heartbeat thật.
* [ ] Schema head được kiểm tra.
* [ ] Config validation thật.
* [ ] Event dispatcher capability được kiểm tra.
* [ ] API và CLI status nhất quán.

### Verification

* [ ] Full pytest pass.
* [ ] Architecture checker pass.
* [ ] Package isolation pass.
* [ ] Two-process E2E pass.
* [ ] Windows clean-clone pass.
* [ ] Worktree sạch.
* [ ] Remote SHA bằng local SHA.

## Final artifact

```text
artifacts/architecture_v2_runtime_cutover/final/
├── final_verdict.md
├── publication_receipt.json
├── dependency_report.json
├── package_isolation_report.json
├── api_lifecycle_report.json
├── worker_runtime_report.json
├── lease_recovery_report.json
├── outbox_report.json
├── migration_report.json
├── rollback_report.json
├── health_report.json
├── e2e_report.json
├── clean_clone_report.json
└── file_hash_manifest.json
```

## Final verdict hợp lệ

Chỉ khi toàn bộ gate pass:

```text
FINAL VERDICT: ARCHITECTURE_V2_RUNTIME_CUTOVER_COMPLETE
```

Nếu còn bất kỳ blocker nào:

```text
FINAL VERDICT: ARCHITECTURE_V2_RUNTIME_CUTOVER_NOT_COMPLETE
```

---

# 20. Thứ tự phase và dependency

```text
Phase 0  Baseline reproduction
   ↓
Phase 1  API lifecycle
   ↓
Phase 2  Package isolation
   ↓
Phase 3  Durable queue
   ↓
Phase 4  Heartbeat, lease, recovery
   ↓
Phase 5  Outbox repository
   ↓
Phase 6  Outbox runtime
   ↓
Phase 7  Migration mapping
   ↓
Phase 8  Data migration
   ↓
Phase 9  Rollback rehearsal
   ↓
Phase 10 Health wiring
   ↓
Phase 11 Real readiness
   ↓
Phase 12 CLI diagnostics
   ↓
Phase 13 Architecture alignment
   ↓
Phase 14 Two-process E2E
   ↓
Phase 15 Clean-clone verification
   ↓
Phase 16 Final audit
```

Không thực hiện Phase 14 trước khi Queue, Worker, Outbox, Migration và Health đều đạt gate.

---

# 21. Ưu tiên rủi ro

## P0 — Phải xử lý trước

1. API lifespan crash.
2. Worker không claim task SQL.
3. Outbox repository wiring sai.
4. Publisher không được start.
5. API/Worker thiếu package dependencies.
6. Migration self-copy.
7. Rollback không thực sự hoàn nguyên.
8. Health trả kết quả không phản ánh runtime.

## P1 — Xử lý trước E2E

1. Worker heartbeat.
2. Startup recovery.
3. Dead-letter replay.
4. Schema drift detection.
5. Architecture checker không đồng bộ.
6. Graceful shutdown drain.

## P2 — Hoàn thiện trước final verdict

1. Diagnostics UX.
2. Performance measurements.
3. Operational documentation.
4. Failure remediation messages.
5. Artifact hash manifest.

---

# 22. Tiêu chuẩn không được hạ thấp

Không được tuyên bố hoàn thành chỉ vì:

* Focused unit tests pass.
* Static import tests pass.
* Folder structure đúng.
* Object được khởi tạo.
* Publisher object tồn tại.
* Worker `_ready = True`.
* Migration history ghi `completed`.
* Health endpoint trả HTTP 200 trong test fake.
* Architecture checker trả zero nhưng regression test vẫn phát hiện violation.

Completion chỉ hợp lệ khi đường chạy thực:

```text
API submission
→ durable SQL queue
→ Worker atomic claim
→ lease heartbeat
→ execution
→ terminal state commit
→ transactional outbox
→ event publication
→ API result query
```

được chứng minh qua hai process độc lập và clean-clone E2E.
