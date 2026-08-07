# Invalidation Contract (Phase 18, §14.3)

**Gate:** `VP18_ARTIFACT_INVALIDATION_VERIFIED` — plan 05 §11–§16
**Module:** `storage/windagent_storage/video_production/invalidation.py`

## 1. Nguyên tắc

Invalidation **không bao giờ xóa** artifact và **không bao giờ rewrite
history** (§14.3): nó chuyển record từ `VALID` sang `STALE` (hoặc
`SUPERSEDED` khi có replacement) và thêm audit entry — garbage collection
được thực hiện sau theo retention policy.

## 2. Change model

```text
change_type:
  SCREENPLAY_REVISION | CHARACTER_REFERENCE | BGM | PROMPT |
  MODEL | PARAMETER | REVISION
target_artifact_id     — cho change artifact-bound (bắt buộc)
domain_revision_hash   — cho change REVISION (bắt buộc)
reason                 — audit
```

`__post_init__` fail-closed: mỗi change type đòi đúng target field.

## 3. Minimal scope rules (§14.3)

| Change | Affected set |
|---|---|
| `SCREENPLAY_REVISION` | GENERATED_FROM chain downstream: cinematic plan → shot plan → prompt/request → frames/references → clips → final cut |
| `CHARACTER_REFERENCE` | **CHỈ** shots `CHARACTER_BINDING` với character đó + GENERATED_FROM downstream (clips/cuts) — shot không bind sống sót |
| `BGM` | audio mix + final cut qua `AUDIO_INPUT` (+ GENERATED_FROM downstream) — **visual clips không bao giờ bị ảnh hưởng** |
| `PROMPT` / `MODEL` / `PARAMETER` | GENERATED_FROM chain downstream của target |
| `REVISION` | mọi artifact có edge `REVISION` trỏ đúng domain_revision_hash |

## 4. Fail-closed

- **Unknown artifact target** (không phải graph node) → `ValidationError`
  TRƯỚC khi tính scope — một invalidation no-op im lặng sẽ che giấu staleness
  (bug này được review bắt 2 lần và sửa: ban đầu merge record_store làm yếu
  check, giờ chỉ `graph.has_node`).
- Affected artifact không có record → `ValidationError` khi apply.
- History append-only — không bao giờ xóa entry cũ.

## 5. Apply

- `invalidate(change, *, actor, supersede_with?)`:
  - với replacement (`supersede_with={artifact_id: replacement}`) → `SUPERSEDED`
    gắn `superseded_by`;
  - ngược lại → `STALE`;
  - mỗi record được lưu atomic; `InvalidationResult` trả về affected/marked/
    audit.
- Determinism: `clock` injectable; mọi history entry + audit timestamp qua
  `self._clock()` (verifier determinism proof dùng clock cố định).

## 6. Kiểm chứng gate

- Screenplay change → full chain stale, history tăng, không xóa.
- Character change → chỉ bound shots + cuts stale; shot không bind vẫn VALID.
- BGM change → audio mix + final cut stale; clip vẫn VALID.
- Unknown target / cycle → fail closed.
