# P0.0 — FEATURE TRUTH BASELINE (captured)

**Gate:** `P0_0_FEATURE_TRUTH_CAPTURED` ✅ **ACHIEVED**

**Ngày capture:** 2026-08-22 · Máy: Windows (win32), PowerShell

---

## 1. P0.0.1 — Baseline đã capture

### Git

```text
HEAD        : cfa7ffb33fc1801ca8ad8115c605c320ddb4c51a   (= baseline trong ban_ke_hoach_v1.md)
Tree SHA    : d09bab04e2e460ab6b7cf684f86c3f96f473904e
Branch      : refactor/architecture-v3-hardening
Dirty state : 1 file  →  M ban_ke_hoach_v1.md (chỉ file kế hoạch, không phải code)
```

### Environment

```text
Python : 3.11.15   (.venv tại repo root, uv workspace 17 members)
Node   : v22.23.1
npm    : 10.9.8    (pnpm không cài)
DB     : SQLite mặc định (windagent.db, sqlite+aiosqlite)
         env override: WINDAGENT_DATABASE_URL
         PostgreSQL hỗ trợ thật: postgresql+asyncpg (+psycopg2 cho sync repos),
         Alembic migrations 0001_baseline … 0015_execution_lease_release
```

DB config tham chiếu: `apps/api/windagent_api/bootstrap/__init__.py:19`, `apps/worker/windagent_worker/composition/settings.py:116`, `storage/windagent_storage/database/connection.py`.

### Kết quả test suites

| Suite | Lệnh | Kết quả |
| --- | --- | --- |
| Provider unit tests | `pytest tests/unit/providers` | **186 passed**, 22 warnings (4.5s) |
| Worker unit tests | `pytest tests/unit/worker` | **94 passed** (9.3s) |
| Studio/API contract subset | `pytest tests/contracts/test_phase7… test_phase8… test_phase9… test_studio_contract_fixtures… test_v3_vertical_lifecycle_real` | 67 passed, **4 FAILED** |
| Toàn bộ contracts suite | `pytest tests/contracts` (trừ phase7 + phase16 theo đúng plan) | **515 passed**, 31 skipped, **1 FAILED** (~102s) |
| Provider routing integration | `pytest tests/integration/test_architecture_v3_phase10_provider_routing.py` | **4 passed** |
| Frontend workspaces | `npm run test --workspaces --if-present` (frontend/) | **119 passed / 22 files**: api-client 20, api-contracts 5, realtime 8, studio-shell 11, ui 23, app 52 |
| Desktop vitest | `npm run test` (apps/desktop) | **27 passed / 4 files** |
| Web vitest | `npm run test` (apps/web) | 1 file passed |
| Desktop typecheck | `npm run type-check` (tsc -b --noEmit) | **PASS** |
| Desktop build | `npm run build` (tsc -b && vite build) | **PASS** (12.8s) |

Phase-16 certification KHÔNG chạy (đúng phạm vi plan: "Không cần chạy full Phase-16 certification").

### Failures cần biết (truth, không che giấu)

1. `tests/contracts/test_phase7_projects_and_studio.py` — 4 FAIL trên profile sạch:
   `test_list_projects_contract`, `test_filter_and_search_projects_contract`,
   `test_get_project_detail_and_not_found`, `test_list_and_create_episodes_contract`.
   Nguyên nhân: test assert `len(items) >= 1` trên DB sạch trong khi demo seed hiện bị gate chặt sau `WINDAGENT_PROFILE=demo`. Đây là **phụ thuộc dữ liệu demo trong test**, không phải lỗi production runtime.
2. `tests/contracts/test_code_video_assembly.py::test_assemble_master_step_executor` — FAIL
   `TypeError: AssembleMasterStepExecutor.__init__() missing 1 required positional argument: 'assembler'`.
   Code-video domain, **ngoài phạm vi P0** — ghi nhận để dọn ở đợt hardening sau.

---

## 2. P0.0.2 — Inventory P0 APIs + phân loại truth

