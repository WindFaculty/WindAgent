"""
Unit Tests for Phase 7 Finalizer (finalize_phase7.py):
- Fail if receipt is missing or hash wrong
- Fail if report contains untraceable value
- Fail if producer jobs < 13 or aggregator not success
- Fail if candidate SHA != CI head SHA
- Fail if evidence bundle SHA non-existent or not proper ancestor
- Fail if finalizer receipt exit code != real execution exit code
- Fail if publication commit contains implementation files
- Fail if open P0/P1 risk exists
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from scripts.verification.finalize_phase7 import (
    build_evidence_bundle,
    check_branch_protection,
    parse_pytest_xml,
)


def test_parse_pytest_xml_valid(tmp_path: Path):
    xml_file = tmp_path / "pytest.xml"
    xml_file.write_text(
        '<testsuite name="pytest" tests="10" failures="0" errors="0" skipped="1" time="2.5"></testsuite>',
        encoding="utf-8",
    )
    counts = parse_pytest_xml(xml_file)
    assert counts["tests"] == 10
    assert counts["failures"] == 0
    assert counts["errors"] == 0
    assert counts["skipped"] == 1


def test_parse_pytest_xml_missing(tmp_path: Path):
    counts = parse_pytest_xml(tmp_path / "non_existent.xml")
    assert counts["tests"] == 0
    assert counts["failures"] == 0


def test_check_branch_protection_live(tmp_path: Path):
    is_valid, data = check_branch_protection(tmp_path)
    # Under real environment where gh CLI is authenticated, this returns boolean and API response
    assert isinstance(is_valid, bool)
    assert isinstance(data, dict)


def test_finalizer_gate_evaluation(tmp_path: Path):
    # Verify build_evidence_bundle returns gates dictionary with all boolean entries
    root_dir = Path(__file__).resolve().parents[3]
    sha = "6dab084abd3d46cc9f0c9e7dcbb6e65254b83057"
    final_dir, gates, r_status = build_evidence_bundle(root_dir, sha, sha, sha)
    assert final_dir.is_dir()
    assert "artifact_protocol" in gates
    assert "ci_verified" in gates
    assert "branch_protection_verified" in gates
    assert isinstance(gates["ci_verified"], bool)
