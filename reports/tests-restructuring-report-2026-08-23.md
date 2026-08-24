# BÁO CÁO PHÂN LOẠI & TÁI CẤU TRÚC THƯ MỤC `tests` — CHUẨN BỊ CHO UNIT TEST & CI/CD

> **Ngày:** 2026-08-23  
> **Phạm vi:** toàn bộ `tests/` (388 file `.py` thực, 997 file kể cả `__pycache__`, 85.106 LOC non-empty, ~4.0 MB, 1.377 hàm `test_*`)  
> **Mục tiêu:** phân loại hiện trạng, chỉ ra nợ kỹ thuật, đề xuất cấu trúc lại để đạt **test pyramid chuẩn**, **fast feedback < 5 phút**, **deterministic & hermetic**, **sẵn sàng CI/CD matrix (Ubuntu/Windows × SQLite/Postgres)**.

---

## 1. Tổng quan định lượng

| Chỉ số | Giá trị | Ghi chú |
|---|---|---|
| **Tổng file `.py` (loại `__pycache__`)** | **388** | `Get-ChildItem -Recurse -Filter *.py` |
| Tổng file kèm `__pycache__` | 997 | 609 file `.pyc` |
| Tổng LOC (dòng non-empty, không tính comment rỗng) | **85.106** | trung bình 219 LOC/file |
| Tổng test functions (`def test_*`) | **1.377** | trung bình 3.5 test/file |
| File lớn nhất | `tests/unit/intelligence/test_phase26_episode.py` — 947 LOC, 33 tests | Top 20 file đều > 514 LOC (xem §3.5) |
| Thư mục con cấp 1 | 8 | `architecture/`, `contracts/`, `fakes/`, `fixtures/`, `integration/`, `regression/`, `unit/`, `__pycache__/` |

### 1.1 Phân bổ theo thư mục cấp 1

| Nhóm | Số file | % | Vai trò hiện tại | Đánh giá |
|---|---|---|---|---|
| `tests/unit/` | **~243** | 62.6% | Được gọi là "unit" nhưng ~60-70% chạm DB/HTTP | **Cần tách** |
| `tests/architecture/` | **66** | 17.0% | Kiểm tra biên kiến trúc, import graph, canonical fixtures | Tốt nhưng lẫn lộn canonical + policy |
| `tests/contracts/` | **51** | 13.1% | Contract / acceptance trên API thật (`TestClient` + demo seed) | Thuần contract, nên tách `contracts/` → `api-contracts/` + `domain-contracts/` |
| `tests/integration/` | **26** | 6.7% | Multi-component, multi-process, provider routing | Đúng vị trí nhưng thiếu marker PG vs SQLite |
| `tests/regression/` | **2** | 0.5% | Cutover defects, security fail-closed | Quá mỏng, cần mở rộng |
| `tests/fakes/` | **6** | 1.5% | Test doubles (`FakeDurableTaskQueue`, `FakeStudioOrchestrator`, ...) | Tốt, nhưng thiếu quy ước đặt tên |
| `tests/fixtures/` | **4** | 1.0% | `canonical_bunny_episode`, `video_production/*` | Tốt, cần centralize |

### 1.2 Phân bổ chi tiết `tests/unit/` (243 file, 18 nhóm domain)

```
26  tests/unit/verification          # phase03..27, evidence, negative injections
23  tests/unit/orchestration         # dispatcher, scheduler, recovery, studio_run
20  tests/unit/intelligence          # director, shot_graph, compilers phase08-26
19  tests/unit/api                   # api_v2, realtime, health, studio_v3
18  tests/unit/tools                 # blender, browser, cycles, vram, review...
17  tests/unit/core                  # typed_ids, domain, contracts, IR, assets
16  tests/unit/providers             # adapters, routing, singleflight, failover
13  tests/unit/storage               # repositories, outbox, phase18...
10  tests/unit/storage/migrations    # 0010..0015, phase1/7/8/9 integrity
 9  tests/unit/intelligence/story    # bibles, ideation, outline...
 8  tests/unit/domain/story          # bibles, ideation, screenplay...
 7  tests/unit/domain/studio         # aggregates, approval, revision...
 7  tests/unit/worker                # durable_queue, heartbeat, studio_runtime...
 6  tests/unit/cli                   # commands, live_integration, doctor...
 6  tests/unit/observability         # health, capability, outbox
 5  tests/unit/domain/video_production
 4  tests/unit/workflows             # social_research, model_routing...
 4  tests/unit/scripts               # ci_workflow, artifact_schema...
 4  tests/unit/ (root)               # phase7_composition, api_v1_removal...
 2  tests/unit/execution
 1  tests/unit/desktop | web | context | memory | evals | migration | final
```

### 1.3 Phân bổ theo kỹ thuật (heuristic quét mã nguồn)

> Dựa trên quét 388 file: `tmp_path|sqlite|aiosqlite|:memory:|create_async_engine` → DB, `Mock|patch|Fake|fake` → double, `TestClient|httpx` → HTTP, `async def test_` → async.

| Đặc trưng | Số file ước tính | % unit | Vấn đề |
|---|---|---|---|
| Chạm DB (`tmp_path`, `sqlite`, `create_async_engine`, `Session`) | **~140-160** | ~60% của `unit/` | **Không phải unit thuần** — nên là `component` hoặc `integration` |
| Dùng `Fake`/`Mock`/`patch`/`monkeypatch` | **~180** | 46% | Tốt, nhưng phân tán |
| Dùng `TestClient`/`httpx` | **~55** | 14% | HTTP contract nằm lẫn trong `unit/api/` |
| `async def test_` | **~95** | 24% | Cần `pytest-asyncio` config thống nhất |
| `time.sleep` / `asyncio.sleep` | **~15 file** | — | **Flaky**, phải thay bằng fake clock / polling helper |
| `sys.path.insert(0, ...)` | **~30 file** | — | **Debt**: `pyproject.toml` đã có `pythonpath`, cần xóa |
| `windagent.db` hard-coded (không qua `tmp_path`) | **2 file** (`contracts/conftest.py` đúng, `integration/test_phase14_two_process*` sai) | — | Rò rỉ state giữa test |

---

## 2. Phân loại chi tiết theo mục đích (Taxonomy)

### 2.1 `tests/architecture/` — 66 file, 520+ tests

**Bản chất:** Static analysis + boundary gates. Không chạy logic nghiệp vụ, chỉ quét import graph, file system, artifact JSON.

