# Forced Alignment Contract

Stage E, Phase 10, backlog 4 & 5. Authority: `stage_e_concurrent_audio.md`.

## Port

`ForcedAlignmentPort` (contracts) là adapter riêng, tách khỏi `TtsProviderPort`
(stage_e risk: TTS open-source có thể không cung cấp phoneme timing; aligner
không bịa confidence). Trả về `AlignmentResultHandle`:

- `aligner_name`, `aligner_version`, `model_name`, `model_version`;
- `words` — `[{word, start_seconds, end_seconds, confidence}]`;
- `phonemes` — `[{phoneme, start_seconds, end_seconds, confidence}]` (có thể rỗng);
- `segment_confidence` — 0..1.

## Domain `AlignmentResult` (backlog 5)

- Giữ word/phoneme timestamps + confidence + tool/model/version.
- `alignment_hash` = SHA-256(audio_content_hash + text + locale + timestamps).
  Cùng audio + cùng text → cùng hash → alignment reusable qua episode, không
  cần re-run.

## Confidence gate

`align()` áp dụng `ALIGNMENT_CONFIDENCE_FLOOR = 0.6`:

- `segment_confidence < 0.6` → `LowConfidenceAlignmentError` → route **human
  review**, không đưa vào facial/lip-sync.
- Không bao giờ chấp nhận timing low-confidence một cách âm thầm.

## Fail-closed validation (backlog 4)

`validate_tts_output()` kiểm tra trước publish: non-empty bytes, decode probe,
`duration > 0`, sample rate khớp capability, channel layout hợp lệ, content
hash khớp. Bất kỳ issue nào → `AudioValidationReceipt` không valid →
`TtsInvalidOutputError`, KHÔNG publish.
