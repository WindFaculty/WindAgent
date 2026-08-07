# Artifact Key Contract (Phase 18, §13)

**Gate:** `VP18_ARTIFACT_INVALIDATION_VERIFIED` — plan 05 §11–§16
**Module:** `storage/windagent_storage/video_production/key.py`

## 1. Key formula

```text
artifact_key = <key_version>:SHA256(
    canonicalize_input(canonical_input)
    + prompt_version
    + reference_hashes
    + model
    + generation_mode
    + generation_parameters
)
```

- `key_version` hiện tại: **`v1`** (`ARTIFACT_KEY_VERSION = "v1"`).
- Key được tính trên **intent/inputs**, không phải file bytes. Hai run cùng
  input → cùng key (reuse); đổi bất kỳ input nào → key khác (không reuse
  cache stale). File bytes được bảo vệ riêng bởi content SHA-256 trong record.

## 2. Canonicalization được pin

- `canonicalize_input`: JSON deterministic (sorted keys, compact separators).
- **List order được bảo toàn** — một screenplay scene sequence có thứ tự ngữ
  nghĩa; reorder là input khác (key khác). Caller muốn identity
  order-independent phải truyền list đã sort (vd `reference_hashes` — được
  sort riêng trong `compute_artifact_key`).
- Đổi canonicalization/algorithm/key format ⇒ **key version mới**, không
  reinterpret key cũ.

## 3. Tính injective

Toàn bộ 6 component được JSON-encode thành **một array duy nhất**
(`_stable_json([...])`), không join bằng separator. Điều này đảm bảo
injective: không tồn tại hai bộ component khác nhau cho cùng seed, kể cả khi
input chứa ký tự `|`, `"`, `,`, `[`, `]` — một lỗi separator-ambiguity đã
được bắt và sửa trong review.

## 4. Versioning — old keys never reinterpreted

- `compute_artifact_key(key_version="v99")` → `ValueError`.
- `key_matches(record_key, expected_key)`: so sánh **toàn bộ chuỗi** gồm cả
  version prefix — key `v1:...` không bao giờ khớp `v2:...`.
- `key_version_of(key)`: trả về prefix version hoặc `None`.

## 5. Gate usage

- Reuse (§14.4) chỉ khi `key_matches` (full key incl. version).
- Verifier chứng minh: cùng canonical input → reuse; đổi reference/prompt/
  model/parameter/screenplay → key khác.
