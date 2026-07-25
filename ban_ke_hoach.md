# Đánh giá commit `8c2058bca187957c07f702984770fed136056cdf`

Commit này **chưa phải mốc hoàn thiện toàn bộ Architecture V2**. Nó là một commit bổ sung evidence, migration script, compatibility adapter và test lên trên commit `12ddf5f8...`. Artifact bên trong vẫn ghi `final_sha = 12ddf5f8...`, verdict chỉ là `CORE_CANONICAL_VERIFIED_READY_FOR_STAGING`, backend còn `112 failed` và `142 errors`; CI cũng chưa được đính kèm, rollback chưa rehearsal.

Không có GitHub Actions workflow run gắn với commit `8c2058b...`.

## 1. Hiện trạng thực tế

| Khu vực          |  Mức hoàn thiện | Nhận định                                                                                                      |
| ---------------- | --------------: | -------------------------------------------------------------------------------------------------------------- |
| `core/`          |         Khá cao | Canonical model, event, error và boundary đã hình thành; chưa đạt full-adoption do backend và staging gate     |
| `orchestration/` |      Trung bình | Cấu trúc đầy đủ nhưng scheduler, concurrency và một số lock vẫn giữ trạng thái trong RAM                       |
| `providers/`     |         Khá cao | Có adapter, registry, detection, cache, route lock; vẫn export legacy adapter                                  |
| `intelligence/`  |            Thấp | Public API mới có model router và route lock; thiếu 6 năng lực chính                                           |
| `tools/`         | Trung bình-thấp | Có registry, filesystem, shell, MCP; nhiều nhóm tool mục tiêu chưa được đưa vào public API, còn `legacy_tools` |
| `workflows/`     | Trung bình-thấp | Có workflow pack nhưng mới tạo step sequence tuần tự                                                           |
| `verification/`  |            Thấp | Nhiều gate nhận kết quả từ context và mặc định pass                                                            |
| `evals/`         |            Thấp | Có grader/runner nhưng có thể tự dùng expected output khi thiếu execution thật                                 |
| `context/`       |      Trung bình | Có provenance, budget, repository index, compactor và builder                                                  |
| `memory/`        | Trung bình-thấp | Có model, write policy và store; chưa thấy durable multi-layer integration                                     |
| `execution/`     |            Thấp | Public API chỉ export fake runtime và Hermes runtime                                                           |
| `storage/`       |             Khá | ORM, mapper, repository, UoW và outbox đã có                                                                   |
| `observability/` |      Trung bình | Có metrics, trace và audit contracts; chưa được nối toàn bộ runtime                                            |
| `apps/api`       |            Thấp | Vẫn là scaffold, task route dùng dictionary trong RAM                                                          |
| `apps/worker`    |            Thấp | Queue và lease nằm trong RAM, workflow execution đang mô phỏng                                                 |
| `apps/cli`       |            Thấp | Health, task, provider và eval là dữ liệu demo cố định                                                         |
| `apps/web`       |      Trung bình | Có build/lint, nhưng `package.json` chưa có test script                                                        |
| `apps/desktop`   | Thấp-trung bình | Có system metrics nhưng còn hard-code đường dẫn máy phát triển                                                 |
| `apps/backend`   | Legacy monolith | Vẫn tự composition database, model, tools, Hermes, browser, orchestration và provider routing                  |

### Các bằng chứng quan trọng

`apps/api` tự báo trạng thái `"scaffold"`; route task dùng `IN_MEMORY_TASKS` và timestamp hard-code.

Worker gọi bước thực thi mô phỏng; lease manager dùng `_leases` và `_pending_tasks` trong tiến trình, dù docstring tuyên bố distributed và zero duplicate.

CLI chỉ in dữ liệu giả, bao gồm cả tuyên bố “ALL SYSTEMS OPERATIONAL” và điểm eval 92.5%.

`intelligence` khai báo bảy thành phần nhưng chỉ export `RouteLock`, `ModelRouterPolicy`, `RoutingContext`.

