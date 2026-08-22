# P0.3 — MODEL ROUTING RULES (completed)

**Gate:** `P0_3_MODEL_ROUTING_LIVE` ✅ **ACHIEVED**

**Ngày:** 2026-08-22 · Input: `docs/plans/p0_feature_truth_baseline.md`, `ban_ke_hoach_v1.md` §P0.3

---

## 1. P0.3.1 — Canonical Story roles

Contract mới: `core/windagent_core/contracts/studio/story_roles.py` — registry 8 role chuẩn khớp frozen `StudioTaskType` (giữ nguyên contract, đúng quy tắc "existing contract > new duplicate"):

```text
studio.story.idea.generate      ↔ capability "ideation"
studio.story.idea.evaluate      (hiện evaluate cục bộ, không qua LLM)
studio.story.bible.generate     ↔ "bibles"
studio.story.beats.generate     ↔ "beats"
studio.story.outline.generate   ↔ "outline"
studio.story.screenplay.generate↔ "screenplay"
studio.story.review             ↔ "review"   (alias plan: studio.story.screenplay.review)
studio.story.revise             ↔ "revise"   (alias plan: studio.story.screenplay.revise)
```

Cơ chế matching: `expand_role_labels()` mở rộng **context** (phía request) thành full equivalence class (role + alias + capability label). Rule giữ nguyên verbatim `role` làm label duy nhất → rule authored bằng canonical role HOẶC plan alias đều match capability ngắn từ prompt registry, mà không phá context thủ công của phase10.

API: `GET /api/v3/routing/roles` trả role list server-authority cho UI. `POST /providers/rules` normalize alias qua `normalize_story_role()` trước khi persist.

## 2. P0.3.2 — Rule là resource độc lập

Giữ nguyên: mỗi row trong `model_routing_rules_v3` = 1 rule độc lập (role, primary, fallback, priority, enabled) — không có global object hard-coded model names.

## 3. P0.3.3 — Không nhập canonical ID bằng text (UI)

Form "Assign model rule" trên RoutingPage viết lại hoàn toàn:

```text
Role select          ← GET /api/v3/routing/roles (8 story roles)
Primary provider     ← danh sách provider thật (useProviders)
Primary model        ← GET /providers/{id}/models (catalog đã discovery)
Fallback provider/model (optional) ← cùng cơ chế
```

Không còn text input "Discovered canonical model id". api-client thêm `routing.listStoryRoles()`, `routing.listReceipts()`; hooks thêm `useStoryRoles`, `useProviderModels`; contracts thêm `StoryRoleResource`, `RouteReceiptResource`.

## 4. P0.3.4 — Resolution order + FAIL CLOSED

```text
exact role rule (SQL model_routing_rules_v3, priority thấp trước)
      ↓ không match
system default (env WINDAGENT_STUDIO_CANONICAL_MODEL, append MỘT LẦN priority 10_000
                qua compose_story_ruleset(); SQL rules vẫn thắng default)
      ↓ không match
RoutingUnavailableError (code ROUTING_UNAVAILABLE) — fail closed, KHÔNG chọn model ngẫu nhiên
```

- Worker composition (`composition/studio.py`) giờ compose SQL ruleset + system-default thay vì env override đè toàn bộ.
- `NoMatchingRuleError`/`CanonicalModelDisabledError` ở port được chuẩn hóa thành `RoutingUnavailableError` (core); `StoryModelBoundary` để lỗi này xuyên qua nguyên vẹn (không wrap transient-retryable sai semantics); worker `_execute` map thành error code `ROUTING_UNAVAILABLE`.
- API simulate trả 404 kèm `{"code": "ROUTING_UNAVAILABLE"}` trong detail.
- Test tripwire migration head bump 0015 → **0017_route_receipts** (0016 trước đó chưa cập nhật tripwire).

## 5. P0.3.5 — Fallback semantics (đúng định nghĩa)

Chỉ fallback khi failure thuộc `FALLBACK_ELIGIBLE_FAILURES`:

```text
NetworkFailure | TimeoutFailure | ProviderUnavailableFailure |
RateLimitFailure | SameModelEndpointExhausted   (endpoint unavailable /
timeout / rate limit / temporary provider failure / hết endpoint tương đương)
```

KHÔNG fallback với schema validation (`InvalidRequestFailure`, `ContextOverflowFailure`), auth, safety, malformed response… — re-raise ngay.

Cơ chế: `RouteLockService.create_fallback_lock()` tạo lock pin riêng (scope_type `studio_model_fallback`, snapshot `fallback:true` + `source_lock_id`, audit action=`fallback`) — primary lock KHÔNG BAO GIỜ mutate (invariant canonical never changes vẫn đứng). `RouteLockedModelPort._execute_rule_fallback` đọc `rule.fallback_model_id` từ matched rule rồi chạy coordinator lần nữa; fail của fallback không che lỗi gốc. Kết quả gắn `usage.fallback_used/fallback_reason`.

