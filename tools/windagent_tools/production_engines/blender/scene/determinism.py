"""
VP3D Phase 4 — Determinism report (plan Stage B §4 items 6-7).

The plan requires running the fixture TWICE with the same input and proving
structural stability:

- scene plan hash identical (same IR -> same locked plan),
- idempotency key identical,
- frame manifest structural hash identical (same set of validated frames),
- every frame's content hash identical (same bytes),
- final MP4 output SHA-256 identical,
- ffprobe structural fields (frame count, dimensions, duration, streams)
  identical.

PIXEL hash parity is only REQUIRED when the hardware/driver/profile is
byte-identical (same device, same driver, same color management). The report
records the hardware profile and flags whether pixel-level parity was
enforced (item 7: "Pixel hash chỉ được yêu cầu nếu hardware/driver/profile
giống hệt").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RunSnapshot:
    """One execution's durable fingerprint."""

    run_label: str
    scene_plan_hash: str = ""
    idempotency_key: str = ""
    frame_manifest_hash: str = ""
    frame_hashes: Dict[str, str] = field(default_factory=dict)
    final_mp4_hash: str = ""
    ffprobe: Dict[str, Any] = field(default_factory=dict)
    hardware_profile: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_label": self.run_label,
            "scene_plan_hash": self.scene_plan_hash,
            "idempotency_key": self.idempotency_key,
            "frame_manifest_hash": self.frame_manifest_hash,
            "frame_hashes": dict(self.frame_hashes),
            "final_mp4_hash": self.final_mp4_hash,
            "ffprobe": dict(self.ffprobe),
            "hardware_profile": dict(self.hardware_profile),
        }


@dataclass(frozen=True)
class DeterminismReport:
    """Structural determinism comparison of two identical-input runs."""

    run_a: RunSnapshot
    run_b: RunSnapshot
    structural_stable: bool
    frame_hashes_stable: bool
    final_mp4_stable: bool
    ffprobe_stable: bool
    hardware_identical: bool
    pixel_parity_enforced: bool
    differences: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Gate acceptance: structural stability is mandatory; pixel parity
        only when the hardware/driver/profile is identical."""
        base = (
            self.structural_stable
            and self.frame_hashes_stable
            and self.final_mp4_stable
            and self.ffprobe_stable
        )
        if not base:
            return False
        if self.hardware_identical:
            # pixel parity enforced only on identical hardware — and required.
            return self.pixel_parity_enforced
        return True

    def to_dict(self) -> dict:
        return {
            "run_a": self.run_a.to_dict(),
            "run_b": self.run_b.to_dict(),
            "structural_stable": self.structural_stable,
            "frame_hashes_stable": self.frame_hashes_stable,
            "final_mp4_stable": self.final_mp4_stable,
            "ffprobe_stable": self.ffprobe_stable,
            "hardware_identical": self.hardware_identical,
            "pixel_parity_enforced": self.pixel_parity_enforced,
            "differences": self.differences,
            "passed": self.passed,
        }

    @classmethod
    def to_dict_from(cls, report: "DeterminismReport") -> dict:
        return report.to_dict()


def hardware_profile_identical(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True when device + build + driver match byte-for-byte."""
    keys = ("device", "build", "driver", "color_management", "resolution")
    return all(a.get(k) == b.get(k) for k in keys)


def compare_runs(
    run_a: RunSnapshot,
    run_b: RunSnapshot,
    *,
    enforce_pixel_parity: Optional[bool] = None,
) -> DeterminismReport:
    """Compare two runs of the same fixture.

    `enforce_pixel_parity` defaults to `hardware_profile_identical(...)` —
    i.e. pixel parity is only demanded on identical hardware (plan item 7).
    """
    differences: List[str] = []

    structural_stable = run_a.scene_plan_hash == run_b.scene_plan_hash and (
        run_a.idempotency_key == run_b.idempotency_key
    )
    if not structural_stable:
        differences.append("scene_plan_hash or idempotency_key differs")

    frame_hashes_stable = run_a.frame_hashes == run_b.frame_hashes
    if not frame_hashes_stable:
        differences.append("frame content hashes differ")

    final_mp4_stable = run_a.final_mp4_hash == run_b.final_mp4_hash
    if not final_mp4_stable:
        differences.append("final MP4 SHA-256 differs")

    ffprobe_stable = run_a.ffprobe == run_b.ffprobe
    if not ffprobe_stable:
        differences.append("ffprobe structural fields differ")

    hw_identical = hardware_profile_identical(
        run_a.hardware_profile, run_b.hardware_profile
    )
    if enforce_pixel_parity is None:
        enforce_pixel_parity = hw_identical

    if hw_identical and not frame_hashes_stable:
        differences.append("identical hardware but pixel hashes differ")

    return DeterminismReport(
        run_a=run_a,
        run_b=run_b,
        structural_stable=structural_stable,
        frame_hashes_stable=frame_hashes_stable,
        final_mp4_stable=final_mp4_stable,
        ffprobe_stable=ffprobe_stable,
        hardware_identical=hw_identical,
        pixel_parity_enforced=enforce_pixel_parity,
        differences=differences,
    )


__all__ = [
    "RunSnapshot",
    "DeterminismReport",
    "hardware_profile_identical",
    "compare_runs",
]