Workflow hiện trả về danh sách step tuần tự; chưa thể hiện edge, condition, fan-out/fan-in hoặc artifact contract.

Verification mặc định `passed=True` khi context không có test result; eval dùng expected output nếu không tìm thấy execution. Đây là nguồn false-green nghiêm trọng.

---

# 2. Quyết định kiến trúc đề xuất

## Canonical application topology

```text
Web / Desktop / CLI
        │
        ▼
apps/api                    ← API server canonical duy nhất
        │
        ▼
ApplicationContainer
        │
        ├── intelligence
        ├── orchestration
        ├── workflows
        ├── tools
        ├── verification
        ├── execution
        ├── context / memory
        └── storage / observability
                │
                ▼
           apps/worker
```

### Vai trò cuối cùng của `apps/backend`

Vì cấu trúc mục tiêu vẫn giữ `apps/backend`, package này nên trở thành:

* Thin compatibility sidecar cho desktop hoặc deployment cũ.
* Import và khởi chạy application từ `apps/api`.
* Chứa migration-only router hoặc legacy API adapter có thời hạn.
* Không được sở hữu `services/`, domain model, scheduler, provider gateway, event bus hoặc tool executor riêng.

Không nên giữ cả `apps/api` và `apps/backend` như hai backend độc lập.

---

# 3. Roadmap hoàn thiện Architecture V2

## Phase 15 — Trusted Baseline và đóng Phase 14

### Mục tiêu

Biến commit `8c2058b...` thành baseline có evidence đáng tin cậy trước khi tiếp tục mở rộng.

### Công việc

1. Tạo branch:

```text
refactor/architecture-v2-full-completion
```

từ chính xác:

```text
8c2058bca187957c07f702984770fed136056cdf
```

2. Tạo lại toàn bộ receipt với `final_sha` đúng HEAD.
3. Loại bỏ đường dẫn tuyệt đối như `D:\code_ca_nhan\...` khỏi artifact.
4. Phân loại toàn bộ `112 failed` và `142 errors`:

   * app-state wiring;
   * import/package resolution;
   * fixture lifecycle;
   * database isolation;
   * duplicated service construction;
   * event loop/session leakage.
5. Chạy riêng:

   * workspace package tests;
   * `apps/backend`;
   * `apps/api`;
   * `apps/worker`;
   * frontend build/lint;
   * Rust checks;
   * migration tests.
6. Gắn CI trên Windows và Linux.
7. Sửa migration event log để không `except Exception: continue` một cách im lặng; record lỗi phải được quarantine và đếm.

### Gate

* Không còn backend collection error.
* Không có test mặc định bị bỏ qua vì import hoặc fixture lỗi.
* Receipt ghi đúng SHA hiện tại.
* CI run được gắn trực tiếp vào commit.
* Verdict:

```text
ARCHITECTURE_V2_BASELINE_TRUSTED
```

### Artifact

```text
artifacts/architecture_v2_completion/phase_15/
├── repository_inventory.json
├── package_maturity_matrix.json
├── backend_failure_classification.json
├── test_receipt.json
├── ci_receipt.json
└── baseline_verdict.json
```

---

## Phase 16 — Dependency Graph và canonical composition root

### Mục tiêu

Chấm dứt manual service wiring và biến package boundary thành quy tắc có thể kiểm chứng.

### Công việc

1. Mở rộng architecture linter. Checker hiện chỉ kiểm tra dependency bị cấm, chưa kiểm tra:

   * import ngoài `allowed_dependencies`;
   * dependency có import nhưng không khai báo trong `pyproject.toml`;
   * circular dependency;
   * public API leakage;
   * duplicate composition root.
2. Đồng bộ `scaffold_v2.yaml`, package README và `pyproject.toml`.
3. Sửa ngay mismatch:

   * `intelligence` được phép dùng `windagent_context`;
   * nhưng chưa khai báo dependency này trong `pyproject.toml`.
4. Tạo canonical composition:

```text
apps/api/windagent_api/
├── bootstrap.py
├── composition.py
├── lifespan.py
├── dependencies.py
└── health.py
```

