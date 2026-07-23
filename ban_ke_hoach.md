Kế hoạch hoàn thiện orchestration/ — Cutover toàn phần, loại bỏ legacy
1. Quyết định kiến trúc

Phạm vi được chốt:

windagent_orchestration trở thành runtime orchestration duy nhất.
Không duy trì hai orchestration engine sau khi hoàn tất.
Toàn bộ orchestration trong apps/backend/services/ phải được thay thế và xóa.
API, WebSocket và frontend contract hiện tại phải được giữ tương thích.
Ưu tiên cao nhất là:
Hiệu năng.
Tính deterministic.
Crash recovery.
Không thực thi trùng.
Không replay thao tác destructive.
Thực hiện tiếp từ commit:
59aaea22339d26ec9b10dcf398e4380f65f656ba

Package hiện tại đã khai báo đúng bounded context và chỉ phụ thuộc windagent-core cùng windagent-storage.

Tuy nhiên implementation hiện mới ở mức foundation:

Scheduler lưu queue bằng list, gọi sort() sau mỗi lần enqueue và chỉ giữ lock trong RAM.
Dispatcher chống duplicate bằng set trong tiến trình, mất toàn bộ trạng thái khi restart.
Task facts được lưu trong dictionary nội bộ của TaskManager, chưa durable.
Recovery hiện quét event theo session rồi tạo RunId mới, chưa reconcile đúng run, worker và lease thực tế.
Chưa có WorkflowEngine production hoàn chỉnh.
Backend legacy vẫn có DAGScheduler, Hermes supervisor và recovery riêng. Legacy scheduler còn sử dụng vòng polling liên tục với khoảng nghỉ 5 ms.
Legacy recovery chỉ chuyển run chết sang interrupted và task sang retryable, chưa có checkpoint/resume đầy đủ.

Do đó không nên chỉ di chuyển file. Cần xây lại orchestration runtime theo durable execution model rồi cutover một lần sau khi vượt toàn bộ gate.

2. Cấu trúc mục tiêu
orchestration/
├── pyproject.toml
├── README.md
├── windagent_orchestration/
│   ├── __init__.py
│   ├── composition.py
│   ├── ports.py
│   ├── commands.py
│   ├── queries.py
│   ├── events.py
│   ├── metrics.py
│   │
│   ├── task_manager/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── facts.py
│   │   ├── status.py
│   │   ├── lifecycle.py
│   │   ├── command_handlers.py
│   │   └── query_handlers.py
│   │
│   ├── workflow_engine/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── definition.py
│   │   ├── graph.py
│   │   ├── validator.py
│   │   ├── cursor.py
│   │   ├── readiness.py
│   │   ├── result_aggregator.py
│   │   └── checkpoints.py
│   │
│   ├── state_machine/
│   │   ├── __init__.py
│   │   ├── task.py
│   │   ├── workflow.py
│   │   ├── step.py
│   │   ├── transitions.py
│   │   ├── invariants.py
│   │   └── errors.py
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── priority_queue.py
│   │   ├── fairness.py
│   │   ├── concurrency.py
│   │   ├── resource_limits.py
│   │   ├── project_locks.py
│   │   └── wakeup.py
│   │
│   ├── dispatcher/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── leases.py
│   │   ├── deduplication.py
│   │   ├── worker_registry.py
│   │   ├── heartbeat.py
│   │   └── result_handler.py
│   │
│   ├── retry/
│   │   ├── __init__.py
│   │   ├── policy.py
│   │   ├── classifier.py
│   │   ├── backoff.py
│   │   ├── budget.py
│   │   └── deadline.py
│   │
│   └── recovery/
│       ├── __init__.py
│       ├── manager.py
│       ├── scanner.py
│       ├── reconciler.py
│       ├── checkpoint_loader.py
│       ├── lease_reclaimer.py
│       ├── replay_guard.py
│       └── startup_report.py
│
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    ├── concurrency/
    ├── recovery/
    ├── performance/
    └── cutover/

Không giữ các file phẳng hiện tại như:

scheduler.py
dispatcher.py
recovery.py
task_manager.py
retry_policy.py
state_machine.py

Sau khi các package mới hoàn chỉnh, các file phẳng phải bị xóa, không để compatibility import kéo dài.

3. Phân định trách nhiệm
task_manager/

Là application facade của orchestration.

Chịu trách nhiệm:

