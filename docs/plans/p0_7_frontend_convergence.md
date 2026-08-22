# P0.7 — FRONTEND PRODUCT CONVERGENCE (partial)

**Gate:** `P0_7_DESKTOP_VERTICAL_FLOW_LIVE` ◐ **PARTIALLY ACHIEVED**

**Ngày:** 2026-08-22 · Input: baseline §2.5 (⚠️ phát hiện nghiêm trọng: frontend drive pipeline giả)

---

## 1. ĐÃ XÓA đường pipeline giả (mục tiêu số 1 của P0.7)

Baseline phát hiện: `EpisodeWorkspacePage` gọi legacy stub `POST /api/v3/episodes/{id}/start-generation` (instant COMPLETED, không gọi model). Hiện trạng sau P0.7:

```text
Start buttons (IDEA/BIBLE/OUTLINE/SCREENPLAY)
      ↓ client.studio.preflightStart(episodeId)     ← GET /api/v3/studio/.../preflight
      ↓ START_BLOCKED? → banner đỏ liệt kê reasons[] (không enqueue)
      ↓ client.studio.startRun(...)                  ← POST /api/v3/studio/episodes/{id}/runs (202 durable)
      ↓ invalidate + refetch
```

- UI KHÔNG tự quyết state transition — mọi action theo server authority (preflight report + run receipt).
- Bỏ fallback ID cứng `'ep-cb-001'` trong workspace page.

## 2. Bỏ fabricate lock hash (BROKEN semantics → FIXED)

`CheckpointReviewPanel` trước đây tự tạo `sha256-${crypto.randomUUID()}` làm content_hash khi lock. Nay:

- Panel nhận `screenplayContentHash` từ artifact thật (canonical studio artifacts có `content_hash`);
- Không có hash từ server → nút Lock DISABLED kèm tooltip — frontend không bao giờ bịa hash.

## 3. Artifacts chuyển sang canonical authority

`useEpisodeArtifacts` đọc `GET /api/v3/studio/episodes/{id}/artifacts` (content-addressed envelope: content_hash, revision, route provenance) thay cho legacy demo namespace; shape được normalize (`kind`/`content`) nên các panel IdeaPanel/StoryBiblePanel/OutlinePanel/ScreenplayPanel giữ nguyên.

## 4. Routing surfaces (từ P0.1–P0.3)

- ProvidersPage viết lại hoàn toàn (không còn alias RoutingPage): lifecycle đầy đủ + conflict flow khi delete.
- ModelsPage: catalog thật + pricing filter FREE/PAID/UNKNOWN + Test Model per binding.
- RoutingPage rule form: Role select (server `/routing/roles`) + Provider→Model selector (primary + fallback) — hết nhập canonical ID tay.

## 5. api-client / contracts mới

| Surface | Methods |
|---|---|
| StudioApi | listSeries/createSeries/updateSeries/getSeries · listEpisodes/createEpisode/getEpisode/listEpisodeArtifacts · preflightStart · startRun |
| RoutingApi | listStoryRoles · listReceipts |
| Contracts | StoryRoleResource, RouteReceiptResource, StudioSeries*, StudioEpisode*, StudioPreflightReport |

## 6. CÒN LẠI (truthful — chưa đóng gate)

1. **Episode state vẫn đọc legacy**: `useEpisode` → `/api/v3/episodes/{id}` (namespace demo-seeded). Cần switch sang `GET /studio/episodes/{id}` + ánh xạ state/checkpoint.
2. **StudioHome chưa phải Series-domain home**: vẫn landing Projects; thiếu sections Active Series / In-progress / Pending approval / Ready-for-production (methods client đã có sẵn).
3. Legacy stub `start-generation` vẫn tồn tại server-side (UI đã ngừng dùng) — cần remove/gate ở đợt dọn hardening.

## 7. Verification

| Suite | Kết quả |
| --- | --- |
| Frontend workspaces vitest | all pass (app 52 tests gồm episode workspace suite) |
| Typecheck toàn bộ workspaces + Desktop `tsc -b --noEmit` | PASS |
| Desktop build (vite) | PASS |

## Gate

```text
P0_7_DESKTOP_VERTICAL_FLOW_LIVE = PARTIALLY ACHIEVED
(đường chạy thật đã nối; còn 3 mục mục 6 để đóng hoàn toàn)
```