5. Dùng typed `ApplicationContainer`, không gắn hàng chục object tùy ý vào `app.state`.
6. Tách interface và implementation:

   * package nghiệp vụ nhận port;
   * composition root chọn SQL, Hermes, browser hoặc local adapter.
7. Health readiness phải kiểm tra thật:

   * database;
   * migration version;
   * outbox;
   * worker heartbeat;
   * provider registry;
   * event publisher.

### Gate

* Không circular import.
* Không undeclared workspace dependency.
* Chỉ có một composition root production.
* `apps/backend` không còn tự tạo service graph độc lập.
* Import graph được xuất thành artifact.

---

## Phase 17 — Storage, migrations và observability foundation

### Mục tiêu

Cung cấp nền durable chung trước khi xây worker, memory và execution.

### Storage cần hoàn thiện

Schema canonical:

```text
sessions
tasks
task_runs
workflow_runs
workflow_steps
workflow_edges
execution_leases
workers
checkpoints
execution_events
outbox_records
artifacts
provider_configs
route_locks
usage_ledger
memory_records
plugin_installations
skill_installations
```

Cơ chế bắt buộc:

* optimistic version;
* atomic compare-and-set;
* unique idempotency key;
* fencing token;
* transaction task mutation + event + outbox;
* schema migration version;
* forward migration và rollback rehearsal;
* SQLite cho local;
* PostgreSQL-compatible repository contract cho multi-replica.

### Observability cần hoàn thiện

* `trace_id`, `task_id`, `run_id`, `step_id`, `session_id`.
* Structured logs.
* Span xuyên API → orchestration → provider/tool → worker.
* Metrics:

  * queue latency;
  * claim latency;
  * provider latency;
  * token/cost;
  * retries;
  * lease expiry;
  * tool failure;
  * recovery duration.
* Secret redaction trước khi ghi log/event.
* Audit event bất biến cho permission, destructive tool và secret access.

### Gate

* Restart không mất task, lease, event hoặc checkpoint.
* Outbox replay idempotent.
* Concurrent mutation test không tạo state conflict âm thầm.
* Trace của một task nối được xuyên toàn hệ thống.

---

## Phase 18 — Execution runtime và production worker

### Mục tiêu

Thay toàn bộ execution và worker mô phỏng bằng durable execution plane.

### Cấu trúc

```text
execution/
└── windagent_execution/
    ├── registry.py
    ├── runtime.py
    ├── requests.py
    ├── results.py
    ├── cancellation.py
    ├── streaming.py
    ├── sandbox/
    ├── worktree/
    └── adapters/
        ├── hermes.py
        ├── tool_runtime.py
        ├── browser_runtime.py
        ├── local_agent.py
        └── subprocess_runtime.py
```

### Công việc

1. `ExecutionRuntimeRegistry` chọn adapter theo capability.
2. Mỗi dispatch chứa:

   * run ID;
   * step ID;
   * attempt;
   * idempotency key;
   * lease generation;
   * fencing token;
   * deadline;
   * permission context.
3. Worker đăng ký capability và heartbeat durable.
4. Claim bằng atomic transaction, không dùng list/dict.
5. Heartbeat không được renew lease với fencing token cũ.
6. Result handler từ chối late result của worker đã mất lease.
7. Cancellation lan truyền đến Hermes, subprocess, browser và tool runtime.
8. Checkpoint/resume theo step.
9. Crash giữa:

   * tool execution;
   * result persistence;
   * event publish;
   * lease release
     phải phục hồi deterministic.
10. Xóa `FakeRuntimeAdapter` khỏi production composition; chỉ giữ trong test package.

### Gate

* Hai worker không thực thi cùng một step.
* Worker cũ không thể commit result sau khi lease bị reclaim.
* Multi-process và multi-replica fencing pass.
* Kill worker giữa step rồi restart có recovery receipt chính xác.
* Không polling vòng lặp 5 ms.

---

## Phase 19 — Tool platform hoàn chỉnh

