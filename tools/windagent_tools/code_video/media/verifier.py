"""
Take and Media Verification Suite for Code Video Production.

Validates technical compliance of captured visual takes against Video 02 quality gates:
- 2560x1440 (1440p) master resolution
- 30 fps
- Exact frame count ((duration_ms * fps) // 1000)
- Zero audio streams / audio disabled
- Deterministic cryptographic hashes
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from windagent_core.contracts.code_video import CodeVideoPlan, Scene
from windagent_tools.code_video.capture.receipts import (
    FrameReport,
    MediaProbeReport,
    TakeReceipt,
)


@dataclass(frozen=True)
class TakeVerificationResult:
    """Detailed verification outcome for a take."""
    is_valid: bool
    take_id: str
    scene_id: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "take_id": self.take_id,
            "scene_id": self.scene_id,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


class TakeVerifier:
    """
    Validates take receipts, frame reports, and probe reports for Phase 7 Gate.
    """

    @classmethod
    def verify_take_receipt(
        cls,
        receipt: TakeReceipt,
        scene: Optional[Scene] = None,
        expected_resolution: str = "2560x1440",
        expected_fps: int = 30,
    ) -> TakeVerificationResult:
        """Verify technical attributes of a single TakeReceipt."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Take and scene identity
        if not receipt.take_id:
            errors.append("TakeReceipt take_id is missing.")
        if not receipt.scene_id:
            errors.append("TakeReceipt scene_id is missing.")
        if scene and receipt.scene_id != scene.scene_id:
            errors.append(f"Scene ID mismatch: receipt has '{receipt.scene_id}', expected '{scene.scene_id}'")

        # 2. Timing and duration
        if scene:
            if receipt.start_ms != scene.start_ms:
                errors.append(f"Start time mismatch: receipt={receipt.start_ms}ms, scene={scene.start_ms}ms")
            if receipt.duration_ms != scene.duration_ms:
                errors.append(f"Duration mismatch: receipt={receipt.duration_ms}ms, scene={scene.duration_ms}ms")

        # 3. Resolution and FPS
        if receipt.resolution != expected_resolution:
            errors.append(f"Resolution mismatch: got '{receipt.resolution}', expected '{expected_resolution}'")
        if receipt.fps != expected_fps:
            errors.append(f"FPS mismatch: got {receipt.fps}, expected {expected_fps}")

        # 4. Frame count precision
        expected_frames = (receipt.duration_ms * receipt.fps) // 1000
        if receipt.frame_count != expected_frames:
            errors.append(f"Frame count mismatch: got {receipt.frame_count}, expected {expected_frames}")

        # 5. Zero audio policy
        if receipt.audio_enabled:
            errors.append("Audio is enabled in take. Video 02 requires audio_enabled=False.")

        # 6. Cryptographic output hash
        if not receipt.output_hash or len(receipt.output_hash) != 64:
            errors.append(f"Invalid output_hash format: '{receipt.output_hash}' (expected 64-char hex SHA-256)")

        # 7. Status
        if receipt.status != "VERIFIED":
            warnings.append(f"Take status is '{receipt.status}', expected 'VERIFIED'")

        is_valid = len(errors) == 0
        return TakeVerificationResult(
            is_valid=is_valid,
            take_id=receipt.take_id,
            scene_id=receipt.scene_id,
            errors=errors,
            warnings=warnings,
            metadata={
                "frame_count": receipt.frame_count,
                "duration_ms": receipt.duration_ms,
                "output_hash": receipt.output_hash,
            },
        )

    @classmethod
    def verify_media_probe(
        cls,
        probe: MediaProbeReport,
        expected_width: int = 2560,
        expected_height: int = 1440,
        expected_fps: float = 30.0,
    ) -> TakeVerificationResult:
        """Verify media probe report from ffprobe / inspector."""
        errors: List[str] = []
        warnings: List[str] = []

        if not probe.has_video_stream:
            errors.append("Probe report indicates missing video stream.")
        if probe.has_audio_stream or probe.audio_streams_count > 0:
            errors.append(f"Probe report found {probe.audio_streams_count} audio streams. Audio must be 0.")
        if probe.width != expected_width or probe.height != expected_height:
            errors.append(f"Resolution mismatch: probe={probe.width}x{probe.height}, expected={expected_width}x{expected_height}")
        if abs(probe.frame_rate - expected_fps) > 0.01:
            errors.append(f"Frame rate mismatch: probe={probe.frame_rate}, expected={expected_fps}")

        is_valid = len(errors) == 0
        return TakeVerificationResult(
            is_valid=is_valid,
            take_id=probe.take_id,
            scene_id=probe.scene_id,
            errors=errors,
            warnings=warnings,
            metadata={
                "container": probe.container,
                "codec": probe.codec,
                "audio_streams": probe.audio_streams_count,
            },
        )


__all__ = [
    "TakeVerificationResult",
    "TakeVerifier",
]