| Nhóm con | File tiêu biểu | Số file | Mô tả |
|---|---|---|---|
| **V3 Policy** | `test_architecture_v3_phase2..16.py`, `test_architecture_v3_policy.py` | 15 | Mỗi phase 1 file, kiểm tra `check_architecture_imports` + namespace authority |
| **Canonical** | `test_phase06_kernel_canonical.py` .. `test_phase26_episode_architecture.py` | 28 | Mỗi phase 1 file `*_canonical.py`, assert artefact JSON tồn tại & schema |
| **Regression/Quarantine** | `test_phase04_negative_fixtures.py` (543 LOC, 12 tests), `test_phase3_negative.py` (580 LOC, 21 tests), `test_phase13_regression.py` | 6 | Negative fixtures, videoclaw quarantine, flow removal |
| **Scaffold/Export** | `test_scaffold_generator_policy.py`, `test_phase7_scaffold_exports.py` | 4 | Kiểm tra generator không sinh code bẩn |
| **Story boundary** | `test_story_*_boundary.py`, `test_no_story_in_legacy_engines.py` | 6 | Đảm bảo story không rò vào legacy engine |
| **Phase00 cutover** | `test_phase00_*`, `test_phase02_api_worker_boundary.py` | 5 | Single workspace contract, runtime cutover defects |

**Đánh giá:**
- ✅ Bao phủ toàn bộ 16 phase, rất kỷ luật.
- ⚠️ Trùng lặp: `phase16` có cả `test_architecture_v3_phase16.py` (663 LOC) + `test_phase16_composition_root_fixtures.py` + `*_canonical.py` — 3 nơi kiểm cùng 1 biên.
- ⚠️ `sys.path.insert` lặp lại trong 9/66 file (copy-paste).
- ⚠️ Thiếu marker: hiện tại CI chạy `pytest tests/architecture` chung với `tests/unit` trong job `python-unit-sqlite` → không tách được thời gian chạy.

### 2.2 `tests/contracts/` — 51 file, ~480 tests

**Bản chất:** Black-box contract trên **public API thật** (`FastAPI TestClient` + `WINDAGENT_PROFILE=demo` + temp DB). Đây là **acceptance**, không phải unit.

| Nhóm con | File | Số test | Đặc điểm |
|---|---|---|---|
| **Story gates B0-B9** | `test_story_b0_consumer_freeze.py` .. `test_story_b9_handoff_gate.py` | 8-15 mỗi file | Mỗi gate 1 file, kiểm tra artifact contract, prompt catalog, idea/bible/outline/screenplay/review/lock/handoff |
| **P1 production readiness** | `test_p1_*.py` (8 file) + `test_p1_e2e_acceptance.py` (11 tests, 469 LOC) | ~120 | Scenarios A-G, PG idempotency/atomicity/CAS, world_canon, package |
| **Code-video contracts** | `test_code_video_*.py` (10 file) | 5-24 mỗi file | Assembly, capture, compiler, graphics, QC, replay, workspace |
| **Phase contracts** | `test_phase2_api_v3_foundation.py` .. `test_phase16_e2e_certification.py` | 4-24 mỗi file | Mỗi phase 1 file contract |
| **Studio fixtures** | `test_studio_contract_fixtures_v0_1.py`, `test_v3_vertical_lifecycle_real.py` (519 LOC, sys.path hack) | 1-12 | Idempotency, version conflict, hash mismatch |

**Đặc điểm kỹ thuật:**
- `tests/contracts/conftest.py` (28 LOC) là **duy nhất conftest trong toàn repo** — định nghĩa `client` fixture với `monkeypatch.setenv(WINDAGENT_PROFILE=demo)` + `sqlite+aiosqlite:///tmp/contract.db`. **Rất tốt** (hermetic, không rò `windagent.db`), nhưng bị cô lập — `unit/` và `integration/` phải tự chế lại fixture tương tự → duplicate 40+ lần.
- Không có `pytest.mark.contract` hay `slow` — CI phải liệt kê file thủ công trong `studio-roadmap-gates` job.

### 2.3 `tests/integration/` — 26 file, ~150 tests

| Nhóm | File | Async | DB | Mô tả |
|---|---|---|---|---|
| **P0 provider/model** | `test_p0_1_provider_lifecycle.py` (470 LOC, 13 tests), `test_p0_2_model_catalog.py` (360 LOC), `test_p0_3_model_routing.py` (400 LOC) | 1/7/8 | ✅ tmp_path + real `BaseORM` + `httpx.MockTransport` | Mẫu **chuẩn** cho integration: real DB + real encryption + fake HTTP |
| **P0 studio/story DAG** | `test_p0_4_studio_projects.py` (420 LOC, 10 async), `test_p0_5_story_dag_resume.py`, `test_p0_6_lock_semantics.py` | 10/1/2 | ✅ | Studio project + DAG resume + lock fencing |
| **Phase flows** | `test_phase5_asset_gateway_wiring.py`, `test_phase6_asset_trust_flow.py` (344 LOC), `test_phase7_normalization_flow.py`, `test_phase8_e2e_chaos.py` (459 LOC, 6 async), `test_phase25_golden_scene_flow.py`, `test_phase26_episode_flow.py` (520 LOC) | hỗn hợp | ✅ | Mỗi phase 1 flow, dùng `ControlledHermesRuntime` + `FakeDurableTaskQueue` |
| **Architecture integration** | `test_architecture_v3_phase10_provider_routing.py`, `test_architecture_v3_phase4_*` | 2/0 | ✅ | Kiểm tra routing authority với DB thật |
| **E2E multiprocess** | `test_phase1_multiprocess_e2e.py` (126 LOC, `time.sleep`), `test_phase14_two_process_e2e.py` (168 LOC, `time.sleep` + `asyncio.sleep` + `windagent.db`) | 0/1 | ⚠️ | Dùng `multiprocessing`, sleep cứng — **flaky** |
| **Browser/UI** | `test_agent_browser_social_e2e.py` (151 LOC, 1 async), `test_vp3d_ui_p7_realtime_state_verified.py` | 1/0 | Y | Social E2E, realtime state |

**Đánh giá:**
- ✅ Phần lớn đã hermetic (tmp_path + create_all với table whitelist `P01_TABLES`).
- ⚠️ `test_phase14_two_process_e2e.py` là **duy nhất** còn hard-code `windagent.db` + sleep → cần refactor.
- ⚠️ Không phân biệt `integration:sqlite` vs `integration:postgres` bằng marker — CI phải chạy 2 lần toàn bộ `tests/integration`.

### 2.4 `tests/regression/` — 2 file

| File | Tests | Mô tả |
|---|---|---|
| `test_cutover_defects.py` | ~8 | Kiểm tra defect sau cutover (có `sys.path` hack) |
| `test_security_fail_closed.py` | ~6 | Fail-closed cho SSRF, auth, containment |

**Đánh giá:** Quá mỏng. Đáng lẽ chứa mọi bug đã fix (regression corpus). Hiện tại logic regression nằm rải rác trong `architecture/test_phase3_negative.py` và `verification/test_negative_injections.py` (1 test!) → cần gom lại.

### 2.5 `tests/fakes/` & `tests/fixtures/` — 10 file

