# Artifact Model Contract (Phase 18, §12)

**Gate:** `VP18_ARTIFACT_INVALIDATION_VERIFIED` — plan 05 §11–§16
**Module:** `storage/windagent_storage/video_production/model.py`

## 1. Artifact record

Một artifact record là nguồn sự thật duy nhất cho một artifact. Storage
locator **không phải public authority**; content hash + metadata record mới
là identity (§12).

```text
artifact_id            — id ổn định, không derive từ tên/đầu vào
artifact_type          — ArtifactType (PROJECT_RECORD … FINAL_DELIVERABLE)
content_sha256         — SHA-256 của payload (64 hex)
byte_size              — số byte payload
media_type             — MIME family
storage_locator        — content hash (content-address, không phải URL authority)
producer               — step/module tạo ra artifact
project_id / revision_id — scope project/revision
input_hashes           — hash các input đã dùng để tạo artifact
request_hash           — hash generation request (nếu có)
prompt_version         — version prompt template
compiler_version       — version prompt compiler
model_version          — version model provider
generation_mode        — GenerationMode
generation_parameters  — tham số generation (duration, aspect, …)
created_at             — thời điểm publish
validation_status      — PENDING | VALIDATED | INVALID
approval_status        — UNAPPROVED | APPROVED | REJECTED
status                 — VALID | STALE | SUPERSEDED
superseded_by          — artifact_id thay thế (khi SUPERSEDED)
artifact_key           — full content key (§13, gồm cả version prefix)
key_version            — pinned version của key algorithm
history                — audit append-only (không bao giờ xóa/sửa)
```

## 2. Status lifecycle

```text
                    publish (atomic)
  PENDING ────────────────────────────▶ VALIDATED/VALID
                                            │
              invalidation (§14.3)          │
              ├─────────────▶ STALE ────────┤
              └─────(có replacement)──────▶ SUPERSEDED
```

- `mark_stale()`: chỉ chuyển VALID → STALE, thêm history entry.
- `mark_superseded(replacement)`: chuyển → SUPERSEDED, gắn `superseded_by`.
- **Invalidation không bao giờ xóa artifact**; history append-only được giữ
  để garbage collection sau theo retention policy.

## 3. Serialization

- `to_dict()` / `from_dict()` round-trip đầy đủ.
- `from_dict()` **fail-closed** trên schema version major không khớp
  (`1.x` hiện tại) — record tương lai không bị reinterpret (§13 philosophy).
- Lưu ý determinism: mọi timestamp (`created_at`, history `at`) có thể được
  inject qua `clock` để verifier chứng minh byte-identical artifacts.

## 4. Fail-closed properties

1. Record chỉ `VALID` sau khi content file tồn tại **và** record được
   atomic-promote (§14.1) — không bao giờ có VALID record trỏ file thiếu.
2. History append-only — `ArtifactRecordStore.save` từ chối lưu làm history
   co lại (`history would shrink`).
3. `superseded_by` chỉ được đặt bởi `mark_superseded`, có audit.