### Mục tiêu

Hoàn thiện toàn bộ các nhóm trong kiến trúc mục tiêu và loại bỏ legacy tool adapter.

### Cấu trúc

```text
tools/windagent_tools/
├── registry/
├── filesystem/
├── shell/
├── git/
├── code_search/
├── ast/
├── lsp/
├── testing/
├── browser/
├── database/
├── github/
└── mcp/
```

### Contract chung

Mỗi tool phải khai báo:

* input/output schema;
* capability;
* risk level;
* side-effect class;
* idempotent hay non-idempotent;
* destructive hay reversible;
* timeout;
* required permission;
* sandbox requirement;
* artifact outputs;
* retry eligibility;
* redaction policy.

### Công việc chính

* Filesystem: canonical path, symlink escape protection, atomic write.
* Shell: allow/deny policy, process group cancellation, output limit.
* Git: worktree ownership, branch lock, dirty-state protection.
* Code search: grep/ripgrep abstraction, bounded output.
* AST: language-aware symbol extraction.
* LSP: lifecycle và timeout isolation.
* Testing: command runner và normalized test result.
* Browser: session ownership, navigation policy, screenshot artifact.
* Database: read-only mặc định, explicit write permission.
* GitHub: API port tách khỏi provider/model code.
* MCP: server trust policy, namespace collision handling.

### Gate

* Không export `windagent_tools.adapters.legacy_tools` ở top-level.
* Destructive tool không chạy khi thiếu explicit permission.
* Path sandbox, command injection và symlink escape tests pass.
* Tool result luôn có artifact/evidence hoặc structured failure.

---

## Phase 20 — Top-level plugins và skills

### Mục tiêu

Tách distribution content khỏi implementation package.

### Vai trò đề xuất

```text
plugins/
├── registry/
├── installed/
├── manifests/
└── examples/

skills/
├── catalog/
├── installed/
├── manifests/
└── examples/
```

* `plugins/` và `skills/` là content roots.
* Loader/runtime code vẫn thuộc `windagent_tools` hoặc một package plugin-runtime rõ ràng.
* Không đặt executable arbitrary Python vào plugin mà chạy trực tiếp trong API process.

### Công việc

* Manifest schema có version.
* Compatibility range với WindAgent.
* Hash/signature.
* Capability và permission declaration.
* Dependency resolution.
* Install, update, disable, uninstall.
* Plugin namespace isolation.
* Skill prompt/tool/workflow dependency validation.
* Hot reload chỉ cho development; production dùng version pin.
* Quarantine plugin lỗi.

### Gate

* Plugin không thể bypass PermissionEngine.
* Skill không thể gọi tool ngoài manifest.
* Collision tên tool/workflow được phát hiện.
* Reinstall cùng version idempotent.

---

## Phase 21 — Context và memory productionization

### Context

Hoàn thiện pipeline:

```text
Task
 → repository discovery
 → relevant files/symbols
 → recent tool outputs
 → session context
 → project memory
 → token allocation
 → deduplication
 → compaction
 → provenance manifest
```

Yêu cầu:

* Mỗi context item có source, timestamp, hash, sensitivity và token count.
* Phân bổ budget theo task type.
* Không để một file lớn chiếm toàn bộ context.
* Compaction phải giữ requirement, error, decision và unresolved item.
* Prompt-injection marker cho external/browser content.

### Memory

Các scope:

```text
working
session
project
user
episodic
```

Cần có:

* project isolation;
* retention policy;
* consent/write policy;
* provenance;
* update/forget;
* deduplication;
* TTL;
* semantic retrieval optional;
* secret và credential exclusion;
* transactional write qua storage.

### Gate

* Không rò memory giữa project/session.
* Memory write bị từ chối khi thiếu policy.
* Context manifest tái tạo được.
* Token budget không vượt model context limit.
* Compaction regression tests pass.

---

## Phase 22 — Intelligence full implementation

### Mục tiêu

Hoàn thiện bảy bounded components đã định nghĩa.

