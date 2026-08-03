"""
Forced alignment (plan 06 Phase 21 §8.4, gate VP21_AUDIO_PIPELINE_VERIFIED).

Pipeline:

```text
DialogueLine -> TTS -> forced alignment -> word timestamps
             -> shot timing comparison -> timing adjustment proposal
```

Rules (plan §8.4):
- low alignment confidence routes to HUMAN review — never silently accepted;
- audio is never stretched/compressed beyond policy without a warning;
- an overlong line produces a TIMING_PROPOSED adjustment (change timing/shot),
  the line is NEVER cut;
- timing issues are surfaced as typed findings, never hidden.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.audio import DialogueTrack, WordTimestamp
from windagent_core.domain.video_production.enums import AudioAlignmentStatus

from windagent_intelligence.video.audio.models import AlignmentReceipt, AudioIssue
from windagent_intelligence.video.ids import StableIdFactory

ALIGNMENT_VERSION = "1.0.0"
DEFAULT_CONFIDENCE_FLOOR = 0.6
DEFAULT_MAX_STRETCH_RATIO = 1.15  # never stretch audio beyond 15% without warning


class AlignmentService:
    """Deterministic forced-alignment policy (plan §8.4)."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
        max_stretch_ratio: float = DEFAULT_MAX_STRETCH_RATIO,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.confidence_floor = confidence_floor
        self.max_stretch_ratio = max_stretch_ratio

    def align(
        self,
        tracks: List[DialogueTrack],
        *,
        word_timestamps_by_track: Optional[Dict[str, List[WordTimestamp]]] = None,
        shot_duration_by_track: Optional[Dict[str, float]] = None,
    ) -> AlignmentReceipt:
        """Apply word timestamps + shot timing comparison to tracks."""
        word_timestamps_by_track = word_timestamps_by_track or {}
        shot_duration_by_track = shot_duration_by_track or {}
        issues: List[AudioIssue] = []
        proposals: List[Dict[str, Any]] = []
        out_tracks: List[DialogueTrack] = []

        for track in tracks:
            timestamps = word_timestamps_by_track.get(track.dialogue_id.value, [])
            confidence = self._average_confidence(timestamps)
            track = track.model_copy(
                update={"word_timestamps": list(timestamps), "alignment_confidence": confidence}
            )

            # 0. A track with audio but NO word timestamps is a missing-
            #    alignment finding — never silently accepted (fail closed).
            #    The track state is set to UNALIGNED (not ALIGNED) so
            #    has_valid_audio() is False and downstream consumers (e.g.
            #    post-production) cannot include an unaligned track.
            if track.audio is not None and not timestamps:
                track = track.model_copy(
                    update={
                        "alignment_status": AudioAlignmentStatus.UNALIGNED,
                        "alignment_confidence": 0.0,
                    }
                )
                issues.append(
                    AudioIssue(
                        code="ALIGNMENT_MISSING",
                        message=(
                            f"Dialogue {track.dialogue_id} has audio but no "
                            "word timestamps (forced alignment missing)."
                        ),
                        dialogue_id=track.dialogue_id.value,
                    )
                )
                out_tracks.append(track)
                continue

            # 1. Low alignment confidence -> human review (fail closed).
            if timestamps and confidence < self.confidence_floor:
                track = track.model_copy(
                    update={"alignment_status": AudioAlignmentStatus.LOW_CONFIDENCE}
                )
                issues.append(
                    AudioIssue(
                        code="ALIGNMENT_LOW_CONFIDENCE",
                        message=(
                            f"Alignment confidence {confidence:.2f} below floor "
                            f"{self.confidence_floor} for {track.dialogue_id}."
                        ),
                        dialogue_id=track.dialogue_id.value,
                        details={"confidence": confidence},
                    )
                )
                out_tracks.append(track)
                continue

            # 2. Shot timing comparison: overlong line -> proposal, never cut.
            shot_duration = shot_duration_by_track.get(track.dialogue_id.value)
            audio_duration = track.audio.duration_seconds if track.audio else track.target_duration_seconds
            if shot_duration is not None and audio_duration > shot_duration:
                ratio = audio_duration / shot_duration if shot_duration else 1.0
                status = (
                    AudioAlignmentStatus.TIMING_PROPOSED
                    if ratio <= self.max_stretch_ratio
                    else AudioAlignmentStatus.OVERLONG_LINE
                )
                track = track.model_copy(update={"alignment_status": status})
                proposals.append(
                    {
                        "dialogue_id": track.dialogue_id.value,
                        "audio_duration_seconds": audio_duration,
                        "shot_duration_seconds": shot_duration,
                        "ratio": round(ratio, 3),
                        "proposal": (
                            "extend shot timing or shorten line (never cut the line)"
                            if status == AudioAlignmentStatus.OVERLONG_LINE
                            else "stretch within policy with warning"
                        ),
                    }
                )
                if status == AudioAlignmentStatus.OVERLONG_LINE:
                    issues.append(
                        AudioIssue(
                            code="OVERLONG_FOR_SHOT",
                            message=(
                                f"Dialogue {track.dialogue_id} ({audio_duration:.1f}s) exceeds "
                                f"shot ({shot_duration:.1f}s) beyond stretch policy."
                            ),
                            dialogue_id=track.dialogue_id.value,
                            details={"audio": audio_duration, "shot": shot_duration, "ratio": ratio},
                        )
                    )
            out_tracks.append(track)

        return AlignmentReceipt(
            tracks=out_tracks,
            issues=issues,
            timing_proposals=proposals,
        )

    @staticmethod
    def _average_confidence(timestamps: List[WordTimestamp]) -> float:
        if not timestamps:
            return 1.0
        return round(sum(t.confidence for t in timestamps) / len(timestamps), 3)


__all__ = ["ALIGNMENT_VERSION", "AlignmentService"]