Ký hiệu cột: **UI** = có consumer frontend thật · **Persistence** = durable SQL · **Runtime** = gọi runtime thật (provider/worker) · **Demo** = fallback chỉ khi `WINDAGENT_PROFILE=demo` · **Stub** = hard-coded, không gated.

### 2.1 `/api/v3/providers` — file: `apps/api/windagent_api/routers/v3/providers.py`

| Endpoint | Trạng thái | UI | Persistence | Runtime | Demo | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| `GET ""` (list) | WORKING | ✅ RoutingPage | ✅ SQL authority | – | merge catalog demo khi profile=demo | `ProviderResource` chỉ lộ `has_credentials`, không bao giờ trả key |
| `POST ""` (create) | WORKING | ✅ form Add Provider | ✅ vendor+credential+endpoint atomic | – | không | Secret encrypt AES-GCM (`enc:v1:...`) vào `provider_credentials.secret_ciphertext`; key env `WINDAGENT_ENCRYPTION_KEY`, fail-closed nếu thiếu key |
| `GET /health` | PARTIAL | ✅ | ✅ | – | merge demo | OK nhưng map health gộp thêm catalog demo khi profile=demo |
| `POST /{id}/test-connection` | WORKING | ✅ nút Test Connection | ✅ `provider_endpoints.test_status`, `endpoint_health_samples` | ✅ httpx adapter thật: `GET {base_url}/models` | receipt giả CHỈ khi profile=demo, ngược lại 409 fail-closed | Receipt: `test_id, reachable, latency_ms, auth_valid, model_discovery[], error_code, message, completed_at`. Probe fail-closed, không fabricate health |
| Model discovery | PARTIAL (nhúng sai chỗ) | ❌ không có nút riêng | ✅ `canonical_models_v3` + `endpoint_model_bindings` + `model_discovery_snapshots` | ✅ adapter `list_models()` | – | **Discovery đang nhúng bên trong test-connection** (probe.py:105), chưa tách thành operation riêng → vi phạm P0.2.1 |
| `GET /{id}/models` | BACKEND_ONLY | ❌ | ✅ registry discovered | – | demo match | Registry thật tồn tại nhưng Models page không đọc nó |
| `PATCH` provider | **KHÔNG TỒN TẠI** | ❌ | – | – | – | Không route, không service method; api-client cũng không có method |
| `DELETE` provider | **KHÔNG TỒN TẠI** | ❌ | – | – | – | Như trên; cũng chưa có kiểm tra dependency với routing rule |
| Enable/Disable | **KHÔNG TỒN TẠI** | ❌ | – | – | – | Như trên |
| Credential rotate/remove | **KHÔNG TỒN TẠI** (API) | ❌ | util có sẵn | – | – | `reencrypt_to_current` (storage/security/encryption.py:171) chỉ dùng bởi tests/migrations, chưa expose |

Persistence: SQLAlchemy tables `provider_vendors, provider_credentials, provider_endpoints, canonical_models_v3, endpoint_model_bindings, model_routing_rules_v3, provider_routing_audit_v3, endpoint_health_samples` (`storage/windagent_storage/orm/v3_models.py`). Audit persist có redaction trước khi ghi.

Credential security: **đạt chuẩn P0.1.2 ngay từ baseline** — write-only, encrypted-at-rest, never returned/logged/event-payload.

### 2.2 `/api/v3/models` — file: `routers/v3/models.py`

| Endpoint | Trạng thái | Ghi chú |
| --- | --- | --- |
| `GET /models` (list) | **STUB-backed reads** | Đọc từ table generic `v3_resources` namespace `models` — namespace này CHỈ được đổ bởi static demo seed (`v3_demo_seed.py:546-694`, 8 model hard-coded). **Profile mặc định → trả về `[]` rỗng** |
| `GET /models/{id}` | STUB-backed reads | Như trên |
| Sync Models | **KHÔNG TỒN TẠI** | Không endpoint nào; discovery chỉ chạy ngầm trong test-connection |
| Free/Paid filter | **KHÔNG TỒN TẠI** | Không có semantics FREE/PAID/UNKNOWN; demo seed có pricing nhúng |
| Test Model (probe inference nhỏ) | **KHÔNG TỒN TẠI** | Chưa có anywhere |

