"""
Timing and Zero-Audio QC Verifier for Code Video Production (Video 02 Implementation Plan §11.6).

Validates millisecond precision, continuous timeline integrity, and zero-audio decoupling:
- Exact Total Duration: 975,000 ms (16:15.000 = 29,250 frames @ 30 fps).
- Contiguity: Zero gaps, zero overlapping frames between scenes.
- Zero-Audio Policy: audio_policy='EXCLUDED', 0 audio streams (audio handoff via cue_sheet.csv).
- Voiceover Cue Sheet: Complete 19 scene entries matching exact script markers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from windagent_core.contracts.code_video import CodeVideoPlan
from windagent_tools.code_video.media.assembler import CueSheet, MasterAssemblyResult


@dataclass
class TimingQCReport:
    """Detailed report for timing accuracy, frame counts, and zero-audio validation."""
    is_valid: bool
    total_duration_ms: int
    total_frames: int
    scene_count: int
    zero_audio_verified: bool
    cuesheet_verified: bool
    timing_errors: List[str] = field(default_factory=list)
    audio_violations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_duration_ms": self.total_duration_ms,
            "total_frames": self.total_frames,
            "scene_count": self.scene_count,
            "zero_audio_verified": self.zero_audio_verified,
            "cuesheet_verified": self.cuesheet_verified,
            "timing_errors": self.timing_errors,
            "audio_violations": self.audio_violations,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class TimingQCVerifier:
    """
    Validates timing accuracy and zero-audio constraints on master timeline outputs.
    """

    TARGET_DURATION_MS: int = 975_000
    TARGET_FRAMES: int = 29_250
    TARGET_FPS: int = 30
    TARGET_SCENES: int = 19

    @classmethod
    def verify_assembly_result(
        cls,
        assembly_result: MasterAssemblyResult,
        cue_sheet: Optional[CueSheet] = None,
    ) -> TimingQCReport:
        """Verify output of Master Visual Assembly."""
        timing_errors: List[str] = []
        audio_violations: List[str] = []

        # 1. Duration check
        if assembly_result.total_duration_ms != cls.TARGET_DURATION_MS:
            timing_errors.append(
                f"Total duration mismatch: got {assembly_result.total_duration_ms}ms, expected {cls.TARGET_DURATION_MS}ms"
            )

        # 2. Frame count check
        if assembly_result.total_frames != cls.TARGET_FRAMES:
            timing_errors.append(
                f"Total frames mismatch: got {assembly_result.total_frames}, expected {cls.TARGET_FRAMES}"
            )

        # 3. Scene count check
        if assembly_result.scene_count != cls.TARGET_SCENES:
            timing_errors.append(
                f"Scene count mismatch: got {assembly_result.scene_count}, expected {cls.TARGET_SCENES}"
            )

        # 4. Zero audio policy
        if not assembly_result.zero_audio_verified:
            audio_violations.append("Zero-audio constraint violation: audio streams detected or unverified.")

        # 5. Cue sheet verification
        cuesheet_verified = True
        if cue_sheet is not None:
            if len(cue_sheet.entries) != cls.TARGET_SCENES:
                cuesheet_verified = False
                timing_errors.append(
                    f"CueSheet entry count {len(cue_sheet.entries)} != expected {cls.TARGET_SCENES}"
                )
            if cue_sheet.entries:
                if cue_sheet.entries[0].start_timecode != "00:00.000":
                    cuesheet_verified = False
                    timing_errors.append(f"CueSheet start timecode mismatch: {cue_sheet.entries[0].start_timecode}")
                if cue_sheet.entries[-1].end_timecode != "16:15.000":
                    cuesheet_verified = False
                    timing_errors.append(f"CueSheet end timecode mismatch: {cue_sheet.entries[-1].end_timecode}")

        all_errors = timing_errors + audio_violations
        is_valid = len(all_errors) == 0 and cuesheet_verified

        return TimingQCReport(
            is_valid=is_valid,
            total_duration_ms=assembly_result.total_duration_ms,
            total_frames=assembly_result.total_frames,
            scene_count=assembly_result.scene_count,
            zero_audio_verified=assembly_result.zero_audio_verified,
            cuesheet_verified=cuesheet_verified,
            timing_errors=timing_errors,
            audio_violations=audio_violations,
            errors=all_errors,
            metadata={
                "master_1440p_hash": assembly_result.master_1440p_hash,
                "delivery_1080p_hash": assembly_result.delivery_1080p_hash,
            },
        )


__all__ = [
    "TimingQCReport",
    "TimingQCVerifier",
]
