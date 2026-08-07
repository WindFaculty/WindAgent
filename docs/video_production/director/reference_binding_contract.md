# Reference Binding Contract (Phase 11)

> Kế hoạch: `docs/video_production/plans/03_phase_08_11_director_layer.md` §24.1.
> Module: `intelligence/windagent_intelligence/video/reference_selector/`.

## 1. Mục đích

`ReferenceBindingPlanner` gắn (bind) từng **asset đã APPROVED và đúng revision**
vào từng shot theo **content hash**, trước khi prompt compiler sinh
`GenerationRequest`. Một shot chỉ compile khi toàn bộ reference bắt buộc của
nó đã được bind hợp lệ — **fail closed**: candidate, asset bị reject, stale
(hash thay đổi) hoặc sai revision không bao giờ vào request.

## 2. Pipeline

```text
ShotSpecification (+ package + Phase 9 graph)
        ↓
ReferenceBindingPlanner.plan()
        ↓
ReferenceBindingPlanReceipt  (bindings + issues + binding_hash)
        ↓
PromptCompiler.compile_all()  (từ chối nếu còn blocking issue)
```

## 3. Mô hình binding

Mỗi binding (`ReferenceBinding`) ghi:

```text
binding_id            deterministic (shot:asset:role)
shot_id               shot được bind
asset_id              asset được bind
asset_hash            SHA-256 content hash tại thời điểm bind
role                  IDENTITY | LOCATION | PROP | STYLE |
                      FIRST_FRAME | LAST_FRAME | INGREDIENT | PREDECESSOR_CLIP
required              true/false theo generation mode
source_revision       revision package gốc
crop_usage_intent     ví dụ "identity reference", "location reference"
approval_state        AssetLifecycleState (chỉ APPROVED / BOUND_TO_PROJECT hợp lệ)
```

`ReferenceBindingPlan` là aggregate bất biến cho cả revision: danh sách
bindings, issues, `binding_hash`, và các source hash (graph/plan/package).

## 4. Luật validator (`ReferenceBindingValidator`)

| Rule | Code | Blocking |
|---|---|---|
| Asset không tồn tại trong package | `UNKNOWN_ASSET` | ✅ |
| Asset chưa APPROVED (candidate/rejected/license-unknown) | `NOT_APPROVED` | ✅ |
| Hash ghi trong binding khác hash hiện tại của asset | `STALE_HASH` | ✅ |
| Source revision khác revision của plan | `WRONG_REVISION` | ✅ |
| Trùng binding (shot, asset) | `DUPLICATE_BINDING` | ✅ |
| Thiếu binding bắt buộc của shot | `MISSING_REQUIRED_BINDING` | ✅ |

Mọi code trên đều **blocking**. Planner raise `ValidationFailureError` nếu có
blocking issue — không bao giờ publish plan chưa hoàn chỉnh.

## 5. Phân loại role

- Asset trong `character.portrait_asset_ids` → `IDENTITY` (required).
- Asset trong `location.reference_asset_ids` → `LOCATION` (required).
- Asset trong `prop.reference_asset_ids` → `PROP` (required).
- Asset trong `style_bible.reference_asset_ids` → `STYLE` (required).
- Asset còn lại được shot tham chiếu → `INGREDIENT` (required chỉ khi shot
  dùng asset như ingredient trong execution intent).

## 6. Approval state

Assets trong package (qua Phase 7 asset pipeline) mặc định được coi là
`APPROVED`/`BOUND_TO_PROJECT` vì pipeline chỉ đưa asset đã validate vào
package. Caller có thể truyền `asset_approval: Dict[asset_id, state]` để ép
một asset cụ thể ở trạng thái `REJECTED`/`LICENSE_UNKNOWN` — test và verifier
dùng cơ chế này để chứng minh fail-closed.

## 7. Hash và reproducibility

```text
binding_hash = SHA256(
    project_id + revision_id
    + binding_version
    + source_graph_hash + source_plan_hash + source_package_hash
    + bindings (canonical, sort_keys)
)
```

Cùng input → cùng hash. Đổi reference, role, version hoặc source hash → hash
mới (§24.5 invalidation ở mức binding).

## 8. Contract receipt

`artifacts/video_production/phase_11/reference_binding_receipt.json`:

- 3 golden fixtures bind đủ IDENTITY/LOCATION, hash khớp, không blocking;
- negative: asset REJECTED → `NOT_APPROVED`; asset lạ → `UNKNOWN_ASSET`;
- binding hash deterministic và thay đổi khi reference thay đổi.