→ Registry durable thật (`canonical_models_v3`) là BACKEND_ONLY: viết được từ probe nhưng **không bao giờ sync sang router `/models`**. Đây là khoảng trống lớn nhất của P0.2.

### 2.3 `/api/v3/routing` — file: `routers/v3/routing.py`

| Endpoint | Trạng thái | Ghi chú |
| --- | --- | --- |
| `GET/POST /rules`, `GET/PATCH/DELETE /rules/{id}` | WORKING | Durable `v3_resources:routing_rules`, optimistic version check; mỗi mutation refresh runtime ruleset qua `RoutingAuthorityBridge`; SQL rỗng → fallback ruleset immutable deployment |
| `GET /graph` | **STUB** | Tổng hợp link fixed-weight cứng (ungated) |
| `GET /metrics` | **STUB** | Traffic distribution hard-coded ~27000 routes (ungated) — **vi phạm "không fake metrics" nếu UI mount** |
| `WS /ws/v3/model-infra` | **STUB** | Heartbeat canned mỗi 20s (ungated) |
| `POST /simulations` | WORKING | Simulate rule matching |
| `GET /locks/{id}` | WORKING | Durable `route_locks_v3` |
| Resolution order | WORKING | `RouteLockService.resolve_or_create_lock` → `RuleMatcher.find_first_match` theo priority; bất biến `canonical_model_id NEVER changes` |
| Fallback | PARTIAL | Rule-level `fallback_model_id` tồn tại trong schema/simulation nhưng **KHÔNG dùng khi execute**; fallback thật là endpoint-failover cùng model (`EndpointExecutionCoordinator`: exact-equivalent bindings, cooldown, circuit state, attempts vào `route_attempts_v3`). Chưa có semantic "fallback sang model khác cho defined failures" như P0.3.5 |
| Route receipt | PARTIAL | Chưa có literal `route_receipt`; gần nhất: `RouteLockReceipt` + `route_attempts_v3`. Thiếu `fallback_used/fallback_reason` ở mức model như P0.3.6 |
| Worker dùng rules | WORKING | Worker bootstrap load `model_routing_rules_v3` qua `RoutingPolicyProjection` (`apps/worker/windagent_worker/composition/providers.py:52-54`) |

### 2.4 `/api/v3/studio/*`

| Endpoint group | Trạng thái | Persistence | Runtime | Ghi chú |
| --- | --- | --- | --- | --- |
| `series` create/list/get | WORKING | ✅ `studio_series_projects` | – | **Không có update/edit mutation** |
| `episodes` create/list/get | WORKING | ✅ `studio_episodes` | – | **Không có update/edit mutation** |
| `runs` start/resume | WORKING | ✅ queue SQL durable (`SqlDurableTaskQueue`: claim `with_for_update(skip_locked)`, leases + fencing tokens, outbox dedup `studio_submit:<run>:<node>:<attempt>`) | ✅ Worker process riêng claim task | Commit task identity TRƯỚC node DISPATCHED → crash-resumable đúng thiết kế |
| `runs/{id}`, `runs/{id}/events` | WORKING | ✅ `studio_runs`, `studio_run_nodes`, `studio_events` | – | Cursor-based events |
| `artifacts` list/get | WORKING | ✅ `studio_artifacts` content-addressed | – | Chain: revision_id + content_hash |
| decisions: idea-selection / approvals / revisions / screenplay-lock | WORKING | ✅ `studio_revisions`, `studio_approval_policies`, `studio_approval_decisions` | – | CAS/optimistic version + artifact_hash binding đúng hướng plan |
| aggregator `capabilities` / `readiness` | WORKING (backend) | – | – | **Backend expose nhưng frontend không dùng** (frontend gọi `/health` thường) |
| Real Story DAG runtime | WORKING **khi flag** | ✅ toàn bộ tables trên | ✅ `RouteLockedModelPort` → RouteLockService → EndpointExecutionCoordinator → adapter THẬT, "no mock fallback" | Yêu cầu đồng thời `WINDAGENT_STUDIO_RUNTIME=1` VÀ `WINDAGENT_STUDIO_MODEL_ROUTE=1`; thiếu → fail-closed `STUDIO_MODEL_PORT_UNAVAILABLE` (honest). Handlers đầy đủ idea/bible/beats/outline/screenplay/review/revise/lock |
| **Legacy `POST /api/v3/episodes/{id}/start-generation`** | **STUB** | ⚠️ | ❌ | `routers/v3/episodes.py:240-271` — ghi run `status=COMPLETED, progress=100` **ngay lập tức, không gọi model nào, không gated**. ⚠️ **Đây chính là endpoint mà EpisodeWorkspacePage đang gọi** |