```text
intelligence/
├── task_classifier/
├── planner/
├── context_builder/
├── model_router/
├── summarizer/
├── reviewer/
└── reporter/
```

### `task_classifier`

* Deterministic rule trước.
* Model fallback khi confidence thấp.
* Multi-label capability.
* Trả workflow candidates và risk classification.

### `planner`

* Nhận task + context + workflow catalog.
* Trả `WorkflowDefinition` có version.
* Không trực tiếp chạy tool.
* Validate:

  * DAG;
  * tool availability;
  * permission;
  * acceptance criteria;
  * cost/deadline.

### `context_builder`

* Là intelligence facade gọi `windagent_context`.
* Không tự tạo repository index hoặc memory store riêng.

### `model_router`

* Chọn model ban đầu bằng rule.
* Duy trì model identity xuyên luồng.
* Khi 429 hoặc endpoint lỗi:

  * chỉ đổi endpoint tương đương;
  * giữ cùng canonical model;
  * không đổi model âm thầm.
* Route lock durable và có expiration.
* Cache key phải chứa model, provider compatibility, prompt hash và tool schema hash.

### `summarizer`

* Tóm tắt theo provenance.
* Không biến summary thành source of truth duy nhất.

### `reviewer`

* Kiểm tra patch, evidence và acceptance criteria.
* Không tự tuyên bố pass nếu thiếu verification result.

### `reporter`

* Sinh machine-readable report trước.
* Markdown/HTML chỉ là render layer.

### Gate

* Public API export đầy đủ bảy thành phần.
* Planner output luôn validate được.
* Route-lock failover tests pass.
* Reviewer không thể pass khi thiếu test evidence.
* Intelligence không import orchestration hoặc apps.

---

## Phase 23 — Workflow specification và workflow packs

### Mục tiêu

Chuyển workflow pack từ step sequence thành versioned executable DAG.

### Cấu trúc dữ liệu

Mỗi workflow cần:

* workflow ID và semantic version;
* input schema;
* node definitions;
* edges;
* conditional edges;
* fan-out/fan-in;
* artifact contracts;
* model requirement;
* tool requirement;
* retry policy;
* permission policy;
* checkpoint policy;
* verification gate;
* acceptance criteria;
* report schema.

### Built-in packs

* bugfix;
* CI fix;
* code review;
* feature;
* refactor;
* research;
* scientific evaluation;
* release.

### Công việc

* Dùng immutable workflow definition.
* Tách logical step khỏi concrete tool invocation.
* Planner có thể parameterize nhưng không sửa workflow pack gốc.
* Mỗi step có expected artifacts và completion predicate.
* Workflow registry hỗ trợ version pin.
* Workflow migration khi definition đổi giữa lúc run đang tồn tại.

### Gate

* DAG validation pass.
* Conditional/fan-in/retry/recovery tests pass.
* Run cũ tiếp tục dùng definition version cũ.
* Mỗi workflow có ít nhất một E2E real-runtime test.

---

## Phase 24 — Verification và evals fail-closed

### Verification

Thay toàn bộ context-default gate bằng runner thực:

* command execution;
* exit code thật;
* stdout/stderr thật;
* artifact hash;
* timeout;
* environment snapshot;
* test count parser;
* linter/type checker parser;
* security scanner;
* acceptance evaluator.

Nguyên tắc:

```text
missing evidence = BLOCKED
không phải PASSED
```

### Evals

* Mỗi eval case bắt buộc có `execution_id`.
* Không tự thay bằng expected output.
* Dataset version và checksum.
* Seed và runtime configuration.
* Model/provider/endpoint metadata.
* Tool call trace.
* Cost/token/latency.
* Replay result.
* Confidence interval cho suite lớn.
* Baseline comparison.
* Regression threshold.

### Gate

* Không có default-pass path.
* Không có synthetic execution fallback trong production eval.
* Replay và original execution parity được đo.
* Eval report chỉ pass khi evidence đầy đủ.
* False-green regression test bắt buộc.

---

## Phase 25 — Canonical API V2 cutover

