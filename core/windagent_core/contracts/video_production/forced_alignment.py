""""
ForcedAlignmentPort — forced alignment contract (VP3D Phase 10, Stage E).

A forced aligner converts an audio line + its text into word/phoneme timing for
facial/lip-sync animation. It is a SEPARATE adapter from the TTS provider
(stage_e backlog 5 & risk section): a TTS engine that lacks phoneme timing is
not trusted to invent confidence — alignment is its own typed, validated step.

Guarantees:
  - the aligner returns per-word and/or per-phoneme timestamps plus per-segment
    confidence and the exact tool/model/version used (provenance);
  - an alignment hash is computed so identical input yields identical timing
    (deterministic, reusable across episodes);
  - any confidence below threshold routes to human review via the domain,
    never silently into facial animation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ForcedAlignmentPort(Protocol):
    """Port a forced-alignment adapter implements (whisperX, Montreal, etc.)."""

    async def align(self, request: object) -> "AlignmentResultHandle":
        """Align one audio line against its text.

        `request` is an `AlignmentInput` (domain value object: audio asset +
        transcribed text + locale + optional lexicon version). Returns a raw
        `AlignmentResultHandle` — word/phoneme timestamps + confidence + the
        tool/model/version used. The domain computes the alignment hash and
        applies the confidence gate before any timing reaches facial animation.

        Raises:
          LowConfidenceAlignmentError — if the whole-segment confidence is
          under the acceptable floor for lip-sync.
        """


@runtime_checkable
class AlignmentResultHandle(Protocol):
    """Raw alignment result: timestamps + confidence + provenance."""

    aligner_name: str
    aligner_version: str
    model_name: str
    model_version: str
    words: list  # [{word, start_seconds, end_seconds, confidence}]
    phonemes: list  # [{phoneme, start_seconds, end_seconds, confidence}] (may be empty)
    segment_confidence: float  # 0..1


__all__ = ["ForcedAlignmentPort", "AlignmentResultHandle"]