#### ⚠️ Phát hiện nghiêm trọng nhất của baseline

```text
FRONTEND HIỆN ĐANG DRIVE PIPELINE GIẢ:

EpisodeWorkspacePage → POST /api/v3/episodes/{id}/start-generation  (STUB instant-COMPLETED)

Toàn bộ đường thật /api/v3/studio/episodes/{id}/runs (durable queue → worker →
model router → provider thật) CHƯA CÓ BẤT KỲ UI CONSUMER NÀO.
Frontend cũng không có domain "Series" — nó dùng Projects (legacy surface).
```

Đây là việc đầu tiên P0.7 phải nối lại: đổi nguồn dữ liệu episode workspace từ legacy stub sang `/api/v3/studio/*`.

### 2.5 Frontend truth (tóm tắt inventory)

| Surface | File | Truth |
| --- | --- | --- |
| ProvidersPage | `frontend/app/src/features/providers/pages/ProvidersPage.tsx` | **Alias thuần**: `return <RoutingPage/>` — đúng như plan đã nghi ngờ |
| Add Provider + Test Connection + tạo rule | `features/routing/pages/RoutingPage.tsx` | WORKING UI, gọi API thật; nhưng **thiếu Edit/Delete/Enable-Disable** (api-client không có method) |
| Models page | `features/models/pages/ModelsPage.tsx` | Read-only catalog đọc `/api/v3/models` (= dữ liệu stub/demo); **ẩn khỏi sidebar**; không có Sync/Test Model/Free-Paid |
| Tạo routing rule | RoutingPage | **Nhập `primary_canonical_model_id` bằng text thủ công** — đúng vấn đề P0.3.3; toàn bộ UI rules/graph/metrics/simulator rich (`useRouting.ts` + 749-line RoutingRules…) đã code xong nhưng **orphaned, không mount** |
| Studio Home | `features/studio/pages/StudioHomePage.tsx` | Gọi `/api/v3/projects` thật — **không phải `/api/v3/studio/series`** |
| Episode Workspace | `features/episodes/pages/EpisodeWorkspacePage.tsx` + panels | Gọi API thật + WS `/ws` thật; NHƯNG start-generation là **endpoint stub** (mục 2.4); fallback ID hard-coded `proj-cyberpunk-01`/`ep-cb-001` |
| CheckpointReviewPanel | `features/episodes/workspace/CheckpointReviewPanel.tsx` | ⚠️ **Fabricate lock hash client-side**: `` `sha256-${crypto.randomUUID()}` `` — không phải hash nội dung thật |
| LiveRecordPage | `features/live-record/hooks/useLiveRecord.ts` | UI_ONLY canned demo — **NOT_REQUIRED_FOR_P0** |
| Frontend tests | 27 file Vitest | Toàn bộ mocked-fetch, 0 test chạm API sống; phần lớn là export-smoke |
| Placeholder packages | `frontend/packages/{production-*,story-ui,studio-client,studio-state}` | 8 package rỗng (chỉ tsbuildinfo) |

### 2.6 Registry demo/fallback/toàn bộ trigger

