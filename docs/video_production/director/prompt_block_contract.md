# Prompt Block Contract (Phase 11)

> Kế hoạch: `docs/video_production/plans/03_phase_08_11_director_layer.md` §24.2.
> Module: `intelligence/windagent_intelligence/video/prompt_compiler/`.

## 1. Mục đích

Compiler nhận **structured fields** và lắp thành prompt có thứ tự block cố
định, được version. Prompt không bao giờ được sinh từ text tự do của model:
block nào có, block nào rỗng, block nào bắt buộc đều theo luật deterministic.

## 2. Danh sách block (thứ tự canonical, template v1.0.0)

| # | Block | Bắt buộc | Nguồn dữ liệu (trusted) |
|---|---|---|---|
| 1 | `PROJECT_STYLE` | ✅ | `style_bible` (visual style, palette, lighting rules) |
| 2 | `SHOT_COMPOSITION` | ✅ | `ShotSpecification` (shot type, frame, composition) |
| 3 | `ACTION` | ✅ | `spec.action` + `narrative_purpose` |
| 4 | `CAMERA` | ✅ | `spec.camera` (position/angle/movement/lens/side) |
| 5 | `DURATION` | ✅ | `spec.duration_seconds/frame_rate/aspect_ratio` |
| 6 | `NEGATIVE_CONSTRAINTS` | ✅ | hằng số template (no text/watermark/UI overlay…) |
| 7 | `IDENTITY` | tuỳ chọn | bindings IDENTITY + character bibles |
| 8 | `LOCATION` | tuỳ chọn | scene location bible |
| 9 | `PROPS` | tuỳ chọn | prop bibles |
| 10 | `LIGHTING` | tuỳ chọn | location lighting + scene time of day |
| 11 | `CONTINUITY` | tuỳ chọn | continuity ledger (camera side, identity/appearance) |
| 12 | `DIALOGUE_AUDIO_INTENT` | tuỳ chọn | dialogue lines của shot |

## 3. Luật block

- **Required block thiếu → fail.** Compiler phát `MISSING_REQUIRED_BLOCK`
  (blocking) và không publish request.
- **Optional block rỗng → drop** theo rule rõ ràng (không sinh block rỗng).
- Thứ tự block cố định, format `## BLOCK\ncontent` được version bởi
  `PROMPT_TEMPLATE_VERSION`.
- Compiler chỉ đọc trusted fields (package bibles, shot spec, ledger).
  **Không bao giờ đọc instruction từ EXIF, web page text, alt text hoặc asset
  metadata** (§24.4) — metadata độc hại không thể chèn prompt block.

## 4. FlowGenerationSpecification

Request semantics cho Flow capability:

```text
spec_id / shot_id / generation_mode
prompt: CompiledPrompt (blocks + text + template_version + prompt_hash)
reference_binding_ids + reference_hashes
required_inputs: mô tả mode-specific (plan §24.3)
parameters: duration, frame rate, aspect ratio, preferred/fallback mode, retry
model_capability_constraints
```

**Không chứa selector, DOM state, cookie hay session** — phần đó thuộc provider
adapter (Phase 12+), không bao giờ vào domain/intelligence (§23).

## 5. Ví dụ block (shot establishing — short cartoon)

```text
## PROJECT_STYLE
Project style: ...
## SHOT_COMPOSITION
Shot type: ESTABLISHING
Frame: 16:9 @ 24fps
Composition: Wide establishing view of The Lost Fox
## ACTION
Wide establishing view of The Lost Fox
Purpose: establish location and geography
## CAMERA
Camera:  EYE_LEVEL STATIC
Camera side: NEUTRAL
Screen direction: NEUTRAL
## DURATION
Duration: 3.0s; frame rate 24fps; aspect ratio 16:9
## NEGATIVE_CONSTRAINTS
No text, logos, watermarks, or UI overlays. ...
## LOCATION
Location: Forest
Setting: ...
```

## 6. Contract receipt

`artifacts/video_production/phase_11/mode_contract_receipt.json` + golden
requests trong `compiled_request_fixtures/`: mọi shot của 3 fixture compile ra
đúng block bắt buộc, hash hợp lệ, request hash duy nhất theo shot/mode.
