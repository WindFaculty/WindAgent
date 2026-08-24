Đúng. Nếu mục tiêu là **đưa WindAgent lên production**, tôi sẽ đổi hướng từ “migration mềm” sang **hard cutover có kiểm soát** cho `tests/`: thiết kế kiến trúc đích ngay, di chuyển test về đúng tier, sửa fixture/CI cùng lúc, rồi khóa kiến trúc bằng automated gates.

Repo hiện tại mới có `architecture/`, `contracts/`, `fakes/`, `fixtures/`, `integration/`, `regression/`, `unit/`; chưa có `component/`, `verification/`, `e2e/`, `support/` hay root `conftest.py`.  Báo cáo cũng cho thấy khoảng 60% `tests/unit/` đang chạm DB/HTTP, nên giữ cấu trúc hiện tại rồi chỉ thêm marker sẽ không đủ sạch cho production. 

## Kiến trúc production tôi đề xuất

```text
tests/
├── conftest.py
│
├── support/
│   ├── db.py
│   ├── api.py
│   ├── waiting.py
│   ├── process.py
│   ├── environment.py
│   └── assertions.py
│
├── fakes/
│   ├── providers/
│   ├── studio/
│   ├── execution/
│   └── storage/
│
├── fixtures/
│   ├── factories/
│   ├── canonical/
│   └── video_production/
│
├── unit/
│   ├── core/
│   ├── domain/
│   ├── intelligence/
│   ├── orchestration/
│   ├── workflows/
│   └── tools/
│
├── component/
│   ├── storage/
│   ├── providers/
│   ├── orchestration/
│   ├── worker/
│   ├── observability/
│   └── migrations/
│
├── contracts/
│   ├── api/
│   ├── cli/
│   ├── story/
│   ├── studio/
│   └── code_video/
│
├── integration/
│   ├── studio/
│   ├── providers/
│   ├── workers/
│   └── persistence/
│
├── e2e/
│   ├── multiprocess/
│   ├── postgres/
│   └── golden_path/
│
├── architecture/
│   ├── boundaries/
│   ├── policies/
│   ├── canonical/
│   └── forbidden_dependencies/
│
└── verification/
    ├── evidence/
    ├── reliability/
    ├── certification/
    └── characterization/
```

Tôi sẽ **loại `regression/` khỏi vai trò một tier riêng**. Regression là thuộc tính của test, không phải mức integration. Bug repository thì test nằm `component/storage/` + marker `regression`; bug API nằm `contracts/api/` + marker `regression`.

---

## Boundary rules phải enforce bằng code

| Tier           | Được phép                                     | Cấm                                     |
| -------------- | --------------------------------------------- | --------------------------------------- |
| `unit`         | domain objects, pure services, fakes          | DB, TestClient, HTTP, subprocess, sleep |
| `component`    | một production component + SQLite/local infra | API server, multi-process               |
| `contracts`    | FastAPI TestClient, CLI surface               | real external provider                  |
| `integration`  | nhiều production components                   | Internet thật                           |
| `e2e`          | API + Worker + DB + process                   | mock business flow quá mức              |
| `architecture` | AST/import/filesystem inspection              | business execution                      |
| `verification` | artifacts, receipts, certification            | trở thành nơi chứa unit test            |

Đây phải là **machine-enforced rule**, không chỉ convention.

Tạo:

```text
scripts/verification/check_test_architecture.py
```

Gate phải fail nếu chẳng hạn:

```text
tests/unit/** imports aiosqlite
tests/unit/** imports sqlalchemy
tests/unit/** imports TestClient
tests/unit/** imports subprocess
tests/unit/** uses time.sleep
tests/unit/** uses asyncio.sleep

tests/component/** starts uvicorn
tests/contracts/** performs external network
tests/** writes windagent.db outside tmp_path
tests/** calls sys.path.insert(...)
```

---

# Hard cutover nên thực hiện theo 7 phase

| Phase                             | Việc chính                                                  | Exit gate                                |
| --------------------------------- | ----------------------------------------------------------- | ---------------------------------------- |
| **T0 — Freeze baseline**          | lưu số test, test IDs, current verdict                      | baseline reproducible                    |
| **T1 — Foundation**               | support layer, conftest hierarchy, markers, hygiene checker | infrastructure PASS                      |
| **T2 — Unit purification**        | đẩy DB/HTTP/worker khỏi `unit/`                             | unit = pure 100%                         |
| **T3 — Component/Contract split** | storage/providers → component; API → contracts              | taxonomy PASS                            |
| **T4 — Integration/E2E split**    | process/multiprocess/full stack → e2e                       | isolation PASS                           |
| **T5 — Architecture cleanup**     | canonical/policy/boundary decomposition                     | no duplicate architecture responsibility |
| **T6 — Production CI**            | parallel pipeline + PG + Windows + coverage                 | production gates PASS                    |

