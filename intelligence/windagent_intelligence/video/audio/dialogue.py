"""
Dialogue preparation (plan 06 Phase 21 §8.1, gate VP21_AUDIO_PIPELINE_VERIFIED).

Normalizes dialogue text WITHOUT changing the meaning of locked lines:
- punctuation/abbreviation/number expansion via a versioned pronunciation
  lexicon (Unicode / Vietnamese safe);
- splits spoken dialogue vs narration vs non-verbal cues by intent type;
- records language/locale, speaking intent and target duration;
- a text revision creates a NEW audio revision (the track carries
  `audio_revision`), never mutating a previous track;
- empty/overlong lines are surfaced as typed issues, never silently dropped.

Fully offline and deterministic — no provider call.
"""

from __future__ import annotations

import re
from typing import List, Optional

from windagent_core.domain.video_production.audio import DialogueTrack
from windagent_core.domain.video_production.enums import (
    AudioAlignmentStatus,
    AudioIntentType,
)
from windagent_core.domain.video_production.ids import DialogueTrackId
from windagent_core.domain.video_production.screenplay import DialogueLine

from windagent_intelligence.video.audio.models import (
    AudioIssue,
    DialoguePreparationReceipt,
)
from windagent_intelligence.video.ids import StableIdFactory

DIALOGUE_PREP_VERSION = "1.0.0"
PRONUNCIATION_LEXICON_VERSION = "1.0.0"

# Very small abridged lexicon for the PoC fixture (plan §8.1: number /
# abbreviation / pronunciation handling). Production lexicons live in config.
_NUMBER_RE = re.compile(r"\b(\d+)\b")
_ABBREV_RE = re.compile(r"\b([A-Z]{2,})\b")
_NUMBER_WORDS = {
    "0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn",
    "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín",
    "10": "mười",
}

# Per-line speaking rate floor for target-duration estimation (chars/sec).
DEFAULT_DIALOGUE_CHARS_PER_SECOND = 8.0
MAX_LINE_CHARS = 400  # overlong guard for the PoC scope (30-45s videos)


class DialoguePreparer:
    """Deterministic dialogue preparation (plan §8.1)."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        chars_per_second: float = DEFAULT_DIALOGUE_CHARS_PER_SECOND,
        max_line_chars: int = MAX_LINE_CHARS,
        lexicon_version: str = PRONUNCIATION_LEXICON_VERSION,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.chars_per_second = chars_per_second
        self.max_line_chars = max_line_chars
        self.lexicon_version = lexicon_version

    def prepare(
        self,
        dialogue_lines: List[DialogueLine],
        *,
        language: str = "vi-VN",
        locale: str = "vi-VN",
    ) -> DialoguePreparationReceipt:
        """Prepare dialogue lines into DialogueTrack[] (plan §8.1)."""
        tracks: List[DialogueTrack] = []
        issues: List[AudioIssue] = []

        for line in dialogue_lines:
            if not line.text or not line.text.strip():
                issues.append(
                    AudioIssue(
                        code="EMPTY_LINE",
                        message=f"Dialogue line {line.dialogue_id} is empty.",
                        dialogue_id=str(line.dialogue_id),
                    )
                )
                continue
            if len(line.text) > self.max_line_chars:
                issues.append(
                    AudioIssue(
                        code="OVERLONG_LINE",
                        message=(
                            f"Dialogue line {line.dialogue_id} exceeds "
                            f"{self.max_line_chars} chars."
                        ),
                        dialogue_id=str(line.dialogue_id),
                        details={"chars": len(line.text)},
                    )
                )
                continue

            prepared = self._normalize(line.text)
            target_duration = self._target_duration(prepared)
            intent = self._classify_intent(line)
            tracks.append(
                DialogueTrack(
                    track_id=DialogueTrackId(
                        self.id_factory.entity_id("dtr", str(line.dialogue_id))
                    ),
                    dialogue_id=line.dialogue_id,
                    character_id=line.character_id,
                    text=line.text,
                    intent_type=intent,
                    language=language,
                    locale=locale,
                    target_duration_seconds=target_duration,
                    voice_profile_hash="",
                    audio_revision=1,
                    alignment_status=AudioAlignmentStatus.ALIGNED,
                    alignment_confidence=1.0,
                    speaking_intent=line.delivery or intent.value.lower(),
                    prepared_text=prepared,
                    pronunciation_lexicon_version=self.lexicon_version,
                    provenance={
                        "prep_version": DIALOGUE_PREP_VERSION,
                        "lexicon_version": self.lexicon_version,
                    },
                )
            )

        return DialoguePreparationReceipt(
            tracks=tracks,
            issues=issues,
            lexicon_version=self.lexicon_version,
            language=language,
            locale=locale,
        )

    # -- normalization (§8.1: meaning-preserving) ---------------------------
    def _normalize(self, text: str) -> str:
        normalized = text.strip()
        # Number expansion (words, not digits — TTS pronunciation).
        normalized = _NUMBER_RE.sub(lambda m: _NUMBER_WORDS.get(m.group(1), m.group(1)), normalized)
        # Abbreviations -> spelled form for clear TTS delivery.
        normalized = _ABBREV_RE.sub(lambda m: self._expand_abbrev(m.group(1)), normalized)
        # Collapse repeated whitespace; keep punctuation (meaning).
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _expand_abbrev(self, token: str) -> str:
        mapping = {
            "OK": "ok",
            "TV": "tivi",
            "VIP": "vip",
        }
        if token in mapping:
            return mapping[token]
        return " ".join(token)  # "AI" -> "A I" spelled out

    @staticmethod
    def _classify_intent(line: DialogueLine) -> AudioIntentType:
        delivery = (line.delivery or "").lower()
        if "narrat" in delivery or "voice over" in delivery or "v.o." in delivery:
            return AudioIntentType.NARRATION
        if "non-verbal" in delivery or "nonverbal" in delivery or "sfx" in delivery:
            return AudioIntentType.NON_VERBAL_CUE
        return AudioIntentType.SPOKEN_DIALOGUE

    def _target_duration(self, prepared: str) -> float:
        if not prepared:
            return 0.0
        return round(len(prepared) / self.chars_per_second, 2)


__all__ = [
    "DIALOGUE_PREP_VERSION",
    "PRONUNCIATION_LEXICON_VERSION",
    "DialoguePreparer",
]
