"""
Reproducibility Auditor (Phase 22 — plan 06 §13.4).

Audits post-production render runs to verify byte-identical output or semantic
reproducibility across runs given identical input clip hashes and EDL parameters.
"""

from __future__ import annotations

from typing import Sequence

from windagent_core.domain.video_production.postproduction import (
    EditDecisionList,
    FfmpegCommandReceipt,
)
from windagent_intelligence.video.postproduction.models import (
    ManifestAuditReport,
    ReproducibilityReport,
)


class ReproducibilityAuditor:
    """Audits post-production render executions for reproducibility."""

    def audit_render_runs(
        self,
        edl_a: EditDecisionList,
        edl_b: EditDecisionList,
        receipts_a: Sequence[FfmpegCommandReceipt],
        receipts_b: Sequence[FfmpegCommandReceipt],
        output_hash_a: str,
        output_hash_b: str,
    ) -> ReproducibilityReport:
        """Compare two render runs and generate audit reproducibility report."""
        reasons: list[str] = []

        edl_matched = edl_a.edl_hash == edl_b.edl_hash
        if not edl_matched:
            reasons.append("EDL hashes do not match between runs.")

        # Check input clip hashes
        inputs_a = [h for r in receipts_a for h in r.input_hashes]
        inputs_b = [h for r in receipts_b for h in r.input_hashes]
        inputs_matched = inputs_a == inputs_b
        if not inputs_matched:
            reasons.append("Input clip hashes differ between runs.")

        # Check command manifests
        argv_a = [r.argv for r in receipts_a]
        argv_b = [r.argv for r in receipts_b]
        cmd_matched = argv_a == argv_b
        if not cmd_matched:
            reasons.append("FFmpeg command argv manifests differ between runs.")

        is_reproducible = edl_matched and inputs_matched and cmd_matched and (output_hash_a == output_hash_b)
        if output_hash_a != output_hash_b and edl_matched:
            reasons.append("Output SHA-256 hashes differ despite identical EDL and inputs.")

        return ReproducibilityReport(
            is_reproducible=is_reproducible,
            input_hashes_matched=inputs_matched,
            edl_hash_matched=edl_matched,
            command_manifest_matched=cmd_matched,
            output_sha256=output_hash_a,
            previous_sha256=output_hash_b,
            mismatch_reasons=tuple(reasons),
        )

    def audit_manifest_runs(
        self,
        manifest_a: dict,
        manifest_b: dict,
    ) -> ManifestAuditReport:
        """Manifest-level reproducibility (VP3D Phase 24, stage_l §3.8).

        Bit-exact equality is REQUIRED only when tool, platform and encoding
        profile are identical; otherwise the audit compares manifests and
        technical properties (codec/resolution/fps/duration/streams) plus
        input/EDL/mix hashes.
        """
        reasons: list[str] = []

        tool_matched = manifest_a.get("tool_hash") == manifest_b.get("tool_hash")
        platform_matched = (
            manifest_a.get("platform") == manifest_b.get("platform")
        )
        profile_matched = (
            manifest_a.get("profile_hash") == manifest_b.get("profile_hash")
        )
        inputs_matched = (
            manifest_a.get("input_hashes") == manifest_b.get("input_hashes")
        )
        edl_matched = manifest_a.get("edl_hash") == manifest_b.get("edl_hash")
        mix_matched = manifest_a.get("mix_hash") == manifest_b.get("mix_hash")
        semantic_matched = self._semantic_match(manifest_a, manifest_b)

        bit_exact = manifest_a.get("output_hash") == manifest_b.get("output_hash")
        bit_exact_required = tool_matched and platform_matched and profile_matched

        if not tool_matched:
            reasons.append("ffmpeg tool hash differs between runs.")
        if not platform_matched:
            reasons.append("platform identity differs between runs.")
        if not profile_matched:
            reasons.append("encoding profile hash differs between runs.")
        if not inputs_matched:
            reasons.append("input frame/audio hashes differ between runs.")
        if not edl_matched:
            reasons.append("EDL hash differs between runs.")
        if not mix_matched:
            reasons.append("audio mix plan hash differs between runs.")
        if not semantic_matched:
            reasons.append("technical properties (codec/res/fps/duration/streams) differ.")
        if bit_exact_required and not bit_exact:
            reasons.append(
                "bit-exact required (same tool/platform/profile) but output "
                "SHA-256 differs."
            )

        is_reproducible = (
            inputs_matched
            and mix_matched
            and semantic_matched
            # The EDL pins the encoding profile, so EDL equality is only
            # required when the profile itself matches; a different profile
            # legitimately yields a different EDL hash.
            and (edl_matched or not profile_matched)
            and (bit_exact if bit_exact_required else True)
        )
        return ManifestAuditReport(
            is_reproducible=is_reproducible,
            bit_exact=bit_exact,
            bit_exact_required=bit_exact_required,
            tool_matched=tool_matched,
            platform_matched=platform_matched,
            profile_matched=profile_matched,
            input_hashes_matched=inputs_matched,
            edl_hash_matched=edl_matched,
            mix_hash_matched=mix_matched,
            semantic_properties_matched=semantic_matched,
            mismatch_reasons=tuple(reasons),
        )

    @staticmethod
    def _semantic_match(manifest_a: dict, manifest_b: dict) -> bool:
        properties = (
            "video_codec",
            "resolution",
            "frame_rate",
            "duration_seconds",
            "audio_streams",
            "pixel_format",
        )
        return all(
            manifest_a.get(prop) == manifest_b.get(prop) for prop in properties
        )