Tôi sẽ làm **một branch refactor duy nhất**, nhưng commit từng phase để bisect được.

---

## T0 — Không được refactor trước khi freeze baseline

Trước tiên tạo manifest:

```text
artifacts/test-refactor/baseline/
├── collected_tests.txt
├── nodeids.txt
├── junit.xml
├── durations.json
├── environment.json
└── baseline_manifest.json
```

Phải lưu:

```text
collected count
passed
failed
skipped
xfail
top slow tests
platform
Python
SQLite
PostgreSQL version
commit SHA
```

Mục đích là tránh trường hợp refactor xong:

```text
1377 → 1320 tests
```

nhưng CI vẫn xanh vì 57 test biến mất.

---

# T1 — Fixture architecture

Không tạo một `tests/conftest.py` khổng lồ.

Root:

```text
tests/conftest.py
```

chỉ chứa fixture universal:

```text
temp environment
random deterministic IDs
test clock
common assertions
```

Sau đó:

```text
tests/component/conftest.py
    SQLite engine
    transaction
    repositories

tests/contracts/conftest.py
    TestClient
    demo profile
    API overrides

tests/integration/conftest.py
    production composition
    DB lifecycle

tests/e2e/conftest.py
    process lifecycle
    ports
    worker/API startup
```

Contract fixture hiện tại đã làm đúng một việc quan trọng: enable `WINDAGENT_PROFILE=demo` explicit và tạo DB trên `tmp_path`. Cần giữ semantics đó khi tái cấu trúc.

---

# T2 — Làm sạch `unit/` thật sự

Đây là thay đổi quan trọng nhất.

Ví dụ hiện tại:

```text
tests/unit/storage/test_storage_repositories.py
```

đang tạo `DatabaseManager`, tables, `SqlUnitOfWork` và repository SQL thật. Đây rõ ràng là component test.

Phải chuyển thành:

```text
tests/component/storage/test_storage_repositories.py
```

Tương tự:

```text
unit/storage/migrations/
→ component/migrations/

unit/providers/* route lock DB
→ component/providers/

unit/worker/* real persistence
→ component/worker/
```

Sau phase này, command:

```bash
uv run pytest tests/unit
```

phải có đặc tính:

```text
no database initialization
no TestClient startup
no subprocess
no network
no arbitrary wait
```

Mục tiêu runtime hợp lý:

```text
< 60–90 giây
```

trước xdist.

---

# T3 — API thành contract đúng nghĩa

Ví dụ:

```text
tests/unit/api/test_studio_v3_api.py
```

đang dùng `FastAPI TestClient`, dependency overrides và application service thật.

Nó phải về:

```text
tests/contracts/api/studio/test_studio_v3_api.py
```

Toàn bộ `tests/unit/api/` cần audit theo rule:

```text
TestClient / httpx against app
→ contracts

pure request mapper / validator
→ unit

DB + API + multiple services
→ integration
```

Không dùng directory name cũ để quyết định. Quyết định theo execution behavior.

---

# T4 — Integration và E2E phải tách

`test_phase14_two_process_e2e.py` hiện thực sự:

```text
launch uvicorn
launch Worker
shared durable DB
submit HTTP request
worker processes DAG
restart API
verify durability
```

Đây không còn là integration thông thường.

Nó nên chuyển thành:

```text
tests/e2e/multiprocess/test_api_worker_durability.py
```

Và toàn bộ process management:

```python
_free_port()
_wait_url()
_wait_exit()
Popen cleanup
```

đưa về:

```text
tests/support/process.py
tests/support/waiting.py
```

---

# T5 — Xử lý architecture tests

66 architecture file là tài sản tốt, nhưng hiện đang theo “phase history”.

Production codebase không nên phụ thuộc quá nhiều vào:

```text
phase4
phase7
phase13
phase16
```

vĩnh viễn.

Dần chuyển từ:

```text
test_architecture_v3_phase4.py
test_architecture_v3_phase7.py
```

sang invariant:

```text
test_domain_has_no_infrastructure_dependencies.py
test_storage_implements_declared_ports.py
test_api_depends_on_application_ports.py
test_worker_composition_is_authoritative.py
test_no_legacy_runtime_imports.py
test_provider_routing_has_single_authority.py
```

