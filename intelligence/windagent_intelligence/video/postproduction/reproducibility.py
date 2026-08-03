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
