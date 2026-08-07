# Cost Catalog Contract (plan 05 §19.1) — Phase 19

Gate: `VP19_COST_AND_QUOTA_CONTROL_VERIFIED`

## 1. Mục đích

Catalog giá/credit là **provider configuration** có thời điểm hiệu lực và
provenance — **không hard-code** số liệu dễ thay đổi vào domain invariant
(plan 05 §18). Module: `orchestration/windagent_orchestration/production/cost_catalog.py`.

## 2. Cấu trúc entry

Mỗi `CostCatalogEntry`:

```text
provider                 # "flow", ...
model                    # "video-v2", ...
operation                # "video_generation", "image_generation", ...
mode                     # "standard" | "quality"
candidate_semantics      # "per_candidate" | "per_request"
base_credits             # credit nền
per_second_credits       # credit mỗi giây duration
per_reference_credits    # credit mỗi reference/image generation
post_production_credits  # credit nếu hậu kỳ có external cost
effective_at             # ngày hiệu lực (ISO date)
source                   # "observed" | "vendor_doc"
confidence               # 0..1
```

## 3. Luật lookup

`CostCatalog.rule_for(provider, model, operation, mode, effective_at)`:

- khớp chính xác 4 trường đầu (provider/model/operation/mode);
- nếu `effective_at` được cung cấp, chỉ nhận entry có `effective_at <=` ngày đó;
- chọn entry có `effective_at` mới nhất;
- **không có rule khớp → trả `None`** — estimator báo `UNKNOWN` và budget
  policy chặn submit (fail closed, §19.1).

## 4. Versioning & staleness

- `CostCatalog.signature()` = SHA-256 của (schema version + signature từng entry).
- Estimate lưu `catalog_signature` tại thời điểm tính; khi catalog đổi,
  signature đổi → estimate (và approval gắn estimate hash của nó) trở thành
  stale (§19.2).
- Catalog đổi rule = thêm entry mới có `effective_at` mới — không sửa entry cũ.

## 5. Kiểm chứng (verifier)

- `cost_catalog_receipt.json`: rule khớp đúng, unknown rule → `None`,
  signature thay đổi khi thêm entry, lookup deterministic.
