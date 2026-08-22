# P0.8 — FUNCTIONAL E2E ACCEPTANCE

**Gate:** `P0_8_FUNCTIONAL_E2E_SQLITE` ✅ **PASS**

**P0 final acceptance:** **BLOCKED** by PostgreSQL authentication and real-provider authentication.

**Ngày:** 2026-08-22 · Input: `ban_ke_hoach_v1.md` §P0.8 + P0 Final Acceptance matrix

---

## 1. Scenario → test mapping

| Scenario | Luồng | Test chứng minh | Kết quả |
|---|---|---|---|
| **A — Auto approval** | API→Series→Episode→Run→durable queue→production Worker→route lock/coordinator→provider transport→artifacts→review→lock→restart | `tests/contracts/test_v3_vertical_lifecycle_real.py`; production composition và SQL authorities, deterministic adapter chỉ thay external provider transport | **PASS** trên SQLite |
| **B — Human approval** | Review → WAITING_APPROVAL → Approve → Lock | `test_studio_full_dag_auto_drive.py` + `test_story_b8_lock_gate.py` | **PASS** |
| **C — Revision** | Review issue → Revision → Re-review → Approval → Lock | auto-drive + P0.6 lock suites | **PASS** |
| **D — Provider failure → declared fallback** | Eligible primary failure → declared fallback model → separate immutable lock → persisted receipt | `test_p0_3_model_routing.py` + `test_studio_model_port.py` | **PASS** |
| **E — Restart recovery** | Worker restart giữa run → same-run resume, no duplicate committed work/event | `tests/integration/test_p0_5_story_dag_resume.py` | **PASS** |

Vertical lifecycle không bypass queue/worker và không insert artifact cuối bằng tay. Nó đăng ký/discover provider qua production management/probe services, boot production `WorkerContainer`, thực thi `ProductionWorker`, dùng `RouteLockedModelPort` + `EndpointExecutionCoordinator`, persist route receipts/artifacts, rồi reopen storage để chứng minh durability.

## 2. Final verification matrix

| Gate | Trạng thái | Evidence thực tế |
|---|---|---|
| P0.3 routing/model port | **PASS** | focused matrix; fallback eligibility/lock/receipt semantics giữ nguyên |
| P0.4 Series/Episode/preflight | **PASS** | worker/model_route/story_engine missing hoặc unavailable đều FAIL; active-run resume vẫn drift tolerant |
| P0.5 Story DAG/resume | **PASS** | durable resume regression |
| P0.6 review/revision/lock | **PASS** | lock/CAS/immutability regression |
| SQLite vertical lifecycle | **PASS** | 1 canonical full lifecycle + restart |
| Canonical Studio contracts/consumers | **PASS** | **739 passed, 31 baseline skips, 0 failed** |
| Focused P0 + P1 truth-repair regression | **PASS** | **105 passed, 0 failed** |
| Frontend tests | **PASS** | **119 passed** |
| Frontend typecheck | **PASS** | 0 errors |
| Desktop tests | **PASS** | **27 passed** |
| Desktop typecheck | **PASS** | 0 errors |
| Desktop build | **PASS** | Vite production build |
| Studio CI checker bundle | **PASS** | all 8 checkers passed |
| Architecture checker | **PASS** | 0 violations, 0 dependency cycles |
| PostgreSQL server | **PASS (server only)** | PostgreSQL 18 service, `localhost:5432` accepting connections |
| PostgreSQL migration + Studio vertical | **BLOCKED_ENVIRONMENT** | SCRAM auth requires password; no `WINDAGENT_TEST_POSTGRES_URL`, pgpass, or non-interactive credential. Repository head resolves to `0017_route_receipts`; actual PG upgrade/vertical **NOT RUN** |
| Real-provider smoke | **FAIL_AUTH** | Anthropic credential variables exist, but production Test Connection returned invalid-token/HTTP 400 for the two configured credential sources; Sync Models/Test Model/routing/Studio inference therefore did not run |

## 3. P0.7 drift reconciliation

Các mục từng được ghi là outstanding đã được đóng và không còn là blocker:

- episode state dùng canonical Studio authority;
- Studio Home dùng Series domain và live metrics;
- legacy `/api/v3/episodes/{episode_id}/start-generation` đã rời OpenAPI authority;
- desktop regression mocks đã chuyển từ `/api/v3/projects` sang `/api/v3/studio/series`.

## 4. Gate

```text
P0_8_FUNCTIONAL_E2E_SQLITE = PASS

POSTGRES_STUDIO_VERTICAL_SLICE = BLOCKED_ENVIRONMENT
REAL_PROVIDER_SMOKE = FAIL_AUTH

P0_FINAL_ACCEPTANCE_BLOCKED
DO NOT START P1.1
```

Không được nâng PostgreSQL hoặc provider smoke thành PASS dựa trên SQLite, deterministic transport, hay assumption.
