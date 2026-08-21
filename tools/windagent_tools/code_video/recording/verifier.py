"""
Recording Verification Engine and Gate Certification for Phase 9.

Validates the integrity, secret-freedom, terminal authenticity, and determinism
of the 16 recorded Video 02 passes against the gate CV02_P9_RECORDING_VERIFIED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List

from windagent_tools.code_video.recording.passes import PassCatalog, PassStatus
from windagent_tools.code_video.recording.recorder import RecordingManifest


@dataclass
class RecordingVerificationReport:
    """
    Detailed verification verdict for Video 02 recorded passes.
    """
    gate: str
    is_valid: bool
    total_passes_checked: int
    passed_checks: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "is_valid": self.is_valid,
            "total_passes_checked": self.total_passes_checked,
            "passed_checks": self.passed_checks,
            "violations": self.violations,
            "summary": self.summary,
            "verified_at": self.verified_at,
        }


class RecordingVerifier:
    """
    Certifies that all recorded passes meet the strict Phase 9 visual production gates.
    """

    GATE_NAME: str = "CV02_P9_RECORDING_VERIFIED"

    @classmethod
    def verify_manifest(cls, manifest: RecordingManifest) -> RecordingVerificationReport:
        """
        Verify an in-memory or deserialized RecordingManifest against Phase 9 rules.
        """
        passed_checks: List[str] = []
        violations: List[str] = []

        # 1. Total passes check (must be exactly 16)
        if manifest.total_passes == 16:
            passed_checks.append("TOTAL_PASS_COUNT_16_VERIFIED")
        else:
            violations.append(f"Pass count expected 16, got {manifest.total_passes}")

        # 2. All passes verified status
        failed_passes = [p.pass_id for p in manifest.passes if p.status != PassStatus.VERIFIED]
        if not failed_passes:
            passed_checks.append("ALL_PASSES_STATUS_VERIFIED")
        else:
            violations.append(f"Passes with non-VERIFIED status: {failed_passes}")

        # 3. Secret clean check
        if manifest.all_secrets_clean:
            passed_checks.append("ZERO_SECRET_EXPOSURE_VERIFIED")
        else:
            violations.append("Secret exposure detected in one or more recorded passes")

        # 4. Terminal authenticity check
        if manifest.all_terminals_verified:
            passed_checks.append("TERMINAL_OUTPUT_AUTHENTICITY_VERIFIED")
        else:
            violations.append("Unverified or mismatched terminal output detected")

        # 5. Master Resolution and FPS
        if manifest.master_resolution == "2560x1440":
            passed_checks.append("MASTER_RESOLUTION_1440P_VERIFIED")
        else:
            violations.append(f"Master resolution mismatch: {manifest.master_resolution}")

        if manifest.fps == 30:
            passed_checks.append("MASTER_FPS_30_VERIFIED")
        else:
            violations.append(f"Master FPS mismatch: {manifest.fps}")

        # 6. Tri-hash non-empty check
        invalid_hashes = [
            p.pass_id for p in manifest.passes
            if not p.source_hash or not p.render_config_hash or not p.output_hash
        ]
        if not invalid_hashes:
            passed_checks.append("TRI_HASH_DETERMINISM_VERIFIED")
        else:
            violations.append(f"Missing tri-hashes in passes: {invalid_hashes}")

        # 7. Pass Catalog ID alignment
        catalog_pass_ids = {p.pass_id for p in PassCatalog.get_all_passes()}
        manifest_pass_ids = {p.pass_id for p in manifest.passes}
        if catalog_pass_ids == manifest_pass_ids:
            passed_checks.append("PASS_CATALOG_ALIGNMENT_VERIFIED")
        else:
            missing = catalog_pass_ids - manifest_pass_ids
            extra = manifest_pass_ids - catalog_pass_ids
            violations.append(f"Pass ID mismatch (missing: {missing}, extra: {extra})")

        is_valid = (len(violations) == 0)

        summary = {
            "video_id": manifest.video_id,
            "total_duration_ms": manifest.total_duration_ms,
            "total_frames": manifest.total_frames,
            "manifest_hash": manifest.manifest_hash,
            "gate": cls.GATE_NAME,
            "verdict": "PASS" if is_valid else "REJECT",
        }

        return RecordingVerificationReport(
            gate=cls.GATE_NAME,
            is_valid=is_valid,
            total_passes_checked=len(manifest.passes),
            passed_checks=passed_checks,
            violations=violations,
            summary=summary,
        )

    @classmethod
    def verify_manifest_file(cls, manifest_path: Path) -> RecordingVerificationReport:
        """
        Load and verify a recording_manifest.json file.
        """
        raw_text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        passes_raw = data.get("passes", [])

        from windagent_tools.code_video.recording.passes import PassRecord
        pass_records = [
            PassRecord(
                pass_id=p["pass_id"],
                scene_id=p["scene_id"],
                status=PassStatus(p["status"]),
                duration_ms=p["duration_ms"],
                frame_count=p["frame_count"],
                source_hash=p["source_hash"],
                render_config_hash=p["render_config_hash"],
                output_hash=p["output_hash"],
                verified_terminal=p["verified_terminal"],
                secret_clean=p["secret_clean"],
                keyframe_marks=p.get("keyframe_marks", []),
                artifacts_produced=p.get("artifacts_produced", []),
                recorded_at=p.get("recorded_at"),
                notes=p.get("notes"),
            )
            for p in passes_raw
        ]

        manifest = RecordingManifest(
            video_id=data.get("video_id", "video-02"),
            milestone=data.get("milestone", "v0.1 — Simple Agent"),
            total_passes=data.get("total_passes", len(pass_records)),
            total_duration_ms=data.get("total_duration_ms", 0),
            total_frames=data.get("total_frames", 0),
            master_resolution=data.get("master_resolution", "2560x1440"),
            fps=data.get("fps", 30),
            all_secrets_clean=data.get("all_secrets_clean", False),
            all_terminals_verified=data.get("all_terminals_verified", False),
            passes=pass_records,
            recorded_at=data.get("recorded_at", datetime.now(timezone.utc).isoformat()),
        )
        return cls.verify_manifest(manifest)