Nhận task command.
Tạo TaskRun.
Quản lý lifecycle.
Gọi classifier, planner và context builder qua port.
Khởi tạo workflow.
Pause, resume, cancel.
Derive UI status từ durable facts.
Trả task snapshot cho API.
Không trực tiếp chạy tool, model hoặc Hermes.
workflow_engine/

Chịu trách nhiệm:

Nạp WorkflowDefinition.
Validate DAG.
Quản lý workflow cursor.
Xác định step nào sẵn sàng.
Fan-out/fan-in.
Conditional edge.
Aggregation.
Checkpoint sau mỗi state-changing operation.
Không trực tiếp quản lý worker process.
state_machine/

Chịu trách nhiệm:

Task state.
Workflow state.
Step state.
Transition table.
Invariant.
Terminal state.
Transition reason.
Optimistic version.
Reject mọi transition không hợp lệ.

State machine hiện có 15 trạng thái task phù hợp với master plan, nhưng mới chỉ kiểm tra chuyển trạng thái trong bộ nhớ.

scheduler/

Chịu trách nhiệm:

Priority.
Bounded concurrency.
Fairness giữa session/project.
Resource admission.
Project lock.
Worktree ownership.
Wake-up theo event.
Không busy-poll database.
Không trực tiếp submit sang Hermes.
dispatcher/

Chịu trách nhiệm:

Claim step.
Tạo execution lease.
Chọn worker phù hợp theo capability.
Gọi ExecutionRuntimePort.
Duy trì heartbeat.
Deduplicate.
Nhận kết quả.
Release hoặc expire lease.
retry/

Chịu trách nhiệm:

Error classification.
Retry eligibility.
Exponential backoff và jitter.
Attempt budget.
Cost/token budget.
Deadline.
Provider/tool-specific policy.
Idempotency requirement.

Không giữ hành vi hiện tại là mặc định retry mọi exception không phân loại. Implementation hiện tại đang làm như vậy và có thể lặp lại lỗi lập trình hoặc lỗi destructive.

recovery/

Chịu trách nhiệm:

Startup scan.
Lease reclamation.
Worker reconciliation.
Checkpoint restoration.
Event sequence verification.
Resume safe steps.
Chặn destructive replay.
Sinh startup recovery receipt.
Không tạo run giả hoặc RunId mới thay cho run cũ.
4. Luồng orchestration chuẩn
API / CLI / Desktop
        │
        ▼
TaskManager.submit()
        │
        ├── persist Task + TaskRun
        ├── append task.received event
        └── transition RECEIVED
        │
        ▼
Classifier / Context / Planner ports
        │
        ▼
WorkflowEngine.create_run()
        │
        ├── validate DAG
        ├── persist workflow + steps + edges
        ├── checkpoint
        └── mark root steps READY
        │
        ▼
Scheduler.enqueue_ready_steps()
        │
        ├── priority heap
        ├── fairness
        ├── resource admission
        └── project/worktree lock
        │
        ▼
Dispatcher.claim()
        │
        ├── atomic execution lease
        ├── idempotency key
        ├── worker capability match
        └── dispatch through ExecutionRuntimePort
        │
        ▼
Worker / Hermes / Tool runtime
        │
        ├── heartbeat
        ├── progress events
        └── terminal result
        │
        ▼
Dispatcher.result_handler()
        │
        ├── persist result
        ├── release lease
        ├── transition step
        └── append outbox event
        │
        ▼
WorkflowEngine.advance()
        │
        ├── unlock downstream steps
        ├── aggregate results
        ├── verify/review
        └── complete or retry

Mỗi state mutation phải đi qua:

load aggregate
→ verify expected version
→ validate transition
→ update durable facts
→ append event
→ append outbox
→ commit
5. Roadmap triển khai
Phase 8.0 — Inventory và performance baseline
Mục tiêu

Xác định chính xác mọi orchestration entrypoint và đo baseline trước khi thay thế.

Công việc

Inventory:

apps/backend/services/dag_scheduler.py
apps/backend/services/recovery_service.py
apps/backend/services/hermes/supervisor.py
apps/backend/services/workflow_service.py
apps/backend/services/workflow_runner.py
apps/backend/routers/conversations.py
apps/backend/routers/sessions.py
apps/backend/routers/workflows.py
apps/backend/main.py
apps/worker/*
apps/api/*

Lập call graph:

HTTP route
→ service
→ scheduler/supervisor
→ Hermes bridge
→ event bus
→ database
→ WebSocket

Đo:

Task submission latency.
DAG validation time.
Dispatch latency.
DB query count trên mỗi step.
Idle CPU.
Peak memory.
Throughput.
Duplicate dispatch rate.
Restart recovery duration.
Event propagation latency.
Artifact
artifacts/architecture_v2/phase_08/
├── legacy_orchestration_inventory.json
├── orchestration_call_graph.json
├── current_state_matrix.json
├── performance_baseline.json
└── baseline_receipt.json
Gate
Không thay behavior.
Inventory không bỏ sót entrypoint.
Có baseline tái tạo được.
Không chuyển phase nếu không chạy được benchmark tối thiểu.
Phase 8.1 — Contracts và package decomposition
Mục tiêu

Tách file phẳng thành bounded components nhưng chưa cutover.

Ports bắt buộc
TaskRuntimeRepository
WorkflowRuntimeRepository
ExecutionLeaseRepository
CheckpointRepository
WorkerRegistryPort
ExecutionRuntimePort
Clock
IdGenerator
EventPublisher
OutboxPort
PermissionPort
VerificationPort
ResourceMonitorPort

ExecutionRuntimePort là abstraction chung cho:

Hermes.
Local agent.
Workflow worker.
Browser runtime.
Computer-use runtime.
Tool execution runtime.

Orchestration không được import:

apps.backend
HermesSessionBridge
provider SDK
FastAPI
concrete SQLAlchemy ORM
Gate
Import-boundary check pass.
Public API được export từ top-level package.
Không circular import.
Legacy runtime vẫn chạy trong giai đoạn này.
Phase 8.2 — Durable state machine và TaskManager
Mục tiêu

Loại bỏ _facts: Dict[...] trong RAM.

Công việc

Tạo durable facts:

task_id
run_id
session_id
state
state_version
current_workflow_id
current_step_id
last_sequence
pending_permission_id
retry_count
last_error_code
last_error_metadata
verification_state
deadline_at
cancel_requested_at
paused_at
updated_at

Mỗi transition phải có:

from_state
to_state
reason_code
actor
correlation_id
expected_version
occurred_at

Dùng optimistic concurrency:

UPDATE task_runs
SET state = ?, state_version = state_version + 1
WHERE id = ? AND state_version = ?

Nếu affected rows bằng 0:

WINDAGENT_ERR_CONCURRENT_STATE_MODIFICATION
Gate
Toàn bộ transition table được test.
100 concurrent transition attempts không làm sai state.
Restart không mất task facts.
Terminal state không thể bị mở lại.
API status được derive từ durable facts.
Phase 8.3 — Workflow engine và DAG runtime
Mục tiêu

Thay thế hoàn toàn apps/backend/services/dag_scheduler.py.

Công việc

DAG representation:

nodes_by_id: dict
incoming_count: dict
outgoing_edges: dict
ready_set
completed_set
failed_set
blocked_set

Cycle detection và validation phải đạt:

O(V + E)

Workflow hỗ trợ:

Sequential.
Parallel fan-out.
Fan-in.
Conditional branch.
Optional step.
Required step.
Step timeout.
Failure policy.
Compensation metadata.
Checkpoint.
Resume.

Không query toàn bộ node/edge lại trong mỗi vòng scheduler như legacy.

Gate
DAG 10.000 node validate được trong giới hạn benchmark.
Dangling edge bị reject.
Cycle bị reject.
Fan-out/fan-in deterministic.
Failed required dependency không để downstream chạy.
Resume không chạy lại completed step.
Không còn production import tới legacy DAGScheduler.
Phase 8.4 — Scheduler hiệu năng cao
Mục tiêu

Thay scheduler dựa trên list.sort() bằng scheduler event-driven.

Thiết kế

Queue:

heapq hoặc indexed priority heap

Sort key:

effective_priority
created_at
sequence
task_id

Effective priority phải tính:

base priority
+ age boost
+ deadline pressure
+ retry penalty
+ project fairness

Concurrency:

global semaphore
per-project semaphore
per-runtime semaphore
per-worktree exclusive lock
resource admission

Wake-up:

asyncio.Condition
event notification
outbox signal

Không dùng:

while True:
    await asyncio.sleep(0.005)
Fairness

Dùng weighted fair scheduling hoặc deficit round-robin để một project lớn không chiếm toàn bộ worker.

Gate
Idle scheduler không busy-loop.
Không starvation.
Priority ordering đúng.
Per-project lock đúng.
Worktree không bị hai coding agent ghi đồng thời.
Cancelled item được loại khỏi queue hiệu quả.
Queue 100.000 item không gây tăng độ trễ bất thường.
Phase 8.5 — Dispatcher, leases và worker registry
Mục tiêu

Bảo đảm exactly-once claim và at-least-once result handling có deduplication.

Execution lease
lease_id
run_id
step_id
worker_id
attempt
status
claimed_at
heartbeat_at
expires_at
idempotency_key
dispatch_token
version

Claim phải atomic:

UPDATE workflow_steps
SET lease_id = ?, status = 'dispatched'
WHERE id = ?
  AND status = 'ready'
  AND lease_id IS NULL
Worker registry

Theo dõi:

worker_id
runtime_type
capabilities
capacity
active_count
health
last_heartbeat
workspace affinity
supported tools
supported agent types
Hermes migration

HermesSupervisor không được di chuyển nguyên khối vào orchestration.

Thay bằng:

HermesExecutionRuntimeAdapter
implements ExecutionRuntimePort

Adapter được đặt tại execution hoặc application composition layer, không nằm trong domain orchestration.

Gate
100 concurrent claims chỉ có một claim thành công.
Duplicate result không tạo duplicate event hoặc artifact.
Worker chết làm lease expire.
Worker heartbeat được kiểm tra.
Runtime cancellation được truyền xuống adapter.
Không còn orchestration state trong HermesSupervisor.
Phase 8.6 — Retry, timeout và cancellation
Mục tiêu

Retry có phân loại, budget và deadline.

Error classes
RETRYABLE_TRANSIENT
RETRYABLE_RATE_LIMIT
RETRYABLE_RESOURCE
RETRYABLE_RUNTIME_LOST
NON_RETRYABLE_VALIDATION
NON_RETRYABLE_PERMISSION
NON_RETRYABLE_DESTRUCTIVE_UNCERTAIN
NON_RETRYABLE_INTEGRITY
NON_RETRYABLE_CANCELLED
Retry decision
error classification
AND attempt < max_attempts
AND deadline chưa hết
AND retry budget còn
AND operation retry-safe
AND idempotency được chứng minh
Backoff
exponential backoff
+ bounded jitter
+ Retry-After support
+ maximum deadline
Cancellation

Cancellation hierarchy:

session
→ task
→ workflow
→ step
→ runtime invocation
→ process tree

Cancellation phải durable; không chỉ lưu trong set của tiến trình như implementation hiện tại.

Gate
Non-retryable error không retry.
Rate limit tôn trọng Retry-After.
Retry exhaustion chuyển terminal state chính xác.
Cancellation hoạt động qua restart.
Child process được terminate.
Không để orphan lease hoặc orphan worker run.
Phase 8.7 — Recovery và checkpoint
Mục tiêu

Recovery chạy được sau backend crash, worker crash và mất kết nối runtime.

Startup recovery flow
1. Acquire singleton recovery lock
2. Scan non-terminal task/workflow/step
3. Load latest checkpoints
4. Inspect active leases
5. Query worker/runtime health
6. Reconcile persisted state với runtime state
7. Reclaim expired leases
8. Resume safe step
9. Block uncertain destructive step
10. Emit recovery receipt
11. Release recovery lock
Recovery decision matrix
Persisted	Runtime	Hành động
running	alive	reattach
running	completed	ingest terminal result
running	missing	expire lease, classify retry
dispatched	never started	redispatch nếu safe
destructive running	unknown	block, require review
completed	runtime running	cancel duplicate runtime
cancelled	runtime alive	propagate cancellation
retry_wait	deadline passed	move ready hoặc fail
Destructive replay guard

Không hard-code chỉ năm tool name như hiện tại. Risk phải lấy từ ToolDefinition và permission metadata.

Quy tắc:

read-only + idempotent
    → auto-resume

workspace-write + idempotency key
    → resume có verification

destructive + terminal result unknown
    → không replay, WAITING_PERMISSION hoặc FAILED_INTEGRITY
Gate
Kill backend tại từng transition point.
Restart không duplicate tool call.
Interrupted destructive operation không tự chạy lại.
Recovery giữ nguyên run ID.
Event sequence monotonic.
Recovery 1.000 in-flight runs đạt performance budget.
Phase 8.8 — Composition và production cutover
Mục tiêu

Chuyển tất cả entrypoint sang orchestration V2.

Thứ tự cutover
1. Worker entrypoint
2. Internal execution service
3. Workflow APIs
4. Task/session APIs
5. WebSocket event producers
6. Desktop commands
7. CLI commands
8. Startup recovery
9. Shutdown cancellation
API compatibility

Giữ nguyên:

URL.
HTTP methods.
Request shape.
Response shape.
Error status.
WebSocket event shape.
Event sequence semantics.
Pause/resume/stop behavior.

API layer chỉ làm:

parse request
→ invoke orchestration command
→ map result

Không để business logic orchestration trong router.

Gate
Production runtime chỉ resolve windagent_orchestration.
Không còn router gọi legacy scheduler/supervisor/recovery.
E2E task thật chạy qua V2.
WebSocket nhận event thật.
Pause/resume/cancel chạy thật.
Restart recovery chạy thật.
Frontend không cần compatibility workaround mới.
Phase 8.9 — Performance hardening
Performance targets

Các ngưỡng phải được đo trên SQLite local và môi trường Windows mục tiêu:

Metric	Gate
Task enqueue p95	≤ 15 ms
Ready-step scheduling p95	≤ 10 ms
Dispatch claim p95	≤ 20 ms
State transition p95	≤ 15 ms
Event persist-to-broadcast p95	≤ 50 ms
DAG 1.000 node validation	≤ 50 ms
DAG 10.000 node validation	≤ 500 ms
1.000-run startup recovery	≤ 5 giây
Duplicate execution	0
Idle scheduler CPU	< 1% một core
Lost terminal result	0
Orphan lease sau test	0

Các ngưỡng này chỉ được điều chỉnh nếu có artifact benchmark chứng minh giới hạn phần cứng hoặc SQLite.

Tối ưu bắt buộc
heapq, không sort toàn queue.
Indexed database queries.
Batch state reads.
Batch event/outbox writes.
Prepared statement/repository reuse.
Không N+1 query trên DAG.
Không polling 5 ms.
Không serialize payload nhiều lần.
Bounded event buffer.
Backpressure.
Lazy artifact loading.
Structured metrics không block execution.
asyncio.TaskGroup hoặc quản lý task tương đương.
Graceful shutdown có deadline.
Gate
Benchmark cũ và mới cùng workload.
V2 không chậm hơn legacy ở critical path.
Không đổi correctness để đạt benchmark.
Memory không tăng tuyến tính vô hạn theo số completed run.
Phase 8.10 — Xóa legacy và decommission
Chỉ thực hiện khi tất cả gate trước pass

Xóa hoặc rút toàn bộ orchestration logic khỏi:

apps/backend/services/dag_scheduler.py
apps/backend/services/recovery_service.py
apps/backend/services/hermes/supervisor.py
apps/backend/services/workflow_service.py
apps/backend/services/workflow_runner.py

Các phần Hermes transport còn cần thiết phải chuyển thành adapter trong execution layer, không giữ tên hoặc vai trò supervisor orchestration legacy.

Xóa:

Legacy feature flags liên quan orchestration.
Shadow orchestration comparator.
Compatibility shim cho workflow/task.
Legacy ORM access trực tiếp từ orchestration.
Test chỉ dành cho legacy orchestration.
Dead routes.
Dead event producer.
Dead dependency injection.
Dead config.
Static enforcement

Thêm script:

scripts/check_no_legacy_orchestration.py

Fail nếu phát hiện:

from services.dag_scheduler import
from services.recovery_service import
from services.hermes.supervisor import
from services.workflow_runner import

Hoặc construction trực tiếp của class legacy.

Final gate
legacy_orchestration_files = 0
legacy_orchestration_imports = 0
legacy_orchestration_runtime_paths = 0
compatibility_orchestration_flags = 0
6. Migration map
Legacy	Đích mới
DAGScheduler.validate()	workflow_engine.validator
DAGScheduler.run_plan()	workflow_engine.engine + scheduler.service
_run_task() retry logic	dispatcher.service + retry.policy
Parent progress aggregation	workflow_engine.result_aggregator
HermesSupervisor.spawn_subagent()	ExecutionRuntimePort.dispatch()
Hermes run mapping	Hermes execution adapter
stop_subagent()	cancellation propagation
Worktree assignment	dispatcher resource admission
RecoveryManager.recover() legacy	recovery.reconciler
replay_after()	event store/replay service
In-memory task facts	durable task runtime repository
In-memory dispatch set	durable execution lease
In-memory cancellation set	durable cancellation request
Direct event bus call	transactional outbox
7. Database/index requirements

Các bảng hoặc storage model tương đương:

task_runs
workflow_runs
workflow_step_runs
execution_leases
execution_attempts
workflow_checkpoints
cancellation_requests
worker_registrations
worker_heartbeats
recovery_runs

Index tối thiểu:

task_runs(session_id, state)
task_runs(state, priority, created_at)
workflow_runs(task_run_id, state)
workflow_step_runs(workflow_run_id, state)
workflow_step_runs(state, ready_at, priority)
execution_leases(status, expires_at)
execution_leases(step_run_id, status)
execution_attempts(step_run_id, attempt)
worker_registrations(runtime_type, health)
outbox(status, available_at)

Mọi migration phải additive trước. Chỉ xóa bảng/cột legacy trong migration decommission riêng sau khi đã có backup và parity receipt.

8. Test matrix bắt buộc
Unit
Transition table.
Invariant.
DAG cycle.
Dependency readiness.
Priority.
Fairness.
Retry classification.
Backoff.
Deadline.
Destructive replay guard.
Contract
Repository contracts.
Execution runtime port.
Worker registry.
Event publisher.
Checkpoint repository.
Permission integration.
Concurrency
Duplicate claim.
Concurrent transition.
Concurrent cancel/result.
Lease expiry/result race.
Worker heartbeat/reclaimer race.
Project lock.
Worktree lock.
Crash injection

Dừng process tại:

sau state update, trước event
sau event, trước outbox
sau lease claim, trước dispatch
sau dispatch, trước heartbeat
sau tool success, trước result persistence
sau result persistence, trước lease release
sau checkpoint, trước downstream unlock
E2E
Single-step task.
Multi-step sequential.
Fan-out/fan-in.
Permission wait.
Pause/resume.
Cancel.
Retry.
Worker crash.
Backend restart.
WebSocket reconnect/replay.
Coding agent với worktree.
Browser agent.
Hermes agent.
Destructive tool interruption.
Performance
100, 1.000 và 10.000 DAG nodes.
10, 100 và 1.000 concurrent tasks.
Queue 100.000 items.
1.000 stale leases.
1.000 startup recovery candidates.
Long-running soak test.
Memory leak check.
9. Commit strategy
1. chore(orchestration): inventory legacy runtime and freeze benchmarks
2. refactor(orchestration): introduce package boundaries and runtime ports
3. feat(orchestration): add durable task state machine and task manager
4. feat(orchestration): implement workflow DAG engine and checkpoints
5. perf(orchestration): add event-driven priority scheduler and fairness
6. feat(orchestration): add durable dispatcher leases and worker registry
7. feat(orchestration): implement retry budgets cancellation and deadlines
8. feat(orchestration): implement crash recovery and replay guards
9. refactor(apps): cut production entrypoints to orchestration v2
10. perf(orchestration): optimize scheduling dispatch and recovery paths
11. test(orchestration): add concurrency crash and performance gates
12. refactor(legacy): remove legacy orchestration runtime
13. docs(orchestration): publish cutover and decommission receipts

Không gộp toàn bộ thay đổi vào một commit.

10. Acceptance verdict cuối

Chỉ được kết luận thành công khi:

FINAL VERDICT:
ORCHESTRATION_V2_FULL_CUTOVER_PASSED

REQUIRED:
- production runtime uses only windagent_orchestration
- no legacy orchestration imports
- no legacy orchestration feature flags
- no duplicate execution
- crash recovery passed
- destructive replay guard passed
- API parity passed
- WebSocket parity passed
- performance gates passed
- full backend tests passed
- frontend tests/typecheck/build passed
- migration upgrade/downgrade passed
- clean-clone E2E passed
- worktree clean
- remote SHA equals local SHA

Nếu một trong các điều kiện trên không đạt:

FINAL VERDICT:
BLOCKED_ORCHESTRATION_V2_CUTOVER

Không được xóa legacy để ép cutover thành công.