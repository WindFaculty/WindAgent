"""
Contract and Verification Tests for Phase 3 — Generated API Client & Realtime Package.
Validates package structure, OpenAPI export integrity, zero new direct fetch violations, and Phase 3 manifests.
"""

import json
from pathlib import Path
import pytest
from scripts.frontend_api.export_openapi import export_openapi
from scripts.frontend_api.validate_openapi import validate_openapi
from scripts.check_no_new_direct_fetch import check_direct_fetches

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE_3_DIR = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "phase_03"
PACKAGES_DIR = WORKSPACE_ROOT / "frontend" / "packages"

def test_phase3_packages_structure():
    """Verify that all 3 Phase 3 canonical packages exist and have correct entrypoints."""
    required_packages = ["api-contracts", "api-client", "realtime"]
    for pkg in required_packages:
        pkg_path = PACKAGES_DIR / pkg
        assert pkg_path.exists(), f"Package folder {pkg} missing"
        assert (pkg_path / "package.json").exists(), f"package.json missing for {pkg}"
        assert (pkg_path / "tsconfig.json").exists(), f"tsconfig.json missing for {pkg}"
        assert (pkg_path / "src" / "index.ts").exists(), f"src/index.ts missing for {pkg}"
        
        with open(pkg_path / "package.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data.get("name") == f"@windagent/{pkg}"
            assert data.get("type") == "module"

def test_openapi_v3_export_and_validation():
    """Verify OpenAPI v3 schema export and quality validation."""
    schema = export_openapi()
    assert schema is not None
    assert "paths" in schema
    assert len(schema["paths"]) > 0
    
    valid = validate_openapi()
    assert valid is True

def test_zero_new_direct_fetch_violations():
    """Verify CI rule: Zero new direct fetch violations introduced in production frontend code."""
    direct_fetch_pass = check_direct_fetches()
    assert direct_fetch_pass is True

def test_phase3_manifests_and_verdict():
    """Verify Phase 3 artifacts and verdict."""
    final_verdict_file = PHASE_3_DIR / "final_verdict.json"
    assert final_verdict_file.exists()
    
    with open(final_verdict_file, "r", encoding="utf-8") as f:
        verdict = json.load(f)
        assert verdict.get("phase") == "3"
        assert verdict.get("verdict") == "FEV3_P3_GENERATED_CLIENT_VERIFIED"
        assert verdict.get("status") == "PASS"
        criteria = verdict.get("criteria", {})
        assert criteria.get("openapi_export_pass") is True
        assert criteria.get("openapi_validation_pass") is True
        assert criteria.get("generated_ts_contracts_pass") is True
        assert criteria.get("generated_api_client_pass") is True
        assert criteria.get("realtime_package_pass") is True
        assert criteria.get("new_direct_fetch_violations") == 0
        assert criteria.get("v2_regression_pass") is True
        assert criteria.get("v3_studio_regression_pass") is True

def test_client_contract_report_contents():
    """Verify client contract report contains expected namespaces and capabilities."""
    report_file = PHASE_3_DIR / "client_contract_report.json"
    assert report_file.exists()
    
    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)
        features = report.get("features", {})
        assert features.get("typed_api_problem_mapping") is True
        assert features.get("correlation_id_propagation") is True
        assert features.get("idempotency_key_mutations") is True
        assert features.get("get_retry_on_network_error") is True
        assert features.get("realtime_sequence_dedup") is True
        assert features.get("realtime_exponential_backoff") is True
        assert set(features.get("facade_namespaces", [])) >= {"projects", "episodes", "studio", "agents", "assets", "system"}
