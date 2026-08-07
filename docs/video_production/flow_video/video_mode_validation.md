# Video Mode Validation — Flow Video Generation (Phase 15, plan 04 §23.2)

- **Gate:** `VP15_FLOW_VIDEO_GENERATION_VERIFIED`
- **Module:** `tools/windagent_tools/google_flow/video_operations.py`
  (`VideoOperationMapper.validate_mode`)

## Mục đích

Mọi video request phải vượt mode validation **fail-closed** TRƯỚC khi
navigator chạy và TRƯỚC khi submit được click. Một issue → generator raise
`FlowVideoModeValidationError` với danh sách `FlowVideoModeIssue` typed;
không có gì được submit.

## Inputs

- `request.reference_bindings` — (role, content_hash).
- `approved_hashes` — tập content hash của approved assets (từ approved
  asset store / composition root). Binding có hash không nằm trong tập này
  được coi là **chưa approved** và chặn mode.

## Rules theo mode

| Mode | Yêu cầu | Issue codes |
|---|---|---|
| `TEXT_TO_VIDEO` | Không cần binding | — |
| `FRAMES_TO_VIDEO` | FIRST_FRAME + LAST_FRAME, cả hai approved | `MISSING_FIRST_FRAME`, `MISSING_LAST_FRAME`, `FIRST_FRAME_NOT_APPROVED`, `LAST_FRAME_NOT_APPROVED`, `*_WRONG_MEDIA` (dự trữ) |
| `INGREDIENTS_TO_VIDEO` | ≥ 1 INGREDIENT binding, tất cả approved | `MISSING_INGREDIENT`, `INGREDIENT_NOT_APPROVED` |
| `VIDEO_EXTENSION` | PREDECESSOR_CLIP approved + continuity_state khác rỗng | `MISSING_PREDECESSOR_CLIP`, `PREDECESSOR_NOT_APPROVED`, `CONTINUITY_NOT_READY` |
| `VIDEO_TO_VIDEO` | SOURCE_CLIP approved + transformation_intent khác rỗng | `MISSING_SOURCE_CLIP`, `SOURCE_NOT_APPROVED`, `TRANSFORMATION_INTENT_MISSING` |

## Policy chung (mọi mode)

- `duration_seconds` trong `[min_duration, max_duration]` (mặc định 1.0–300.0)
  → `DURATION_OUT_OF_POLICY`.
- `aspect_ratio` trong tập hỗ trợ (16:9, 9:16, 1:1, 4:3, 21:9)
  → `ASPECT_RATIO_UNSUPPORTED`.
- `model` trong tập hỗ trợ (`video_model_0.1`, `video_model_0.1_slow`)
  → `MODEL_UNSUPPORTED`.

## Thứ tự trong generator

1. `mapper.supported(operation)` — ngoài capability → error.
2. `mapper.validate_mode(request, approved_hashes=...)` — có issue → raise,
   **không** navigate, **không** submit.
3. Reconcile idempotency key → navigate → guard → submit.

## Fail-closed guarantees

- Không bao giờ tạo job/submit khi mode invalid.
- Không dùng display-name/guess; mọi binding phải là approved hash.
- Issue giữ `code` + `detail` để verifier assert chính xác lý do chặn.