### Mục tiêu

Biến `apps/api` từ scaffold thành API thật.

### Công việc

1. Xóa toàn bộ `IN_MEMORY_*`.
2. Route gọi application services qua typed dependency injection.
3. Các nhóm route:

   * sessions;
   * tasks;
   * runs;
   * workflows;
   * events;
   * providers;
   * tools;
   * permissions;
   * artifacts;
   * memory;
   * plugins;
   * skills;
   * evals;
   * observability.
4. WebSocket/SSE đọc canonical event stream.
5. Hỗ trợ:

   * reconnect;
   * `last_sequence`;
   * replay;
   * backpressure;
   * terminal event;
   * heartbeat.
6. Idempotency key cho POST task và destructive action.
7. Pagination và filtering.
8. OpenAPI canonical schema.
9. Error mapping từ `WindAgentError`.
10. V1 compatibility chỉ nằm ở edge adapter.
11. `/health/ready` không được trả ready nếu DB, migration hoặc worker chưa sẵn sàng.

### Gate

* API E2E chạy task thật tới terminal state.
* Restart API không mất task.
* WebSocket reconnect nhận đúng event còn thiếu.
* Contract test V1/V2 pass.
* Không còn hard-coded timestamp hoặc demo object.

---

## Phase 26 — CLI, Web và Desktop convergence

### CLI

* Chuyển thành API client hoặc local composition client.
* `doctor` kiểm tra thật.
* `run` stream event thật.
* `task inspect` đọc snapshot và event trace thật.
* `eval` chạy eval service thật.
* JSON output mode cho automation.
* Exit code chuẩn.

### Web

`package.json` hiện chỉ có dev/build/lint, chưa có test script.

Cần bổ sung:

* generated TypeScript API client;
* query cache;
* WebSocket resume;
* optimistic UI có reconciliation;
* task/workflow/event/provider/tool pages;
* permission dialog;
* artifact viewer;
* eval report;
* component/integration/E2E test;
* accessibility và error boundary.

### Desktop

Desktop hiện hard-code các đường dẫn `D:\antigaravity_code\...` trong logger/startup marker và mới đăng ký hai Tauri command.

Cần:

* loại bỏ toàn bộ absolute development path;
* app data directory chuẩn theo OS;
* sidecar supervisor cho API và worker;
* dynamic port reservation;
* process health/restart;
* graceful shutdown;
* log rotation;
* credential storage bằng OS keychain;
* update/migration lifecycle;
* installer smoke test;
* frontend dùng cùng API contract với web.

### Gate

* CLI/Web/Desktop cùng quan sát một task và cùng event sequence.
* Không còn demo output.
* Desktop restart sidecar an toàn.
* Frontend unit, integration và E2E pass.
* Windows path portability tests pass.

---

## Phase 27 — Legacy backend evacuation

### Mục tiêu

Loại bỏ business logic trùng lặp khỏi `apps/backend`.

### Di chuyển

| Legacy source                 | Đích                                           |
| ----------------------------- | ---------------------------------------------- |
| `services/planner_service.py` | `intelligence/planner`                         |
| model routing services        | `intelligence/model_router` + `providers`      |
| `tool_executor.py`            | `tools` + `execution`                          |
| Hermes runtime/session bridge | `execution/adapters/hermes`                    |
| browser service               | `tools/browser` + execution adapter            |
| worktree service              | `execution/worktree`                           |
| event bus/hooks               | `core/events` + storage outbox + observability |
| permission service            | `core/security` + `tools/security`             |
| workflow services             | `orchestration` + `workflows`                  |
| DB models/repositories        | `storage`                                      |
| eval/verification             | `evals` + `verification`                       |

### Trạng thái cuối của `apps/backend`

Chỉ còn:

```text
apps/backend/
├── main.py              # compatibility bootstrap
├── compatibility/
├── migrations/
└── README.md
```

Không còn:

```text
services/
db/models.py
planner riêng
scheduler riêng
event bus riêng
provider gateway riêng
tool executor riêng
```

