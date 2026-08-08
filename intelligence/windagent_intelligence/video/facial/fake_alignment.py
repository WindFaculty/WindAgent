"""
Deterministic fake forced-alignment source for the facial pipeline (Phase 18).

Produces Stage E `AlignmentResult`-shaped data: Vietnamese text with
diacritics, a silence gap, a fast sentence, an emotion change and a
two-character dialogue — the stage_i §5 fixture minimum. Deterministic:
same inputs, same timestamps, so rebuild evidence is reproducible.
"""

from __future__ import annotations

from windagent_core.domain.video_production.concurrent_audio import (
    AlignmentResult,
    compute_alignment_hash,
)
from windagent_core.domain.video_production.ids import (
    AlignmentReceiptId,
    ForcedAlignRunId,
    TtsAudioAssetId,
)

# (phoneme, start_s, end_s, confidence, is_silence)
# Line A1: "Chào bạn, hôm nay thế nào?" (with diacritics, emotion change)
LINE_A_PHONEMES = [
    ("ch", 0.00, 0.10, 0.95, False),
    ("ao", 0.10, 0.24, 0.96, False),
    ("b", 0.26, 0.34, 0.90, False),
    ("an", 0.34, 0.46, 0.93, False),
    ("SIL", 0.46, 0.60, 1.00, True),
    ("h", 0.60, 0.70, 0.88, False),
    ("om", 0.70, 0.84, 0.94, False),
    ("n", 0.84, 0.92, 0.91, False),
    ("ay", 0.92, 1.06, 0.95, False),
    ("SIL", 1.06, 1.14, 1.00, True),
    ("th", 1.14, 1.24, 0.89, False),
    ("e", 1.24, 1.38, 0.97, False),
    ("n", 1.38, 1.46, 0.92, False),
    ("ao", 1.46, 1.60, 0.96, False),
]
# Line B1: "Tôi ổn, cảm ơn!" — fast sentence, second character
LINE_B_PHONEMES = [
    ("t", 0.00, 0.06, 0.93, False),
    ("oi", 0.06, 0.16, 0.95, False),
    ("SIL", 0.16, 0.22, 1.00, True),
    ("o", 0.22, 0.30, 0.94, False),
    ("n", 0.30, 0.36, 0.90, False),
    ("SIL", 0.36, 0.40, 1.00, True),
    ("k", 0.40, 0.46, 0.89, False),
    ("am", 0.46, 0.58, 0.93, False),
    ("SIL", 0.58, 0.62, 1.00, True),
    ("o", 0.62, 0.70, 0.95, False),
    ("n", 0.70, 0.76, 0.91, False),
]

VIETNAMESE_LINE_A = "Chào bạn, hôm nay thế nào?"
VIETNAMESE_LINE_B = "Tôi ổn, cảm ơn!"


def _phoneme_timestamps(entries):
    return [
        {
            "phoneme": ph,
            "start_seconds": start,
            "end_seconds": end,
            "confidence": conf,
            "is_silence": silent,
        }
        for ph, start, end, conf, silent in entries
    ]


def _words(text: str):
    """Per-word timestamps: split text evenly across the line duration."""
    words = []
    n = max(1, len(text.split()))
    duration = _line_duration(text)
    per_word = duration / n
    for i, word in enumerate(text.split()):
        words.append({
            "word": word,
            "start_seconds": round(i * per_word, 3),
            "end_seconds": round((i + 1) * per_word, 3),
            "confidence": 0.95,
        })
    return words


def _line_duration(text: str) -> float:
    if text == VIETNAMESE_LINE_A:
        return LINE_A_PHONEMES[-1][2]
    return LINE_B_PHONEMES[-1][2]


def fake_alignment(
    *,
    text: str,
    run_id: str = "fa-run-p18",
    audio_asset_id: str = "audio-p18",
    segment_confidence: float = 0.96,
) -> AlignmentResult:
    """Build a deterministic AlignmentResult for one dialogue line.

    `segment_confidence < 0.5` triggers the REQUIRES_HUMAN_REVIEW path
    (stage_i §4 — low-confidence alignment).
    """
    entries = LINE_A_PHONEMES if text == VIETNAMESE_LINE_A else LINE_B_PHONEMES
    words = _words(text)
    phonemes = _phoneme_timestamps(entries)
    audio_hash = f"audio-content-{text[:4]}".ljust(64, "0")[:64]
    alignment_hash = compute_alignment_hash(
        audio_content_hash=audio_hash,
        text=text,
        locale="vi-VN",
        timestamps=words,
    )
    return AlignmentResult(
        receipt_id=AlignmentReceiptId(f"alr-p18-{text[:4]}"),
        run_id=ForcedAlignRunId(run_id),
        audio_asset_id=TtsAudioAssetId(audio_asset_id),
        aligner_name="fake-aligner",
        aligner_version="1.0",
        model_name="fake-model",
        model_version="1.0",
        word_timestamps=words,
        phoneme_timestamps=phonemes,
        segment_confidence=segment_confidence,
        alignment_hash=alignment_hash,
    )


__all__ = [
    "VIETNAMESE_LINE_A",
    "VIETNAMESE_LINE_B",
    "LINE_A_PHONEMES",
    "LINE_B_PHONEMES",
    "fake_alignment",
]
