"""Stage I — Final Acceptance evidence (UI50, evidence bundle).

Keeps the two real checks from the old Stage I suite:
- UI50: video workspace foundation architecture check
- Stage I evidence bundle generation + Go/No-Go verdict

The UI47/48/49 "golden workflow invariant" tests were removed: they asserted
on hand-built literals (no production code exercised). The behaviors they
named are covered by real suites:
- locked-revision immutability  -> tests/unit/domain/video_production/test_script_behavioral_invariants.py
- license governance            -> tests/unit/domain/video_production/test_asset_behavioral_invariants.py
- script<->asset eligibility    -> tests/unit/domain/video_production/test_stage_e_script_asset_binding.py
"""

from __future__ import annotations

import pytest
from scripts.check_video_workspace_architecture import main as check_video_arch
from scripts.produce_stage_i_evidence import run_stage_i_evidence_generation


def test_ui50_video_workspace_foundation_architecture():
    """Verify UI50 Video Workspace Foundation architecture audit."""
    result = check_video_arch()
    assert result == 0, "UI50 Video Workspace architecture check failed!"


def test_stage_i_evidence_bundle_and_go_no_go_verdict():
    """Verify Stage I evidence bundle generation and Go/No-Go release verdict."""
    summary = run_stage_i_evidence_generation()
    assert summary["overall_verdict"] == "RELEASE_APPROVED"
    assert summary["go_no_go_status"] == "GO"
    assert len(summary["gates"]) == 4
    for gate, status in summary["gates"].items():
        assert status == "PASSED", f"Gate {gate} did not pass!"