### Gate

* AST scan không còn import legacy service từ production path.
* Không có duplicate model, event, lifecycle, provider contract.
* Backend compatibility tests pass.
* V1 API adapter gọi canonical services.
* Có deadline rõ ràng để xóa compatibility layer sau release ổn định.

---

## Phase 28 — Production verification và full-adoption verdict

### Kiểm thử bắt buộc

1. Unit toàn workspace.
2. Contract tests giữa bounded contexts.
3. API integration.
4. Worker multi-process.
5. Multi-replica fencing.
6. Outbox replay.
7. Crash/restart matrix.
8. Database migration với dữ liệu thật.
9. Event migration với quarantine.
10. WebSocket disconnect/reconnect.
11. Provider 429 same-model endpoint failover.
12. Tool destructive replay guard.
13. Plugin/skill permission isolation.
14. Context/memory project isolation.
15. Eval false-green tests.
16. Desktop sidecar crash recovery.
17. Performance and soak tests.
18. Security and secret scanning.
19. Rollback rehearsal.
20. Clean-clone build trên Windows và Linux.

### Performance gate đề xuất

* API task submit p95 ≤ 100 ms, không tính model latency.
* Durable queue claim p95 ≤ 50 ms.
* Event publish-to-client p95 ≤ 250 ms.
* Idle CPU không có busy polling.
* Duplicate execution = 0.
* Stale fencing result accepted = 0.
* Lost terminal events = 0.
* Recovery hoàn tất trong giới hạn cấu hình.
* Không có plaintext secret trong DB, log hoặc artifact.

### Final artifact

```text
artifacts/architecture_v2_completion/final/
├── commit_receipt.json
├── architecture_graph.json
├── package_maturity_matrix.json
├── legacy_removal_report.json
├── test_matrix.json
├── ci_receipt.json
├── migration_receipt.json
├── multi_replica_fencing_receipt.json
├── crash_recovery_receipt.json
├── rollback_receipt.json
├── security_report.json
├── performance_report.json
└── final_verdict.json
```

Verdict duy nhất được chấp nhận:

```text
ARCHITECTURE_V2_FULL_ADOPTION_VERIFIED
```

---

# 4. Thứ tự dependency bắt buộc

```text
Phase 15  Trusted baseline
    ↓
Phase 16  Dependency graph + composition root
    ↓
Phase 17  Storage + observability
    ↓
Phase 18  Execution + worker
    ↓
Phase 19  Tools
    ↓
Phase 20  Plugins + skills
    ↓
Phase 21  Context + memory
    ↓
Phase 22  Intelligence
    ↓
Phase 23  Workflows
    ↓
Phase 24  Verification + evals
    ↓
Phase 25  API cutover
    ↓
Phase 26  CLI + Web + Desktop
    ↓
Phase 27  Legacy backend evacuation
    ↓
Phase 28  Staging + production verification
```

Không nên triển khai đồng thời API, worker, intelligence và workflow trên các contract chưa khóa. Làm như vậy sẽ tái tạo đúng vấn đề hiện tại: nhiều package có tên và public class nhưng không có một vertical slice chạy thật.

# 5. Definition of Done toàn chương trình

Kiến trúc chỉ được xem là hoàn thiện khi:

* Không còn production store hoặc lease nằm trong dictionary/list.
* Không còn demo response, timestamp hoặc health result hard-code.
* `apps/api` là API canonical duy nhất.
* `apps/backend` không còn business logic độc lập.
* Worker sử dụng durable claim và fencing.
* Intelligence có đủ bảy component.
* Workflow là versioned DAG, không chỉ là step list.
* Tool legacy adapter bị loại khỏi production exports.
* Verification fail-closed.
* Eval không thể chạy nếu thiếu execution thật.
* Web, desktop và CLI dùng chung API contract.
* Mọi state mutation có event, outbox và trace.
* Backend, workspace, frontend và desktop test đều xanh.
* CI, multi-replica fencing và rollback rehearsal được thực hiện tại đúng final SHA.
