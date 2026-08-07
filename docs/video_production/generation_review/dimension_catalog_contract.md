# Review Dimension Catalog Contract (plan 05 §23) — Phase 20

Gate: `VP20_GENERATION_REVIEW_VERIFIED`

## 1. Mục đích

`REVIEW_DIMENSIONS` (trong
`intelligence/windagent_intelligence/video/reviewers/dimensions.py`) là
**catalog versioned** gồm đủ **11 review dimensions** (plan 05 §23). Mỗi
dimension khai báo reviewer type, PASS threshold, confidence floor và cờ
**blocking rule** — verdict/selection/rejection đều dựa vào catalog này, không
hard-code số liệu trong domain invariant.

## 2. 11 dimensions (plan §23)

```text
TECHNICAL_VALIDITY   deterministic  threshold 1.0  blocking  (decoder/hash/stream/duration/…)
SAFETY               deterministic  threshold 1.0  blocking  (safety file checks)
PROMPT_COMPLIANCE    VLM            threshold 0.7  blocking
IDENTITY_CONSISTENCY VLM            threshold 0.7  blocking
LOCATION_CONSISTENCY VLM            threshold 0.7  blocking
PROP_CONSISTENCY     VLM            threshold 0.7  blocking
CONTINUITY           cross-shot     threshold 1.0  blocking  (continuity ledger)
MOTION_QUALITY       VLM            threshold 0.6  non-blocking
CAMERA_COMPLIANCE    VLM            threshold 0.7  blocking
DIALOGUE_ALIGNMENT   VLM            threshold 0.6  non-blocking
VISUAL_ARTIFACTS     VLM            threshold 0.6  non-blocking
```

Mỗi `DimensionConfig` gồm: `dimension`, `reviewer_type`, `pass_threshold`,
`confidence_floor`, `blocking`. `config_for(dimension)` fail closed với
dimension không biết.

## 3. Versioning (plan §26)

`REVIEW_POLICY_VERSION = "1.0.0"`. **Một thay đổi threshold/policy phải tạo
version mới** — review result cũ không bao giờ bị sửa. `review_id` gắn
candidate + policy version (`rv_{candidate_id}:{policy_version}`) nên cùng một
candidate re-review dưới policy mới tạo **revision mới**, không collision.

## 4. Blocking rule

`BLOCKING_DIMENSIONS` là tập bất biến các dimension blocking. Một blocking
defect **luôn thắng** aggregate preference (plan §25.4): candidate có average
score cao nhưng vi phạm blocking rule vẫn REJECT, không auto-select.

## 5. Kiểm chứng (verifier)

- `dimension_catalog_receipt.json`: đủ 11 dimensions, mỗi dimension có
  threshold + confidence floor + blocking flag; catalog version cố định;
  `config_for` fail closed.