**Phase-based test là migration evidence.
Invariant-based test mới là production architecture.**

Canonical phase artifacts có thể chuyển sang:

```text
verification/characterization/
```

nếu chúng chỉ chứng minh roadmap cũ.

---

# T6 — CI production

CI hiện vẫn chạy:

```bash
pytest tests/architecture tests/unit tests/regression
```

trong một job timeout 1200 giây, trong khi Windows chỉ chạy `tests/unit`. Đây không phải pipeline cân bằng cho production.

Kiến trúc CI cuối cùng:

```text
PR
│
├── lint
├── architecture
├── unit
│
├── component-sqlite
├── contracts
├── integration-sqlite
│
├── postgres-production-semantics
├── windows-portability
│
└── final-evidence
```

Chạy song song khi có thể.

Release/nightly bổ sung:

```text
e2e-multiprocess
chaos
long-running worker
PostgreSQL concurrency
restart/recovery
golden production flow
```

---

## Marker production

Primary tier có thể suy ra từ directory. Marker chủ yếu dùng cho capability/modifier:

```toml
markers = [
    "postgres: requires real PostgreSQL semantics",
    "slow: intentionally expensive",
    "regression: fixed production defect",
    "multiprocess: starts OS processes",
    "windows_only: Windows behavior",
    "network: controlled network boundary",
]
```

Tôi **không cần marker `unit/component/contract/...` ở từng file** nếu folder đã là authority.

CI dùng:

```bash
pytest tests/unit
pytest tests/component
pytest tests/contracts
```

Còn cross-cut:

```bash
pytest -m postgres
pytest -m regression
```

Cách này ít duplicate metadata hơn.

---

# PostgreSQL phải là production authority

SQLite chỉ nên đóng vai:

```text
fast component validation
local persistence tests
developer feedback
```

Những semantics sau phải chứng minh trên PostgreSQL thật:

```text
CAS
row locking
lease/fencing
idempotency under concurrency
transaction isolation
outbox atomicity
multi-worker claim
unique constraint races
migration forward/backward
```

Hiện CI đã có PostgreSQL 16 service, nhưng vẫn chạy gần toàn bộ `tests/integration` rồi dùng `-k "fencing or replica..."`.

Production architecture nên dùng explicit marker:

```python
@pytest.mark.postgres
```

và:

```bash
pytest -m postgres
```

---

# Production acceptance gate

Tôi sẽ chỉ coi refactor hoàn thành khi đạt toàn bộ:

```text
TEST INVENTORY
1377+ test node IDs accounted for
0 unexplained test loss

UNIT
0 DB imports
0 TestClient
0 subprocess
0 real I/O
0 arbitrary sleep

ISOLATION
0 repo-root database writes
0 state leakage
xdist-safe where enabled

ARCHITECTURE
0 sys.path.insert
0 forbidden tier dependencies
0 duplicated composition setup

DATABASE
SQLite component PASS
PostgreSQL semantic suite PASS

PLATFORM
Ubuntu PASS
Windows PASS

FLAKINESS
3 consecutive full runs PASS
multiprocess/e2e bounded by deterministic timeouts

CI
fast gates <3 min target
full required pipeline <10–12 min wall time target

EVIDENCE
every required gate uploads receipt + JUnit
final-evidence validates every required job
```

Ngoài ra, `final-evidence` hiện cần được chỉnh vì `studio-roadmap-gates` nằm trong `needs` nhưng danh sách `--jobs` của validator không thấy nó được đưa vào cùng các required artifacts. Đây nên được xử lý như **P0 CI correctness** trước khi gọi pipeline là production-grade.

## Kết luận

Với mục tiêu của bạn, tôi chọn **full production refactor**, không giữ trạng thái trung gian lâu:

```text
Mixed tests
     ↓
Freeze baseline
     ↓
Build test infrastructure
     ↓
Purify unit
     ↓
Create component
     ↓
Normalize contracts
     ↓
Separate integration / e2e
     ↓
Convert phase gates → architecture invariants
     ↓
Production PostgreSQL + Windows CI
     ↓
Final evidence certification
```

Đây là hướng phù hợp hơn cho WindAgent hiện tại: giữ lại giá trị của 1.377 test, nhưng **thay toàn bộ cấu trúc tổ chức xung quanh chúng thành production architecture**, thay vì chỉ tối ưu tốc độ CI. 