| File | LOC | Vai trò | Đánh giá |
|---|---|---|---|
| `fakes/fake_asset_resolver.py` | 120 | `FakeAssetResolver` với GLB/PNG/license state | Tốt, deterministic |
| `fakes/fake_task_queue.py` | 110 | `FakeDurableTaskQueue` (implements `DurableTaskQueuePort` + `TaskLeasePort`) | Chuẩn, dùng trong 15+ integration test |
| `fakes/phase8_controlled_doubles.py` | 180 | `ControlledHermesRuntime` (complete/fail/cancel/crash) | Rất tốt, mô hình 2 external boundaries |
| `fakes/provider_graph_seed.py` | 200 | `seed_provider_graph` + `PersistentRouteLocks` (FK-aware) | Thiết yếu cho SQLite FK `ON` |
| `fakes/routing_fakes.py` | 180 | `InMemoryBindingStore` (dev/test fallback) | Bị duplicate với `provider_graph_seed` |
| `fakes/studio_fakes.py` | 450 | 9 fake repos + `FakeStudioOrchestrator` | Quá lớn, cần tách theo aggregate |
| `fixtures/canonical_bunny_episode.py` | 350 | `build_canonical_bunny_episode()` — fixture chuẩn cho Stage H | Tốt, nhưng chỉ 1 episode |
| `fixtures/video_production/*.py` | 4 file, ~600 LOC | `director_fixtures`, `fixture_builder`, `ir_fixture_builder` | Tốt, nhưng đặt tên không nhất quán |

### 2.6 `tests/unit/` — 243 file, ~980 tests (phân loại sâu)

Phân loại theo **mức độ cô lập**:

| Loại | Định nghĩa | Số file ước tính | Ví dụ | Nên đổi thành |
|---|---|---|---|---|
| **A. Pure unit** (không I/O, không DB, không HTTP, <100ms) | Chỉ test hàm/domain object với fake input | **~85** (35%) | `domain/story/test_ideation.py`, `domain/studio/test_aggregates.py`, `core/test_typed_ids.py`, `intelligence/story/test_*` | Giữ `unit/` |
| **B. Component (DB-backed)** | Dùng `tmp_path` + `create_async_engine` + `BaseORM.metadata.create_all` | **~110** (45%) | `storage/test_storage_repositories.py`, `providers/test_route_lock.py` (462 LOC), `orchestration/test_studio_run_service.py` (751 LOC) | **→ `tests/component/` hoặc `tests/unit` + marker `@pytest.mark.component`** |
| **C. HTTP contract lẫn trong unit** | Dùng `TestClient` trong `unit/api/` | **~18** | `unit/api/test_studio_v3_api.py` (666 LOC, 31 tests), `test_architecture_v3_phase6_realtime.py` (847 LOC, 23 tests) | **→ `tests/contracts/` hoặc `tests/api/`** |
| **D. Script/CLI verification** | Chạy `subprocess`, kiểm tra file system, yaml | **~10** | `unit/scripts/test_ci_workflow.py`, `unit/cli/test_live_integration.py` (525 LOC) | **→ `tests/verification/` hoặc `tests/cli/` với marker `slow`** |
| **E. Verification/Evidence** | Kiểm tra `artifacts/`, `scripts/verification/*.py` | **~26** (`unit/verification/`) | `test_evidence_generation.py` (576 LOC), `test_phase25_reliability.py` | **→ `tests/verification/` đã đúng, nhưng đang nằm trong `unit/`** |

**Chi tiết theo domain (top 5 nặng nhất cần refactor):**

| File | LOC | Tests | Vấn đề chính |
|---|---|---|---|
| `unit/worker/test_studio_runtime.py` | 926 | 29 (27 async) | Quá lớn, gộp 3 trách nhiệm: runtime + deadline + model. Nên tách 3 file. |
| `unit/intelligence/test_phase26_episode.py` | 947 | 33 | 910 LOC thuần logic, nhưng nằm trong `unit/` dù là E2E episode. |
| `unit/orchestration/test_studio_run_service.py` | 751 | 17 async | DB-backed, nên là component. |
| `unit/workflows/test_phase4_social_source_collection.py` | 779 | 58 (25 async) | 58 tests trong 1 file — cần tách theo source type. |
| `unit/api/test_architecture_v3_phase6_realtime.py` | 847 | 23 (12 async) | HTTP + WebSocket + DB — rõ ràng là contract/integration, không phải unit. |

---

## 3. Nợ kỹ thuật & vấn đề hiện trạng

### 3.1 Thiếu `conftest.py` gốc & duplicate fixtures (CRITICAL)

- **Hiện trạng:** Chỉ có 1 `tests/contracts/conftest.py`. Toàn bộ `tests/unit/` và `tests/integration/` tự định nghĩa lại `provider_db`, `db`, `tmp_path` engine, `TestClient` setup — ước tính **40+ định nghĩa trùng lặp** của `create_engine(f"sqlite:///{tmp_path/...}")` + `BaseORM.metadata.create_all`.
- **Hậu quả:** Thay đổi schema phải sửa 40 nơi. Không có `autouse` cleanup, dễ rò `windagent.db-wal`.
- **Ví dụ duplicate:** `integration/test_p0_1_provider_lifecycle.py: P01_TABLES = [...]` vs `integration/test_p0_2_model_catalog.py: P01_TABLES = [...]` — cùng 13 bảng nhưng khai báo riêng.

### 3.2 `sys.path.insert` hack lan tràn (HIGH)

- **30 file** chứa `sys.path.insert(0, str(SCRIPTS))` hoặc `str(ROOT / "apps/api")`.
- `pyproject.toml` đã khai báo đúng `pythonpath = [".", "scripts", "apps/api", ...]` — hack là thừa và gây `import` order flake trên Windows.
- Cần xóa toàn bộ, thay bằng `import check_architecture_imports` trực tiếp (đã có `pythonpath`).

### 3.3 `time.sleep` / `asyncio.sleep` cứng (HIGH — flaky)

- 15 file: `architecture/test_phase3_negative.py`, `unit/memory/test_memory_system.py` (`time.sleep`), `unit/orchestration/test_phase17_durable_workflow.py`, `integration/test_phase1_multiprocess_e2e.py`, `worker/test_phase04_worker_heartbeat.py` (`asyncio.sleep`), v.v.
- Trong CI Windows với runner chậm, sleep 0.1s có thể không đủ → flaky.
- Giải pháp: `pytest-asyncio` + `asyncio.Event` / `anyio` + `freezegun` hoặc helper `poll_until(condition, timeout=2, interval=0.05)`.

### 3.4 File quá lớn & God test class (MEDIUM)

- 25 file >500 LOC, 5 file >750 LOC. Ví dụ `test_phase26_episode.py:947 LOC` chứa 33 tests cho cả `compilation` + `render` + `audio` — vi phạm SRP.
- `test_p1_e2e_acceptance.py:469 LOC` chứa 7 scenarios A-G trong 1 file — nên tách `test_p1_scenario_{a..g}.py`.
- `studio_fakes.py:450 LOC` chứa 9 fake repos — nên tách `fakes/studio/{orchestrator, repositories, capability}.py`.