`RoutingRule.fallback_model_id` là field additive mới; `RoutingPolicyProjection` populate từ `ModelRuleRecord.fallback_canonical_model_id`.

## 6. P0.3.6 — Route receipt persist

Bảng mới `model_route_receipts_v3` (migration `0017_route_receipts`, additive/idempotent):

```text
task_id, role, rule_id, route_lock_id (FK route_locks_v3),
selected_provider, selected_model_id, provider_model_id, endpoint_id,
fallback_used, fallback_reason, status(success|failed), error_code,
started_at, completed_at
```

- Ghi bởi chính executor thật (`RouteLockedModelPort`) sau success VÀ cả failure (status=failed + error_code) — không bao giờ fabricate.
- Repo: `SQLModelRouteReceiptRepository` (+alias `SqlModelRouteReceiptRepository`), ORM `ModelRouteReceiptV3ORM`, DI `get_route_receipt_repository`.
- Đọc: `GET /api/v3/routing/receipts?task_id=&role=&limit=`.
- `/metrics` viết lại: tính THẬT từ receipts + rules (total_routes, success rate, latency trung bình, traffic distribution group-by model). Hết thời đại 27.000 routes hard-coded.
- `/graph` bỏ 6 node role cứng — derive từ agent_types/task_labels của rule thật.
- WS `/ws/v3/model-infra`: heartbeat canned chỉ còn khi `WINDAGENT_PROFILE=demo`; ngoài demo fail-closed (`model_infra.unavailable`).

## 7. Code map

| Layer | File |
| --- | --- |
| Core contract | `core/windagent_core/contracts/studio/story_roles.py` (MỚI: roles, aliases, expand_role_labels, RoutingUnavailableError, ROUTING_UNAVAILABLE) |
| Rule runtime | `providers/windagent_providers/routing/rules.py` (+fallback_model_id), `route_lock_service.py` (+create_fallback_lock) |
| Projection | `management/policy_projection.py` (+fallback_model_id, strip role) |
| Port | `apps/worker/windagent_worker/studio_model_port.py` (context expansion, fallback execution, receipts, compose_story_ruleset) |
| Worker runtime/composition | `studio_runtime.py` (map ROUTING_UNAVAILABLE), `composition/studio.py` (resolution order + receipt repo + bindings cho cả fallback model) |
| Storage | ORM `v3_models.py` (+ModelRouteReceiptV3ORM), repo `v3_routing_repositories.py` (+SQLModelRouteReceiptRepository), migration `0017_route_receipts.py` (MỚI) |
| API | `routers/v3/routing.py` (+/roles, /receipts, metrics/graph thật, WS gate), `providers.py` (normalize role), `dependencies.py`, `composition/repositories.py`, `composition/container.py` |
| Intelligence | `story/prompts/structured.py` (passthrough RoutingUnavailableError) |
| FE contracts/client/hooks | `routing.ts` (+2 types), `client.ts` (+2 methods), `useProviders.ts` (+useStoryRoles/useProviderModels) |
| FE UI | `RoutingPage.tsx` — form rule: Role select + Provider→Model selector (primary + fallback) |

## 8. Verification

| Suite | Kết quả |
| --- | --- |
| `tests/integration/test_p0_3_model_routing.py` (10 test mới: alias match, plan-alias normalize, exact-vs-system-default, fail-closed, boundary passthrough, fallback timeout→receipt đầy đủ, schema-no-fallback, compose dedupe, API receipts+roles, alembic head) | **10 passed** |
| Provider unit + Worker unit + phase10 integration | **294 passed** |
| Migration integrity suite | **37 passed, 1 skipped** (tripwire head = 0017) |
| Full `tests/contracts` (ignore phase7/phase16/code-video như baseline) | **539 passed, 31 skipped** (test_get_routing_metrics viết lại theo truthful semantics) |
| ruff toàn bộ file thay đổi | clean |
| Frontend workspaces vitest | all pass (119 test) |
| Frontend typecheck toàn workspace + Desktop `tsc -b --noEmit` + build | PASS / PASS |

Ghi chú trung thực:
- `test_get_routing_metrics` (phase12) trước đây assert số liệu fabricated (27k routes, success 99.7%) — viết lại để assert truthful metrics; đây chính là behavior P0 yêu cầu ("không fake metrics"), không phải test break.
- `test_lock_route_rejects_disabled_model_fail_closed` đổi expect sang `RoutingUnavailableError` — semantic P0.3.4 (disabled model = không có route hợp lệ → fail-closed typed).
- Receipt FK về `route_locks_v3.id`: SQLite test mặc định không enforce FK nên InMemoryLockStore vẫn dùng được trong unit/integration; production worker dùng `SQLRouteLockRepository` nên FK luôn thỏa.

## Gate

```text
P0_3_MODEL_ROUTING_LIVE = ACHIEVED
```

Next: **P0.5 — Real Story DAG** (song song được với P0.4 Series/Episode metadata + preflight START_BLOCKED).
