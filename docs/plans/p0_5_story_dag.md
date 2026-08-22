# P0.5 — REAL STORY PIPELINE (completed)

**Gate:** `P0_5_STORY_DAG_REAL` ✅ **ACHIEVED**

**Ngày:** 2026-08-22 · Input: `ban_ke_hoach_v1.md` §P0.5, baseline §2.4

---

## Kết luận xác minh

Đường Story DAG thật **đã tồn tại và chạy được khi flag bật** từ trước (`WINDAGENT_STUDIO_RUNTIME=1` + `WINDAGENT_STUDIO_MODEL_ROUTE=1`, fail-closed trung thực khi thiếu). P0.5 theo plan là **COMPLETE + VERIFY**, không redesign. Các mục dưới đây được xác minh bằng test chạy trên đường durable thật (API → queue → worker → router → port → persistence), không qua mock path.

## 1. Canonical DAG

```text
idea.generate → idea.evaluate → WAIT_FOR_IDEA_SELECTION
  → bible.generate → beats.generate → outline.generate
  → screenplay.generate → screenplay.review (→ revise loop bounded) → lock
```

- Không bypass worker: mọi node đi qua `SqlDurableTaskQueue` (claim `FOR UPDATE SKIP LOCKED`, lease + fencing token, outbox dedup `studio_submit:<run>:<node>:<attempt>`).
- Selection là A-command có CAS (revision_id + candidate_id + expected_content_hash + expected_optimistic_version) — giữ nguyên semantics.

## 2. P0.5.1 — Inputs từ authoritative artifacts

`StudioRuntimeAdapter._load_inputs` đọc đúng bảng `INPUT_TYPES_BY_TASK` (frozen story_task_io): mỗi task nhận artifact đầu vào đã persist (SelectedIdea, StoryBible+World+Canon, BeatSheet, Outline, Draft+ReviewReport) + CreativeBrief từ episode metadata/envelope; thiếu input → `STUDIO_INPUT_ARTIFACT_MISSING` fail-closed. Không đọc ngầm global state.

## 3. P0.5.2 — Structured outputs

Provider raw response → `StoryModelBoundary`: safety check → parse JSON với tối đa 1 bounded syntax repair (fence/leading-object/first-brace) → `jsonschema` validate theo output_schema khai báo trong prompt registry → domain validators → envelope. Invalid sau repair → `STORY_SCHEMA_FAILURE` (terminal), không persist garbage rồi tiếp tục DAG.

## 4. P0.5.3 — Durable artifact chain

`StoryArtifactEnvelope` (frozen, content-addressed) chứa đủ:

```text
artifact_id, artifact_type, schema_version,
series_id, episode_id, revision_id,
input_artifact_refs (parent/input hashes), content_hash (64 hex),
prompt_id/version/hash, model_route/provider/binding/attempt provenance,
created_at, created_by, output_schema_contract
```

Vertical lifecycle test assert từng artifact gắn đúng episode/revision, hash hợp lệ; route provenance persist kèm artifact (model_route_id, provider_id, usage…).

## 5. P0.5.4 — Crash/resume (Scenario E chạy thật)

Test mới `tests/integration/test_p0_5_story_dag_resume.py` — file-backed DB, container thật, FixtureModelPort worker:

```text
start run → Worker#1 xử lý ĐÚNG 1 task rồi "crash" (không poll nữa)
→ start_or_resume_run gọi lại lúc run còn RUNNING:
   cùng run_id, resuming=true, số task_runs KHÔNG tăng
   (resume không re-submit node đã committed — outbox dedup)
→ Worker#2 (instance mới) resume → lock SUCCEEDED
   → mỗi stage ĐÚNG 1 artifact (hash unique toàn cục;
      IdeaCandidateSet = 2 hợp lệ: generate + evaluate)
   → SCREENPLAY_LOCKED event ĐÚNG 1 lần
   → episode LOCKED / READY_FOR_PRODUCTION
```

Storage-restart sau hoàn tất (asserts 33–37) do vertical lifecycle test bảo vệ sẵn.

## 6. Verification

| Suite | Kết quả |
| --- | --- |
| `tests/integration/test_p0_5_story_dag_resume.py` (crash prefix → same-run resume, no re-submit, no duplicate artifact/event, terminal state) | **1 passed** |
| `tests/contracts/test_v3_vertical_lifecycle_real.py` (full DAG + restart + immutability) | **passed** |
| Full `tests/contracts` (ignore phase7/phase16/code-video) | **540 passed** |

Ghi chú trung thực:
- Run COMPLETED là terminal: start tiếp theo trên episode đó tạo run MỚI cho revision hiện hành (thiết kế C7 auto-drive) — KHÔNG phải "resurrection" của run cũ; durability contract của P0.5.4 áp dụng cho resume run non-terminal và đã được khóa bằng test.
- Hai `IdeaCandidateSet` artifacts là thiết kế đúng (idea.generate emit set thô; idea.evaluate emit set đã chấm điểm), nội dung khác nhau nên content-hash vẫn unique.

## Gate

```text
P0_5_STORY_DAG_REAL = ACHIEVED
```

Next: **P0.6 — Review/Revision/Approval/Lock semantics (+ fix `issued_at`).**
