# Alignment Policy (plan 06 §8.4) — Phase 21

Gate: `VP21_AUDIO_PIPELINE_VERIFIED`

## 1. Mục đích

`AlignmentService` (`intelligence/.../video/audio/alignment.py`) chạy forced
alignment để gắn **word timestamps** cho mỗi dialogue track, so sánh với thời
lượng shot và đề xuất timing adjustment. Timing/alignment issue **không bao giờ
bị che** — chúng xuất hiện dạng typed finding.

## 2. Pipeline (plan §8.4)

```text
DialogueLine
→ TTS (asset §8.3)
→ forced alignment -> word timestamps
→ shot timing comparison
→ timing adjustment proposal
```

## 3. Rules

- **Low confidence → human review**: alignment confidence dưới floor →
  `LOW_CONFIDENCE` issue; track đánh dấu `ALIGNMENT_MISSING`/pending, không coi
  là final aligned.
- **Không kéo/nén audio quá policy** mà không cảnh báo — timing proposal phải
  nằm trong tolerance; ngoài tolerance → issue.
- **Lời dài hơn shot**: ưu tiên `timing_proposals` đổi timing/shot, **không cắt
  lời im lặng/lời thoại** (`OVERLONG_LINE` → proposal, never cut).
- Track có audio nhưng thiếu word timestamps → `ALIGNMENT_MISSING` (fail
  closed, không im lặng coi là aligned).
- `alignment_status`: `UNALIGNED` → `ALIGNED` (hoặc `TIMING_PROPOSED` khi cần
  đổi timing) + `alignment_confidence` ghi lại.
- Bất kỳ track nào alignment fail đều còn nguyên trong receipt (`tracks`), với
  issue — không drop.

## 4. Kiểm chứng (verifier)

- `alignment_receipt.json`: track có audio + đủ timestamps → ALIGNED; confidence
  thấp → LOW_CONFIDENCE issue + human routing; audio thiếu timestamps →
  ALIGNMENT_MISSING; lời dài hơn shot → timing proposal, không cắt.