| # | Vị trí | Loại | Trigger |
| --- | --- | --- | --- |
| 1 | `lifespan.py:48` + `v3_demo_seed.py` (~35 namespaces sample data) | demo seed | `WINDAGENT_PROFILE=demo` |
| 2 | `providers.py:398-445` receipt connection giả | demo | profile=demo + provider ngoài SQL authority; ngược lại 409 |
| 3 | `providers.py:201-204` health merge demo | demo | profile=demo |
| 4 | `routing.py:410-432` metrics cứng | **STUB ungated** | luôn luôn |
| 5 | `routing.py:532-561` WS heartbeat canned | **STUB ungated** | luôn luôn |
| 6 | `routing.py:378-407` graph weights cố định | **STUB ungated** | luôn luôn |
| 7 | `episodes.py:240-271` start-generation instant COMPLETED | **STUB ungated** | luôn luôn — ⚠️ frontend đang dùng |
| 8 | `intelligence/story/prompts/fixture.py` FixtureModelPort | fake | tests-only; certification mode reject |
| 9 | `worker/composition/core.py:59-66` FakeRuntimeAdapter | fake | `WINDAGENT_FAKE_RUNTIME=1` (non-studio) |
| 10 | `route_lock_service.py:133-140` in-memory lock store | dev/test | không inject repo (warn loudly) |

Không thấy hard-coded success khác trong đường Studio thật; đường Studio fail-closed trung thực khi thiếu flag/port.

### 2.7 Bug `issued_at` (P0.6.1) — xác nhận vị trí

```text
orchestration/windagent_orchestration/studio/service.py:1248-1263 (_lock_inputs)

issued_at = datetime.fromtimestamp(int(draft_hash[:8], 16) % 2_145_916_800, tz=timezone.utc)
```

Timestamp của `LockedScreenplayReceipt` derive từ content hash (pseudo-time 1970–2037 cho fixture determinism), không phải wall-clock persist time. Approval decision thì dùng `utc_now()` thật. Downstream: `intelligence/story/review/service.py:546` copy sang `package.assembled_at`. Sửa ở P0.6.1: production dùng giờ persist thật, test inject deterministic Clock.

---

## 3. P0.0.3 — Freeze existing contracts

Đã verify (`core/windagent_core/contracts/studio/commands.py`, `routers/v3/studio/schemas.py`):

```text
✓ Request schemas REUSE trực tiếp command contracts (CreateSeriesRequest(CreateSeriesCommand)...)
  — single source of truth, KHÔNG phá
✓ StudioCommand base: schema_version="studio.command/v1" + idempotency_key bắt buộc, frozen
✓ Idempotency        : idempotency_key trên mọi command (+ X-Idempotency-Key header ở router)
✓ Optimistic version : expected_optimistic_version (SelectIdea / RecordApproval /
                       DeriveRevision / LockScreenplay)
✓ Artifact hash      : expected_content_hash (64 hex) / artifact_hash
✓ Revision lineage   : DeriveRevisionCommand.parent_revision_id + invalidation_intent
```

Presentation fields (`target_audience, language, genre, tone, creative_brief, target_duration, constraints`):

```text
HIỆN TẠI: CreateSeriesCommand = {title, description, metadata: Dict[str,Any]}
          CreateEpisodeCommand = {series_id, title, episode_number, metadata: Dict[str,Any]}
metadata được persist nguyên trạng khi create VÀ được băm vào episode-identity seed
revision đầu tiên (service.py:954-970) — tức metadata hiện là free-form, CHƯA validate.

QUYẾT ĐỊNH P0 (theo plan): chuẩn hóa các field presentation BÊN TRONG metadata hiện hữu
(schema validate metadata keys), KHÔNG tạo contract V2.
```

Missing mutations đã confirm: **không tồn tại** `update_series` / `update_episode` ở bất kỳ đâu (service + router). P0.4 sẽ thêm dưới dạng mutation riêng có semantics immutable-vs-new-revision.

---

## 4. Bảng phân loại tổng hợp (Feature Truth)

