# Video Operations Contract — Flow Video Generation (Phase 15, plan 04 §21)

- **Gate:** `VP15_FLOW_VIDEO_GENERATION_VERIFIED`
- **Module:** `tools/windagent_tools/google_flow/video_operations.py`

## Operations (plan 04 §21)

```text
TEXT_TO_VIDEO
FRAMES_TO_VIDEO
INGREDIENTS_TO_VIDEO
VIDEO_EXTENSION
VIDEO_TO_VIDEO
```

Mỗi operation ánh xạ một `FlowVideoRequest` typed sang các bước cấu hình
typed (`FlowUiAction` select/fill/upload) — **không bao giờ** nhận raw
browser instruction.

## Request

```python
FlowVideoRequest(
    operation,            # FlowVideoOperation
    request_hash,         # 64-hex sha256 từ compiled request
    project_id,           # WindAgent project
    revision_id,          # immutable production revision
    shot_id="",
    prompt="",
    reference_bindings=(),        # (role, content_hash)
    duration_seconds=4.0,
    aspect_ratio="16:9",
    model="video_model_0.1",
    candidate_limit=1,
    max_cost_credits=0.0,
    idempotency_token="",
    continuity_state="",          # VIDEO_EXTENSION
    transformation_intent="",     # VIDEO_TO_VIDEO
    media_type_hint="video/mp4",
)
```

## Capability

`VideoOperationMapper(capability=...)` — capability rỗng = **không hỗ trợ
operation nào** (fail closed); chỉ `None` mới fallback về toàn bộ tập hợp.
`supported(operation)` trả lời trước khi navigation.

## Policy facts

- `requires_reference(op)` — FRAMES/INGREDIENTS/EXTENSION/VIDEO_TO_VIDEO
  tiêu thụ approved reference binding; TEXT_TO_VIDEO không cần.
- `requires_source_image(op)` — đối với video là source clip (EXTENSION,
  VIDEO_TO_VIDEO) — được pre-submit guard dùng để kiểm tra upload hash.
- `is_character_master(op)` — video ops không phải character master
  (character master là image operation, §18.4).

## Configuration steps

`configuration_actions(request)` trả list `FlowUiAction`:

1. `select generation_mode`
2. `select model_select`
3. `select aspect_ratio_select`
4. `fill prompt_field`
5. `fill duration_field`
6. `upload reference_upload` (nếu op cần reference)
7. `upload source_upload` (nếu op cần source clip)

## Fail-closed guarantees

- Operation ngoài capability → `FlowVideoGenerationError` trước navigation.
- Mode validation (xem `video_mode_validation.md`) chạy TRƯỚC bất kỳ
  navigation/submit nào.
