# P0.4 — SERIES & EPISODE PRODUCT COMPLETION (completed)

**Gate:** `P0_4_STUDIO_PROJECTS_USABLE` ✅ **ACHIEVED**

**Ngày:** 2026-08-22 · Input: `docs/plans/p0_feature_truth_baseline.md`, `ban_ke_hoach_v1.md` §P0.4

---

## 1. Series/Episode metadata authority (chuẩn hóa BÊN TRONG metadata)

Quyết định P0.0.3 được thực hiện đúng: **không tạo contract V2**. Module mới `core/windagent_core/contracts/studio/metadata.py` chuẩn hóa các field presentation bên trong `metadata` hiện hữu của `CreateSeriesCommand`/`CreateEpisodeCommand`:

```text
Series : target_audience, language, genre, tone, narrative_style,
         content_constraints, approval_policy (AUTO|REQUIRE_HUMAN|CONDITIONAL)
Episode: logline, creative_brief, target_duration, target_audience,
         episode_constraints
```

- Known keys được validate kiểu (sai kiểu → `STUDIO_VALIDATION_ERROR` 422 kèm field/got/expected); unknown keys pass-through nguyên trạng.
- `create_series`/`create_episode` validate metadata ngay từ authority (orchestration service).

## 2. Update mutations (trước P0.4: KHÔNG TỒN TẠI)

```text
PATCH /api/v3/studio/series/{id}    ← title/description + metadata_patch (merge)
PATCH /api/v3/studio/episodes/{id}  ← title + metadata_patch (merge),
                                       expected_optimistic_version optional
```

- Commands additive: `UpdateSeriesCommand/Result`, `UpdateEpisodeCommand/Result` (vẫn `studio.command/v1`, idempotency key bắt buộc qua header).
- Events mới (additive cả 2 catalog, giữ bất biến `registered == ALL_EVENTS`): `studio.series.updated`, `studio.episode.updated`.
- Domain: `Episode.edit()` — edit chỉ presentation, stale-write protection qua optimistic version, no-op patch trả về chính aggregate (không bump version).
- Idempotent repeat: patch giống hệt → không đổi version.

## 3. Semantics immutable-vs-new-revision

Sau khi episode rời DRAFT, các field ảnh hưởng generation trở thành **immutable**:

```text
GENERATION_AFFECTING_EPISODE_FIELDS =
    creative_brief | logline | target_duration |
    target_audience | episode_constraints
```

- Patch xung đột → 422 với `details.immutable_fields=[...]` + state hiện tại + hướng xử lý ("derive a new revision instead"). **Không bao giờ silently mutate context của run đang tồn tại.**
- Chỉ conflict khi giá trị THẬT SỰ khác (resubmit identical value = no-op).
- `title` là pure presentation → edit được ở mọi state.

## 4. P0.4.1 — Preflight START_BLOCKED

Module mới `apps/api/windagent_api/services/studio_preflight.py` — server kiểm tra TRƯỚC nút Start Story:

| # | Check | FAIL khi | Blocking |
|---|---|---|---|
| 1 | `episode_exists` | episode không tồn tại / query fail | YES |
| 2 | `creative_brief_valid` | thiếu hoặc không parse được `CreativeBrief` frozen contract | YES |
| 3 | `provider_configured` | không có provider enabled nào có endpoint configured credential | YES |
| 4 | `routing_rules_resolve` | còn role story nào không resolve được rule trong ruleset hiện tại | YES |
| 5 | `worker_capability_available` | capability provider/probe lỗi, hoặc bất kỳ capability `worker` / `model_route` / `story_engine` bị thiếu hay khác `AVAILABLE` | **YES** |
| 6 | `persistence_available` | series của episode đọc không được | YES |

- #5 là hard gate fail-closed cho **START NEW RUN**: capability thiếu không bao giờ được diễn giải thành AVAILABLE. `worker`, `model_route`, và `story_engine` đều phải có mặt và đều `AVAILABLE`.
- **RESUME EXISTING NON-TERMINAL RUN** vẫn giữ invariant P0.5: config/heartbeat drift không chặn resume; preflight chỉ chặn việc tạo run mới.
- API: `GET /api/v3/studio/episodes/{id}/preflight` → report `{episode_id, ready, checks[{name,status,detail}]}` truthy từng check.
- Gate: `POST /episodes/{id}/runs` chạy preflight trước; nếu có check FAIL và episode KHÔNG có active run để resume → **409 `START_BLOCKED`** kèm `reasons[]`. Resume run đang hoạt động không bao giờ bị chặn bởi config drift.
- Wire thật: preflight compose từ `provider_management_service` + `route_lock_service` (ruleset projection hiện hành) + capability probe attestation-based + read adapters.

## 5. Code map

| Layer | File |
| --- | --- |
| Core metadata | `core/windagent_core/contracts/studio/metadata.py` (MỚI) |
| Core commands | `contracts/studio/commands.py` (+4 class update), `ports.py` (+update_series/update_episode) |
| Core events | `events/studio.py`, `events/catalog.py` (+SERIES_UPDATED/EPISODE_UPDATED) |
| Domain | `domain/studio/episode.py` (+edit()) |
| Authority | `orchestration/windagent_orchestration/studio/service.py` (validate create, update_series/update_episode) |
| Preflight | `apps/api/windagent_api/services/studio_preflight.py` (MỚI) |
| App service | `services/studio_application_service.py` (+update passthrough +preflight_start) |
| Composition | `composition/studio.py` (wire preflight) |
| Routers | `routers/v3/studio/{schemas,series,episodes,runs}.py` |

## 6. Verification

| Suite | Kết quả |
| --- | --- |
| `tests/integration/test_p0_4_studio_projects.py` (metadata/update semantics; provider/probe fail-closed; worker missing; worker unavailable; full capability PASS; START_BLOCKED; active-run resume under drift) | **PASS** trong focused matrix cuối |
| Studio regression (`test_studio_run_service.py` + contracts roundtrip) | **32 passed** |
| Vertical lifecycle thật (`test_v3_vertical_lifecycle_real.py`) | **1 passed** — `ProductionWorker` + production `WorkerContainer` + durable route lock/coordinator; chỉ provider network transport dùng deterministic adapter |
| Canonical Studio contracts/consumers đúng scope CI | **739 passed, 31 baseline skips, 0 FAILED** |
| ruff toàn bộ file thay đổi | clean |

Ghi chú trung thực:
- Trước P0.4, start run trong môi trường thiếu provider vẫn 202 rồi chết xuống queue; giờ bị chặn TRƯỚC với lý do rõ ràng — đây chính là behavior plan yêu cầu, vertical lifecycle test đã được cập nhật theo (thêm provider thật qua API).
- `test_phase7_projects_and_studio` giữ nguyên ignore như baseline (phụ thuộc demo seed).

## Gate

```text
P0_4_STUDIO_PROJECTS_USABLE = ACHIEVED
```

Next: **P0.5 — Real Story DAG** (verify inputs/outputs/artifact chain/pause-resume trên đường durable thật).