| Feature | Phân loại |
| --- | --- |
| Provider create/list/get + credential AES-GCM + audit redaction | **WORKING** |
| Connection test thật + receipt + persist health | **WORKING** (receipt naming lệch nhẹ plan: `completed_at` thay `checked_at`) |
| Provider Edit/Delete/Enable/Disable/Credential rotate/remove | **MISSING** (không implement — absence, không phải stub) |
| Tách Sync Models khỏi Test Connection | **MISSING** |
| Discovered-model registry durable | **BACKEND_ONLY** (probe ghi được, không expose lên `/models`) |
| `/api/v3/models` catalog | **STUB-backed** (namespace chỉ đổ bởi demo seed; rỗng khi profile sạch) |
| Free/Paid/UNKNOWN pricing semantics | **MISSING** |
| Test Model probe (inference nhỏ) | **MISSING** |
| Routing rules CRUD durable + worker load ruleset | **WORKING** |
| Routing resolution + route locks + endpoint failover | **WORKING** |
| Rule-level model fallback (P0.3.5 semantics) | **PARTIAL** (schema có, execution không dùng) |
| Route receipt đầy đủ (P0.3.6) | **PARTIAL** (thiếu `fallback_used/fallback_reason` mức model) |
| Routing metrics/graph/model-infra WS | **STUB** (hard-coded, ungated) |
| Series/Episode create/list/get + runs/artifacts/decisions backend | **WORKING** |
| Series/Episode edit metadata | **MISSING** |
| Preflight Start Story (`START_BLOCKED` kèm lý do) | **MISSING** (readiness endpoint có nhưng không check đủ + UI không dùng) |
| Real Story DAG qua durable worker + provider thật | **WORKING khi flag** (`WINDAGENT_STUDIO_RUNTIME=1` + `WINDAGENT_STUDIO_MODEL_ROUTE=1`); fail-closed trung thực khi thiếu |
| Pause/resume/crash recovery | **WORKING** (queue SQL + outbox dedup + fencing) |
| Idea selection CAS | **WORKING** |
| Review/Revision/Approval/Lock semantics backend | **WORKING** (trừ bug `issued_at` đã định vị) |
| Lock immutability | **WORKING** (verify thêm ở P0.6.2) |
| Legacy `episodes/start-generation` | **STUB** — ⚠️ frontend đang tiêu thụ |
| Frontend: Providers surface riêng | **UI_ONLY** (alias RoutingPage) |
| Frontend: Episode workspace panels/pipeline | **PARTIAL** — UI thật nhưng drive pipeline stub, chưa nói chuyện `/api/v3/studio/*` |
| Frontend: Model selector / Provider selector cho rules | **MISSING** (text input thủ công; UI rich đã code nhưng orphaned) |
| Frontend: lock hash client-side | **BROKEN semantics** (`sha256-${uuid}` fabricate) |
| Desktop shell (Tauri 2) + typecheck + build | **WORKING** |
| LiveRecord | **NOT_REQUIRED_FOR_P0** (giữ nguyên) |

---

## 5. Mapping khoảng trống → phase P0

| Gap chính | Phase xử lý |
| --- | --- |
| Provider PATCH/DELETE/enable/rotate + delete-dependency-check | P0.1 |
| Tách Sync Models operation + expose registry lên `/models` + reconciliation ADDED/UPDATED/UNCHANGED/UNAVAILABLE + FREE/PAID/UNKNOWN + Test Model | P0.2 |
| Rule-level fallback semantics + route receipt đầy đủ + bỏ/gate metrics-graph-WS stub | P0.3 |
| Update series/episode mutations + metadata schema validation + preflight START_BLOCKED | P0.4 |
| Frontend chuyển episode workspace từ legacy stub → `/api/v3/studio/runs`; dựng domain Series; mount lại UI routing orphaned; provider/model selector thay text input; bỏ fabricate hash | P0.7 |
| Sửa `issued_at` (service.py:1248-1263) | P0.6.1 |
| Fix test_phase7 (bỏ phụ thuộc demo seed) | P0.8 / dọn test |

---

## Gate

```text
P0_0_FEATURE_TRUTH_CAPTURED = ACHIEVED
```

Baseline này là input bắt buộc cho P0.1 và P0.4 (nhánh song song theo mục 4 của plan).