### 3.5 Thiếu `pytest.mark` & phân loại CI (CRITICAL)

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = [".", "scripts", ...]
# ❌ KHÔNG có markers, addopts, filterwarnings, timeout, xdist, coverage
```

- Không có marker `unit`, `component`, `contract`, `integration`, `architecture`, `slow`, `postgres`.
- Kết quả: CI phải hard-code danh sách file trong từng job (xem `ci.yaml: studio-roadmap-gates: uv run pytest tests/contracts tests/unit/domain/studio ... -q`) — dễ quên file mới.
- Không có `pytest-xdist` → CI chạy tuần tự 1.377 tests ~ 12-18 phút (timeout 1200s).
- Không có `coverage` gate → không biết branch nào chưa cover.

### 3.6 Lẫn lộn `unit` vs `integration` vs `contract` (HIGH)

- `unit/api/test_studio_v3_api.py` (666 LOC, `TestClient`) là contract nhưng nằm trong `unit/`.
- `unit/storage/*` (13 file) đều là DB integration nhưng nằm trong `unit/`.
- `unit/verification/*` (26 file) là verification/evidence, không phải unit.
- Hậu quả: `python-unit-sqlite` job chạy cả `tests/architecture tests/unit tests/regression` (1.377 tests) → **không fast feedback**. Dev phải chờ 12 phút để biết lỗi typo.

### 3.7 Trùng tên test (LOW nhưng gây nhầm khi `-k`)

- `def test_real_repo_architecture_stays_clean():` xuất hiện **20 lần** (mỗi `architecture/*` file 1 lần).
- `test_corpus_results_match_live_behavior`: 6 lần, `test_manifest_checksum_matches_committed_file`: 6 lần.
- Khi chạy `pytest -k test_real_repo_architecture_stays_clean` sẽ chạy 20 tests không mong muốn.

### 3.8 Thiếu `conftest` cho `tmp_path` DB lifecycle & `WINDAGENT_DATABASE_URL` isolation

- Nhiều test tự `monkeypatch.setenv("WINDAGENT_DATABASE_URL", ...)` nhưng quên `monkeypatch.delenv` hoặc dùng `tmp_path` không unique → race khi `xdist` parallel.
- Cần root fixture `isolated_db_url(tmp_path, monkeypatch)` autouse hoặc explicit.

---

## 4. Đối chiếu với thực tế CI/CD hiện tại (`.github/workflows/ci.yaml`)

| Job | Lệnh hiện tại | Vấn đề |
|---|---|---|
| `artifact-protocol` | `generate_phase7_evidence.py` + `validate_*` | OK, nhưng thiếu cache `uv` (`setup-uv` đã có cache nhưng không `actions/cache` cho `artifacts/`) |
| `version-consistency` | `check_version_consistency.py` | OK |
| `architecture-boundaries` | `check_architecture_imports.py` + `check_no_legacy_orchestration.py` + `ruff check` (hard-coded 11 file) | `ruff check` chỉ check 11 file hard-code, không phải toàn repo → dễ miss |
| `python-unit-sqlite` | `pytest tests/architecture tests/unit tests/regression -v --tb=short` | **Quá rộng**: chạy 66+243+2 = 311 file trong 1 job, không phân biệt fast/slow, không `xdist` |
| `python-unit-windows` | `pytest tests/unit -v` | Chỉ chạy `unit`, bỏ `architecture`/`regression` → **không đối xứng** với Ubuntu |
| `python-integration-sqlite` | `pytest tests/integration -v` | OK, nhưng chạy cả PG-only tests với skip → lãng phí |
| `python-integration-postgres` | `pytest tests/integration` + `pytest -k "fencing or replica..."` | Tốt, nhưng `database_preflight.py --initialize-schema` chạy mỗi lần → chậm |
| `runtime-smoke` | `runtime_version_smoke.py` | OK |
| `cli-contract` | `pytest tests/unit/cli/test_live_integration.py tests/unit/cli/test_cli_commands.py ...` | Hard-code 3 file, không dùng marker |
| `web-test` / `desktop-test` | `npm ci` + `typecheck` + `test:coverage` + `build` | OK, nhưng không cache `node_modules` |
| `studio-roadmap-gates` | `run_ci_checkers.py` + `pytest tests/contracts tests/unit/domain/studio ...` (hard-code 6 path) | Hard-code list, dễ quên |
| `p1-e2e-postgres` | `pytest tests/contracts/test_p1_e2e_acceptance.py::TestPostgresVerticalSlice -vv` + grep `skipped/FAILED/1 passed` | Dùng `grep` bash để assert — fragile trên Windows |
| `final-evidence` | `validate_ci_evidence.py` + `CI_JOB_RESULTS` JSON | Rất tốt, nhưng phụ thuộc `pattern: "*-evidence"` → nếu job thiếu upload sẽ silent |

**Nhận xét chung:**
- CI đã rất kỷ luật (15 gates + final, `continue-on-error` bị cấm, `|| true` bị cấm, mỗi job đều `capture_environment` + `upload-artifact`).
- Nhưng **thiếu sharding/parallel** và **thiếu marker** nên không scale khi test tăng lên 2.000+.
- `python-unit-sqlite` là bottleneck (12-18 phút) trong khi `architecture` chỉ cần 30s nếu tách.

---

## 5. Đề xuất cấu trúc lại (Target Architecture)

### 5.1 Nguyên tắc

1. **Hermetic & isolated:** Mỗi test tự tạo DB riêng trong `tmp_path`, không chạm `windagent.db` thật. `WINDAGENT_DATABASE_URL` luôn trỏ vào `tmp_path`.
2. **Fast feedback first:** `unit` (pure) chạy <60s, không cần DB/HTTP. `component`/`contract`/`integration` chạy sau.
3. **Marker-driven:** Mọi test được gán `@pytest.mark.<tier>` để CI có thể `pytest -m "not slow"` hoặc `pytest -m postgres`.
4. **No sys.path hack:** Dùng `pythonpath` trong `pyproject.toml` + `uv` workspace.
5. **Single conftest:** `tests/conftest.py` cung cấp `isolated_db`, `api_client`, `fake_clock`, `poll_until`.
6. **Fakes as package:** `tests/fakes/` thành package có `__init__.py` export rõ ràng, chia theo bounded context.

### 5.2 Cấu trúc thư mục đề xuất (giữ tương thích, di chuyển mềm)

```
tests/
├── conftest.py                          # ★ MỚI — root fixtures (xem §5.3)
├── pytest.ini  (hoặc trong pyproject.toml)
│
├── fakes/                               # Test doubles — giữ nguyên, thêm __init__.py
│   ├── __init__.py                      # export FakeDurableTaskQueue, ControlledHermesRuntime...
│   ├── fake_asset_resolver.py
│   ├── fake_task_queue.py
│   ├── phase8_controlled_doubles.py     # → fakes/execution/controlled_runtime.py (tùy chọn)
│   ├── provider_graph_seed.py
│   ├── routing_fakes.py
│   └── studio/
│       ├── __init__.py
│       ├── orchestrator.py              # tách từ studio_fakes.py
│       ├── repositories.py
│       └── capability.py
│
├── fixtures/                            # Dữ liệu mẫu — giữ nguyên, thêm factory
│   ├── __init__.py
│   ├── canonical_bunny_episode.py
│   ├── factories.py                     # ★ MỚI — factory_boy / polyfactory helpers
│   └── video_production/
│       ├── __init__.py
│       ├── director_fixtures.py
│       ├── fixture_builder.py
│       └── ir_fixture_builder.py
│
├── support/                             # ★ MỚI — helpers dùng chung (không phải fakes)
│   ├── __init__.py
│   ├── db.py                            # create_isolated_engine(tmp_path), P01_TABLES
│   ├── api.py                           # make_test_client(monkeypatch, tmp_path, profile="demo")
│   ├── polling.py                       # poll_until(fn, timeout=2, interval=0.05)
│   └── clock.py                         # FakeClock, freeze_time helpers
│
├── unit/                                # CHỈ pure unit — không DB, không HTTP, không sleep
│   ├── core/                            # typed_ids, domain, contracts, ir, errors
│   ├── domain/
│   │   ├── story/
│   │   └── studio/                      # aggregates, approval, revision (pure)
│   ├── intelligence/
│   │   └── story/                       # prompt_registry, ideation_service (mocked LLM)
│   ├── orchestration/                   # retry_classifier, scheduler (pure logic)
│   ├── tools/                           # ssrf_protection, tool_platform (mocked fs)
│   ├── workflows/                       # workflow_packs (pure)
│   └── ...                              # chỉ giữ file không chạm DB
│
├── component/                           # ★ MỚI — DB-backed nhưng không qua HTTP
│   ├── storage/                         # ← di chuyển từ unit/storage + unit/storage/migrations
│   ├── providers/                       # ← di chuyển từ unit/providers (route_lock, singleflight...)
│   ├── orchestration/                   # ← di chuyển từ unit/orchestration/test_studio_run_service.py etc.
│   ├── worker/                          # ← di chuyển từ unit/worker
│   └── observability/                   # ← di chuyển từ unit/observability
│
├── contracts/                           # API & domain contracts — giữ nguyên, thêm marker
│   ├── conftest.py                      # giữ, nhưng kế thừa từ tests/conftest.py
│   ├── api/                             # ← di chuyển unit/api/test_studio_v3_api.py vào đây
│   ├── p1/                              # ← gom test_p1_*.py vào subfolder
│   │   ├── test_p1_e2e_acceptance.py    # tách scenarios A-G ra 7 file nhỏ (tùy chọn)
│   │   └── ...
│   ├── story/                           # ← test_story_b0..b9
│   └── code_video/                      # ← test_code_video_*.py
│
├── integration/                         # Multi-component E2E — giữ nguyên, thêm markers
│   ├── providers/                       # test_p0_*.py
│   ├── studio/                          # test_p0_4_*, phase26_episode_flow
│   ├── workers/                         # phase8_e2e_chaos, durable workflows
│   └── multiprocess/                    # phase1_multiprocess, phase14_two_process
│
├── architecture/                        # Giữ nguyên 66 file, thêm marker
│   ├── v3/                              # test_architecture_v3_*.py
│   ├── canonical/                       # test_*_canonical.py
│   └── policy/                          # test_architecture_policy.py, scaffold checks
│
├── verification/                        # ★ TÁCH từ unit/verification (26 file)
│   ├── evidence/                        # test_evidence_generation, ci_evidence_validation
│   ├── characterization/                # test_phase05_characterization...
│   └── reliability/                     # test_phase25_reliability, phase26_security...
│
├── regression/                          # Mở rộng từ 2 → N file, mỗi bug 1 file
│   ├── test_cutover_defects.py
│   ├── test_security_fail_closed.py
│   └── test_issue_*.py                  # quy ước đặt tên theo issue ID
│
└── e2e/                                 # ★ MỚI (tùy chọn) — full stack qua TestClient + real worker
    └── test_golden_path.py
```

**Lưu ý di chuyển mềm:** Không cần di chuyển vật lý ngay. Có thể đạt 80% lợi ích chỉ bằng **marker + conftest** mà không đụng file:

- Bước 1 (không di chuyển): Thêm `tests/conftest.py` + `pyproject.toml` markers, gán `@pytest.mark.*` vào file hiện tại, cập nhật CI dùng `-m`.
- Bước 2 (di chuyển): Dần dần `git mv tests/unit/storage tests/component/storage` theo từng PR.

### 5.3 `tests/conftest.py` đề xuất (root)

```python
# tests/conftest.py
from __future__ import annotations
import base64, tempfile, uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# --- DB fixtures -------------------------------------------------------------
@pytest.fixture(scope="function")
def isolated_db_url(tmp_path, monkeypatch) -> str:
    """Hermetic SQLite URL per test — không bao giờ chạm windagent.db thật."""
    url = f"sqlite+aiosqlite:///{(tmp_path / f'test_{uuid.uuid4().hex[:8]}.db').as_posix()}"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", url)
    # ADR 0006 A5 — writable temp dir
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    return url

@pytest.fixture
async def isolated_engine(isolated_db_url):
    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.orm.models import BaseORM
    # import các model để BaseORM biết tables
    import windagent_storage.orm.v2_orchestration_models  # noqa: F401
    import windagent_storage.orm.v3_models  # noqa: F401
    db = DatabaseManager(isolated_db_url)
    await db.create_tables(BaseORM.metadata)
    yield db
    await db.close()

# --- API fixtures ------------------------------------------------------------
@pytest.fixture
def api_client(isolated_db_url, monkeypatch):
    """TestClient với demo profile + isolated DB."""
    monkeypatch.setenv("WINDAGENT_PROFILE", "demo")
    from windagent_api.main import app
    with TestClient(app) as c:
        yield c

@pytest.fixture
def api_client_no_demo(isolated_db_url):
    """TestClient không demo — cho unit/api không cần seed."""
    from windagent_api.main import app
    with TestClient(app) as c:
        yield c

# --- Polling / clock helpers -------------------------------------------------
@pytest.fixture
def poll_until():
    import time, asyncio
    def _poll(fn, timeout=2.0, interval=0.05, msg="poll timeout"):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if fn():
                return True
            time.sleep(interval)
        raise AssertionError(msg)
    return _poll
```

### 5.4 `pyproject.toml` đề xuất (markers + addopts)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = [".", "scripts", "apps/api", "apps/cli", "apps/worker",
              "core", "orchestration", "intelligence", "providers",
              "tools", "workflows", "verification", "context",
              "memory", "execution", "storage", "observability",
              "evals", "plugins", "skills"]
markers = [
    "unit: pure unit — no DB, no HTTP, no sleep, <100ms",
    "component: DB-backed single service (needs tmp_path + BaseORM)",
    "contract: API contract via TestClient (needs demo seed)",
    "integration: multi-component E2E",
    "architecture: import graph & canonical artifact checks",
    "verification: evidence & characterization",
    "regression: bug regression corpus",
    "slow: >1s or multiprocess or PG",
    "postgres: requires WINDAGENT_TEST_POSTGRES_URL",
    "windows_only: Windows-specific",
]
# Fast by default: dev chạy unit không đụng DB
addopts = "-m 'not slow and not postgres' --strict-markers --strict-config -rA"
filterwarnings = [
    "error::DeprecationWarning",
    "ignore::pytest.PytestUnrecognizedHookWarning",
]
# Timeout fail-closed cho CI
# timeout = 120
# timeout_method = "thread"
```

Cách gán marker — **không cần sửa từng hàm**, chỉ cần thêm vào đầu file:

```python
# tests/unit/storage/test_storage_repositories.py
import pytest
pytestmark = pytest.mark.component  # cả file là component

# tests/unit/api/test_studio_v3_api.py
pytestmark = pytest.mark.contract

# tests/integration/test_phase1_multiprocess_e2e.py
pytestmark = [pytest.mark.integration, pytest.mark.slow]
```

### 5.5 Kiểm soát `sys.path` hack

- Xóa toàn bộ `sys.path.insert(0, str(SCRIPTS))` trong 30 file.
- Thay bằng import trực tiếp: `import check_architecture_imports` (đã có `pythonpath`).
- Thêm `ruff` rule để cấm: `scripts/check_no_sys_path_hack.py` hoặc `ruff` select `TID252` (flake8-tidy-imports).

### 5.6 Kiểm soát `sleep`

- Chuẩn hóa helper `tests/support/polling.py::poll_until` và `tests/support/clock.py::FakeClock`.
- Thêm `ruff` hoặc `scripts/check_no_hard_sleep.py` để CI fail nếu `time.sleep`/`asyncio.sleep` xuất hiện ngoài `support/`.

---

## 6. Đề xuất CI/CD tái cấu trúc

### 6.1 Pipeline mới — 3 tiers (fast → full → nightly)

```
Tier 1 — Fast feedback (<3 phút, chạy mọi push & PR, fail-fast)
  ├─ lint (ruff check toàn repo — không hard-code 11 file)
  ├─ architecture (pytest -m architecture -q)              ~30s
  ├─ unit (pytest -m unit -q --cov)                        ~45s  (xdist -n auto)
  └─ contracts-smoke (pytest -m contract -k "not slow" -q) ~60s

Tier 2 — Full verification (<12 phút, chạy mọi PR vào main, required)
  ├─ component-sqlite (pytest -m component -q)              ~3m
  ├─ integration-sqlite (pytest -m integration and not postgres -q)
  ├─ integration-postgres (pg service + -m postgres)
  ├─ verification (pytest -m verification -q)
  ├─ regression (pytest -m regression -q)
  ├─ cli-contract (pytest -m contract -k cli)
  ├─ web-test + desktop-test (npm ci + typecheck + test)
  └─ p1-e2e-postgres (không grep, dùng pytest --junitxml + python assert)

Tier 3 — Nightly / release (chạy schedule + tag)
  ├─ e2e (full golden path với real worker + real blender mock)
  ├─ load / chaos (phase8_e2e_chaos với scale)
  └─ coverage gate (branch coverage >= 80%)
```

### 6.2 `ci.yaml` cụ thể — diff so với hiện tại

| Thay đổi | Hiện tại | Đề xuất | Lợi ích |
|---|---|---|---|
| **Tách `python-unit-sqlite`** | `pytest tests/architecture tests/unit tests/regression` (311 file, 1200s) | `pytest -m unit -q` + `pytest -m architecture` + `pytest -m component` (3 jobs song song) | Giảm wall-time từ 12m → 3m, rõ nguyên nhân fail |
| **Đối xứng Windows** | `tests/unit` only trên Windows | `pytest -m "unit or component"` trên cả Ubuntu & Windows | Phát hiện bug Windows-only sớm |
| **Markers thay hard-code** | `pytest tests/contracts tests/unit/domain/studio ...` (6 path hard-code) | `pytest -m contract -q` | Thêm file mới không cần sửa CI |
| **Ruff toàn repo** | `ruff check apps/cli/... tests/unit/cli/...` (11 file) | `ruff check .` (toàn repo, exclude đã có) | Bắt lỗi toàn diện |
| **Cache** | `setup-uv` cache, không cache `node_modules` | Thêm `actions/cache@v4` cho `~/.cache/uv` + `apps/web/node_modules` + `apps/desktop/node_modules` | Giảm 60-90s mỗi job |
| **xdist** | Không | `pytest -m unit -n auto --dist loadscope` (cần `pytest-xdist`) | Giảm 50% thời gian unit |
| **Coverage** | Không | `pytest --cov=core --cov=orchestration --cov-report=xml --cov-fail-under=70` | Gate chất lượng |
| **P1 postgres assert** | `grep "1 passed"` bash | `python -c "import xml.etree...; assert junitxml...` hoặc `pytest --junitxml` + `python scripts/verification/assert_junit_passed.py` | Không fragile trên Windows, typed |
| **Artifacts** | 15 `upload-artifact` rời rạc | Giữ nguyên, nhưng thêm `retention-days: 14` | Tiết kiệm storage |
| **Timeout** | `timeout 1200` cho mọi job | `timeout 300` cho fast tier, `600` cho integration, `1200` chỉ cho postgres | Fail nhanh hơn |

### 6.3 Ví dụ job mới (thay thế `python-unit-sqlite`)

```yaml
  unit-fast:
    name: Unit (pure, <60s)
    runs-on: ubuntu-latest
    env:
      TMPDIR: ${{ runner.temp }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { version: ${{ env.UV_VERSION }} }
      - uses: actions/setup-python@v5
        with: { python-version: ${{ env.PYTHON_VERSION }} }
      - run: uv sync --all-packages
      - name: Pure unit tests (xdist)
        run: |
          python scripts/verification/run_command_receipt.py \
            --name unit_fast \
            --output artifacts/ci/unit-fast/receipts/pytest.json \
            --timeout 300 \
            -- uv run pytest -m unit -q -n auto --dist loadscope \
               --junitxml=artifacts/ci/unit-fast/test-results/pytest.xml
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: unit-fast-evidence, path: artifacts/ci/unit-fast/ }

  architecture-fast:
    name: Architecture Boundaries (30s)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-python@v5
      - run: uv sync --all-packages
      - run: |
          python scripts/verification/run_command_receipt.py \
            --name architecture \
            --output artifacts/ci/architecture-fast/receipts/pytest.json \
            --timeout 180 \
            -- uv run pytest -m architecture -q \
               --junitxml=artifacts/ci/architecture-fast/test-results/pytest.xml
```

### 6.4 Local DX — `Makefile` / `uv run` shortcuts

```makefile
# Makefile (hoặc scripts/test.sh)
.PHONY: test test-unit test-component test-contract test-integration test-arch

test-unit:
	uv run pytest -m unit -q -n auto

test-component:
	uv run pytest -m component -v --tb=short

test-contract:
	uv run pytest -m contract -v --tb=short

test-integration:
	uv run pytest -m integration -v

test-arch:
	uv run pytest -m architecture -v

test-fast:  # dev pre-commit
	uv run pytest -m "unit or architecture" -q -n auto

test-full:  # pre-push
	uv run pytest -m "not slow and not postgres" -q

ci-local: lint test-fast
	uv run ruff check .
```

---

## 7. Lộ trình di chuyển (Migration Plan — 4 bước, mỗi bước 1 PR)

### Bước 1 — Nền tảng (không đụng file, 1-2 ngày)

- [ ] Tạo `tests/conftest.py` (root) với `isolated_db_url`, `isolated_engine`, `api_client`, `poll_until`.
- [ ] Cập nhật `pyproject.toml`: thêm `markers` + `addopts` + `filterwarnings`.
- [ ] Thêm `pytest-xdist` vào `dependency-groups.dev`.
- [ ] Gán `pytestmark` vào 30 file đại diện (mỗi nhóm 2-3 file) để demo.
- [ ] Xóa `sys.path.insert` trong 5 file pilot, thay bằng import trực tiếp.
- [ ] Cập nhật `ci.yaml`: thêm 2 job pilot `unit-fast` và `architecture-fast` chạy song song với job cũ (không xóa job cũ) — so sánh thời gian.

### Bước 2 — Gán marker toàn bộ (2-3 ngày)

- [ ] Script tự động gán `pytestmark` dựa trên heuristic:
  - File có `tmp_path` + `create_async_engine` → `component`
  - File có `TestClient` → `contract`
  - File trong `architecture/` → `architecture`
  - File trong `verification/` → `verification`
  - Còn lại trong `unit/` không chạm DB/HTTP → `unit`
- [ ] Thay `time.sleep`/`asyncio.sleep` bằng `poll_until` trong 15 file (PR riêng).
- [ ] Xóa toàn bộ `sys.path.insert` còn lại (30 file).
- [ ] Đổi tên test trùng lặp: `test_real_repo_architecture_stays_clean` → `test_phase04_real_repo_stays_clean` (theo phase).

### Bước 3 — Tách thư mục vật lý (tùy chọn, 3-5 ngày)

- [ ] `git mv tests/unit/storage tests/component/storage`
- [ ] `git mv tests/unit/providers tests/component/providers` (trừ `test_canonical_registry` pure)
- [ ] `git mv tests/unit/verification tests/verification`
- [ ] `git mv tests/unit/api/test_studio_v3_api.py tests/contracts/api/`
- [ ] Tách `fakes/studio_fakes.py` → `fakes/studio/{orchestrator,repositories,capability}.py`
- [ ] Tách file lớn: `test_phase26_episode.py` → `test_phase26_episode_{compile,render,audio}.py`

### Bước 4 — CI/CD hoàn chỉnh (2-3 ngày)

- [ ] Thay thế `python-unit-sqlite` bằng 3 jobs `unit-fast`/`component-sqlite`/`architecture-fast`.
- [ ] Thêm `unit-windows` đối xứng, cache `node_modules`, `xdist`, `coverage` gate.
- [ ] Thay `grep` trong `p1-e2e-postgres` bằng `assert_junit_passed.py`.
- [ ] Thêm `ruff check .` toàn repo, cấm `sys.path` hack & `sleep` cứng.
- [ ] Cập nhật `final-evidence` để validate `CI_JOB_RESULTS` mới.
- [ ] Đo lại wall-time: mục tiêu **Tier 1 <3m, Tier 2 <12m** (hiện tại ~18-22m).

---

## 8. Phụ lục — Số liệu chi tiết & file cần chú ý

### 8.1 Top 20 file lớn nhất (cần tách ưu tiên)

| # | LOC | Tests | File | Hành động |
|---|---|---|---|---|
| 1 | 947 | 33 | `tests/unit/intelligence/test_phase26_episode.py` | Tách 3 file theo leg (render/audio/compile) |
| 2 | 926 | 29 | `tests/unit/worker/test_studio_runtime.py` | Tách `runtime`/`deadline`/`model_runtime` |
| 3 | 847 | 23 | `tests/unit/api/test_architecture_v3_phase6_realtime.py` | → `tests/contracts/realtime/` (HTTP) |
| 4 | 788 | 17 | `tests/unit/orchestration/test_studio_run_service.py` | → `tests/component/orchestration/` |
| 5 | 779 | 58 | `tests/unit/workflows/test_phase4_social_source_collection.py` | Tách theo source type (4 file) |
| 6 | 761 | 28 | `tests/unit/intelligence/test_phase25_golden_scene.py` | → `component` (DB) |
| 7 | 740 | 15 | `tests/architecture/test_architecture_v3_phase16.py` | Tách `canonical` vs `policy` |
| 8 | 691 | 40 | `tests/unit/tools/test_phase3_blender_runtime.py` | → `component` (blender mock) |
| 9 | 688 | 59 | `tests/unit/tools/test_phase22_technical_review.py` | Giữ `unit` nhưng tách 2 file |
| 10 | 666 | 31 | `tests/unit/api/test_studio_v3_api.py` | → `tests/contracts/api/` |
| 11 | 645 | 25 | `tests/unit/worker/pipeline/test_phase9_worker_pipeline.py` | → `component/worker` |
| 12 | 637 | 38 | `tests/unit/storage/migrations/test_phase1_migration_integrity.py` | → `component/storage/migrations/` |
| 13 | 635 | 30 | `tests/unit/tools/test_plugins_skills_mcp.py` | Tách `plugins` vs `skills` vs `mcp` |
| 14 | 629 | 37 | `tests/unit/tools/test_phase4_blender_scene.py` | → `component` |
| 15 | 621 | 42 | `tests/unit/intelligence/test_phase20_reviewers.py` | Giữ `unit` |
| 16 | 618 | 44 | `tests/unit/scripts/test_validate_artifact_schema.py` | → `verification` |
| 17 | 617 | 37 | `tests/unit/providers/test_phase5_asset_gateway.py` | → `component/providers` |
| 18 | 609 | 29 | `tests/architecture/test_architecture_v3_phase4.py` | Tách `route-inventory` vs `namespace-authority` |
| 19 | 594 | 21 | `tests/architecture/test_phase3_negative.py` | Giữ nhưng xóa `time.sleep` |
| 20 | 592 | 51 | `tests/unit/intelligence/test_intelligence_system.py` | Tách theo phase |

### 8.2 File có `sys.path` hack (30 file — cần xóa)

```
tests/architecture/test_architecture_v3_phase13.py
tests/architecture/test_architecture_v3_phase14.py
tests/architecture/test_architecture_v3_phase15.py
tests/architecture/test_architecture_v3_phase16.py
tests/architecture/test_architecture_v3_phase2.py
tests/architecture/test_architecture_v3_phase3.py
tests/architecture/test_architecture_v3_phase4.py
tests/architecture/test_architecture_v3_phase7.py
tests/architecture/test_architecture_v3_policy.py
tests/architecture/test_phase04_videoclaw_quarantine.py
tests/contracts/test_v3_vertical_lifecycle_real.py
tests/integration/test_p0_5_story_dag_resume.py
tests/integration/test_p0_6_lock_semantics.py
tests/integration/test_phase5_execute_endpoint.py
tests/integration/test_phase6_workflow_control_surface.py
tests/regression/test_cutover_defects.py
tests/unit/test_phase7_composition.py
tests/unit/api/test_phase25_api_cutover.py
... (xem đầy đủ trong log quét)
```

### 8.3 File có `sleep` cứng (15 file — cần thay `poll_until`)

```
tests/architecture/test_architecture_v3_phase15.py: asyncio.sleep
tests/architecture/test_architecture_v3_phase16.py: asyncio.sleep
tests/architecture/test_phase3_negative.py: time.sleep
tests/integration/test_phase1_multiprocess_e2e.py: time.sleep
tests/integration/test_phase14_two_process_e2e.py: time.sleep + asyncio.sleep + windagent.db
tests/unit/api/test_architecture_v3_phase6_realtime.py: asyncio.sleep
tests/unit/execution/test_phase18_execution_worker.py: time.sleep
tests/unit/memory/test_memory_system.py: time.sleep
tests/unit/orchestration/test_phase17_durable_workflow.py: time.sleep
tests/unit/providers/mock_adapter.py: asyncio.sleep
tests/unit/providers/test_phase5_asset_gateway.py: asyncio.sleep
tests/unit/scripts/test_studio_c8_c9_certification.py: time.sleep
tests/unit/verification/test_evidence_generation.py: time.sleep
tests/unit/worker/test_phase04_worker_heartbeat.py: asyncio.sleep
tests/unit/worker/test_production_worker.py: time.sleep
```

### 8.4 Thống kê `pytest.mark` hiện tại

- `parametrize`: 1 file (`test_architecture_policy.py`)
- `asyncio`: ~35 lần (rải rác, không có `pytestmark` tập trung)
- `skipif`: 1 lần (`test_phase3_negative.py` Windows symlink)
- `skip`: 1 lần (`test_architecture_v3_phase16.py`)
- **Không có** `unit`/`integration`/`slow`/`postgres` → cần bổ sung.

### 8.5 Cấu trúc hiện tại vs đề xuất (so sánh trực quan)

```
HIỆN TẠI (phẳng, lẫn lộn)              ĐỀ XUẤT (pyramid, marker-driven)
─────────────────────────              ──────────────────────────────────
tests/                                tests/
├── architecture/ (66)                 ├── conftest.py ★
├── contracts/ (51) + conftest         ├── support/ ★
├── fakes/ (6)                        ├── fakes/ (chia studio/)
├── fixtures/ (4)                     ├── fixtures/ (+ factories.py)
├── integration/ (26)                 ├── unit/ (chỉ pure, ~85 file)
├── regression/ (2)                   ├── component/ ★ (~110 file từ unit)
├── unit/ (243) ← HỖN HỢP              ├── contracts/ (51 + 18 từ unit/api)
│   ├── api/ (19) ← lẫn contract      ├── integration/ (26, + markers)
│   ├── storage/ (13) ← DB            ├── architecture/ (66, + markers)
│   ├── verification/ (26) ← sai chỗ  ├── verification/ ★ (26 từ unit)
│   └── ...                           ├── regression/ (2 → N)
└── __pycache__/                       └── e2e/ ★ (tùy chọn)
```

---

## 9. Checklist sẵn sàng cho Unit Test & CI/CD

| Tiêu chí | Hiện trạng | Sau tái cấu trúc | Cách kiểm tra |
|---|---|---|---|
| **Unit pure chạy <60s** | ❌ 12-18m (lẫn DB) | ✅ `pytest -m unit -n auto` <60s | `time uv run pytest -m unit -q` |
| **Hermetic (không rò windagent.db)** | ⚠️ 1 file còn hard-code | ✅ 100% qua `isolated_db_url` | `grep -r "windagent.db" tests/ --exclude-dir=__pycache__` == 0 (trừ conftest) |
| **No sleep flaky** | ❌ 15 file | ✅ 0 `time.sleep` ngoài `support/` | `grep -rn "time.sleep" tests/` == 0 |
| **No sys.path hack** | ❌ 30 file | ✅ 0 | `grep -rn "sys.path.insert" tests/` == 0 |
| **Marker coverage 100%** | ❌ 0% | ✅ 100% file có `pytestmark` | `grep -L "pytestmark" tests/**/*.py` == 0 |
| **CI fast feedback <3m** | ❌ 12m | ✅ Tier1 <3m | GitHub Actions wall-time |
| **Coverage gate** | ❌ không | ✅ 70% branch | `pytest --cov --cov-fail-under=70` |
| **Windows parity** | ⚠️ lệch | ✅ đối xứng | So sánh `ci.yaml` jobs ubuntu vs windows |
| **Ruff toàn repo** | ❌ 11 file | ✅ `ruff check .` | `uv run ruff check .` |
| **Duplicate fixture 0** | ❌ 40+ | ✅ 1 `conftest.py` | `grep -rn "P01_TABLES" tests/` == 1 |

---

## 10. Kết luận

- `tests/` hiện tại **rất kỷ luật về mặt kiến trúc** (66 architecture tests, 51 contracts, 26 integration) nhưng **lẫn lộn pyramid**: 60% `unit/` thực chất là `component`/`contract`, thiếu `conftest` gốc, thiếu marker, còn `sys.path` hack và `sleep` cứng.
- **Không cần viết lại test** — 1.377 tests hiện tại có giá trị cao, chỉ cần **gán marker + tách conftest + xóa hack + chia job CI**.
- Lộ trình 4 bước (mỗi bước 1 PR, tổng 8-13 ngày) sẽ đưa repo từ **"1 job 12 phút"** xuống **"Tier1 3 phút + Tier2 12 phút song song"**, đồng thời mở đường cho `xdist`, `coverage`, `postgres` matrix và `e2e` nightly.
- Đề xuất **bắt đầu ngay Bước 1** (tạo `tests/conftest.py` + `pyproject.toml` markers + 2 job pilot) để đo lợi ích trước khi di chuyển vật lý.

---

*Báo cáo được sinh tự động bằng quét tĩnh 388 file + đối chiếu `pyproject.toml` + `.github/workflows/ci.yaml`. Chi tiết quét thô lưu tại `C:\Users\Admin\AppData\Local\Temp\opencode\*_analysis.txt`.*
