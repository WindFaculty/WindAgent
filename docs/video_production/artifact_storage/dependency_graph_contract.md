# Artifact Dependency Graph Contract (Phase 18, §14.2)

**Gate:** `VP18_ARTIFACT_INVALIDATION_VERIFIED` — plan 05 §11–§16
**Module:** `storage/windagent_storage/video_production/graph.py`

## 1. Edge model

```text
artifact_id           — artifact phụ thuộc
depends_on_artifact_id — input artifact (XOR với revision hash)
domain_revision_hash   — input revision hash (XOR với artifact id)
dependency_type        — GENERATED_FROM | REVISION | REFERENCE |
                         CHARACTER_BINDING | AUDIO_INPUT
reason                 — lý do edge (audit)
```

Mỗi edge phải có **đúng một** trong hai target (`__post_init__` fail-closed).

## 2. Dependency types & propagation semantics (§14.3)

| Type | Ý nghĩa | Lan truyền khi thay đổi |
|---|---|---|
| `GENERATED_FROM` | artifact là sản phẩm trực tiếp của artifact khác | chain downstream |
| `REVISION` | artifact phụ thuộc domain revision hash | artifact phụ thuộc hash đó |
| `REFERENCE` | artifact tham chiếu artifact khác | scope tới dependents |
| `CHARACTER_BINDING` | shot được bind với character bible | **CHỈ** các shot bound + downstream cuts |
| `AUDIO_INPUT` | audio artifact feed mix/final cut | audio mix + final cut, **không bao giờ** visual clips |

## 3. Queries

- `outbound(artifact_id)` — inputs của artifact.
- `inbound(artifact_id)` — dependents trực tiếp.
- `inbound_by_type(artifact_id, types)` — dependents theo loại edge.
- `transitive_inbound(artifact_id, types?)` — toàn bộ dependents; với bộ
  lọc type, traversal chỉ đi theo edges thuộc loại đó ⇒ **minimal scope**
  (§14.3: BGM không bao giờ lan qua visual-clip edges).
- `has_node(artifact_id)` — public membership check.

## 4. Fail-closed

- **Unknown node** (bất kỳ phía nào) → `ValidationError` tại `add_edge`.
- **Cycle** → `ValidationError` tại `add_edge` / `validate` (DFS toàn đồ thị).
- `validate()` kiểm tra toàn bộ: node tồn tại, target tồn tại, acyclic.

## 5. Scope helpers (kiểm chứng §14.3)

- `build_character_scope(graph, character_id)` → `(bound_shots,
  downstream_cuts)`: character change chỉ ảnh hưởng shots có
  `CHARACTER_BINDING` với character đó + GENERATED_FROM downstream của chúng
  — **không bao giờ** shots không bind.
- `build_bgm_scope(graph, bgm_id)` → `[audio mix, final cut]`: đi theo
  `AUDIO_INPUT` edges + GENERATED_FROM dependents — **visual clips sống sót**.

## 6. Serialization

`to_dict()` / `from_dict()` round-trip; nodes + edges đầy đủ; deterministic
(sort nodes, thứ tự edges giữ nguyên).
