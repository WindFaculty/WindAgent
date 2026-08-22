# P0.7 — FRONTEND PRODUCT CONVERGENCE

**Gate:** `P0_7_DESKTOP_VERTICAL_FLOW_LIVE` 🟢 **PASS**

**Ngày:** 2026-08-22 · Input: baseline §2.5 & Ban kế hoạch P0.7

---

## 1. ĐÃ XÓA đường pipeline giả (Server Authority 100%)

Hiện trạng sau P0.7:

```text
Start buttons (IDEA/BIBLE/OUTLINE/SCREENPLAY)
      ↓ client.studio.preflightStart(episodeId)     ← GET /api/v3/studio/.../preflight
      ↓ START_BLOCKED? → banner đỏ liệt kê reasons[] (không enqueue)
      ↓ client.studio.startRun(...)                  ← POST /api/v3/studio/episodes/{id}/runs (202 durable)
      ↓ invalidate + refetch
```

- UI KHÔNG tự quyết state transition — mọi action theo server authority (preflight report + run receipt).
- Bỏ fallback ID cứng `'ep-cb-001'` trong workspace page.
- Kết nối tất cả các mutation quyết định sang Canonical Studio endpoints:
  - `selectIdea` → `POST /api/v3/studio/episodes/{id}/idea-selection` (với `candidate_id`, `expected_content_hash`, `expected_optimistic_version`).
  - `recordApproval` → `POST /api/v3/studio/episodes/{id}/approvals` (với `checkpoint`, `artifact_hash`, `decision: APPROVED|REVISE|REJECTED`, `reason`, `expected_optimistic_version`).
  - `deriveRevision` → `POST /api/v3/studio/episodes/{id}/revisions` (với `parent_revision_id`, `new_content_hash`, `summary`, `expected_optimistic_version`).
  - `lockScreenplay` → `POST /api/v3/studio/episodes/{id}/screenplay-lock` (với `expected_content_hash`, `expected_optimistic_version`).

## 2. Bỏ fabricate lock hash (Cryptographic & Revision Authority)

`CheckpointReviewPanel` trước đây tự tạo `sha256-${crypto.randomUUID()}` làm content_hash khi lock. Nay:

- Panel nhận `screenplayContentHash` từ artifact thật (canonical studio artifacts có `content_hash`);
- Không có hash từ server → nút Lock DISABLED kèm tooltip — frontend không bao giờ bịa hash.
- Giao diện hỗ trợ đầy đủ các trạng thái phê duyệt, yêu cầu đạo diễn AI sửa đổi kèm phản hồi văn bản, và khóa kịch bản phục vụ sản xuất.

## 3. Artifacts & Panels chuyển sang canonical authority

- `useEpisode` đọc canonical `GET /api/v3/studio/episodes/{id}` và ánh xạ trạng thái sang checkpoint pipeline (`IDEA`, `STORY_BIBLE`, `OUTLINE`, `SCREENPLAY`, `REVIEW`, `LOCKED`, `READY_FOR_PRODUCTION`).
- `useEpisodeArtifacts` đọc `GET /api/v3/studio/episodes/{id}/artifacts` (content-addressed envelope: content_hash, revision, route provenance).
- `IdeaPanel`: Hỗ trợ cả schema `candidates` và `ideas`, hiển thị điểm khớp kịch bản (match score badge), tone thể loại và nút chọn ý tưởng chuẩn hóa.
- `StoryBiblePanel`: Render đầy đủ `premise`, `theme`, `tone`, `arc_summary`, `stakes`, `story_rules` và danh sách nhân vật.
- `OutlinePanel`: Render các phân cảnh `scenes` với thời lượng (`estimated_seconds`), mục tiêu (`intent`), hành động thị giác (`visual_action`) và nút thắt xung đột (`conflict_change`).
- `ScreenplayPanel`: Trình bày kịch bản chuẩn điện ảnh bao gồm tiêu đề cảnh quay, mô tả hành động, lời dẫn truyện (`narration`), lời thoại kèm sắc thái biểu cảm (`delivery`), và chuyển cảnh (`transition`).

## 4. UX States & Realtime Synchronization

Tất cả các trạng thái UX bắt buộc đã được cài đặt đầy đủ:
- **Loading / Skeleton**: Hiển thị khi đang tải dữ liệu episode hoặc studio series.
- **Offline / Polling Alert**: Tự động thông báo khi kết nối WebSocket gián đoạn và kích hoạt cơ chế polling đồng bộ định kỳ.
- **Failed State Banner**: Hiển thị thông báo lỗi chi tiết kèm nút `Thử lại / Khôi phục Run` từ checkpoint bền vững.
- **Waiting For Input (Idea Selection)**: Banner nổi bật hướng dẫn người dùng chọn tiền đề kịch bản.
- **Preflight START_BLOCKED**: Banner cảnh báo liệt kê chi tiết các điều kiện chưa thỏa mãn trước khi bắt đầu run.

## 5. Studio Home & Series Management

- **Studio Home**: Chuyển đổi thành trung tâm quản trị Series với các chỉ số đo lường trung thực (không fake metrics):
  - `Active Series`: Số lượng series đang hoạt động.
  - `Tập Đang Sản Xuất`: Số lượng episode ở các bước Draft, Ideation, Review, Revision.
  - `Chờ Phê Duyệt`: Số lượng episode đang chờ kiểm định ở các checkpoint.
  - `Sẵn Sàng Sản Xuất`: Số lượng episode đã hoàn thành và khóa kịch bản (`READY_FOR_PRODUCTION`).
- **CreateSeriesDialog**: Modal tạo Series kịch bản mới với đầy đủ thể loại (genre), âm hưởng (tone), đối tượng khán giả (target audience) và ngôn ngữ (language).
- **Navigation Flow**: Click vào episode trong bất kỳ danh sách hay trang chi tiết Series nào đều điều hướng trực tiếp và chính xác đến `/episodes/${episodeId}`.

## 6. Verification Matrix

| Suite | Kết quả | Chi tiết |
| --- | --- | --- |
| Frontend workspaces vitest | PASS | 22 test files, **119 tests**: `@windagent/app` 52 + api-client 20 + api-contracts 5 + realtime 8 + studio-shell 11 + ui 23 |
| Frontend Typecheck | PASS | `npm --prefix frontend run typecheck` (0 errors) |
| Desktop Vitest | PASS | **4 test files, 27 tests**; mocks dùng canonical `/api/v3/studio/series`, không còn legacy `/api/v3/projects` |
| Desktop Typecheck | PASS | `npm --prefix apps/desktop run type-check` (`tsc -b --noEmit`, 0 errors) |
| Desktop Production Build | PASS | `npm --prefix apps/desktop run build` (`vite build`, 0 errors) |

## Gate

```text
P0_7_DESKTOP_VERTICAL_FLOW_LIVE = PASS
```

