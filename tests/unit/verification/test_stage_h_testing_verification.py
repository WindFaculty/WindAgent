"""
Stage H — Testing & Verification Quality Gate Suite (VP3D_UI_TEST_MATRIX_VERIFIED).

Asserts all Stage H capabilities (UI41 to UI46) meet Definition of Done criteria.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.verification.verify_stage_h_testing import run_stage_h_verification


def test_stage_h_master_quality_gate() -> None:
    """Verify Stage H quality gate passes all test matrix requirements."""
    passed = run_stage_h_verification()
    assert passed is True, "Stage H verification master run failed!"


def test_evidence_bundle_report_exists() -> None:
    """Verify evidence bundle JSON report was written without errors."""
    report_path = Path("final-evidence-bundle/stage_h/stage_h_verification_report.json")
    assert report_path.exists(), "Stage H evidence report file is missing!"

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["gate"] == "VP3D_UI_TEST_MATRIX_VERIFIED"
    assert data["overall_verdict"] == "PASSED"
    assert data["suites"]["UI41_contract_tests"] == "PASSED"
    assert data["suites"]["UI42_script_behavioral"] == "PASSED"
    assert data["suites"]["UI43_asset_behavioral"] == "PASSED"
    assert data["suites"]["UI44_consumer_parity"] == "PASSED"
    assert data["suites"]["UI45_desktop_e2e"] == "PASSED"
    assert data["suites"]["UI46_browser_e2e"] == "PASSED"
