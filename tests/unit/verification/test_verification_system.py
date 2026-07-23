"""
Unit tests for WindAgent Verification subsystem (Phase 11):
- All 7 Quality Gates (TestRunnerGate, PolicyEngineGate, IntegrityGate, QualityGates, RegressionGate, SecurityGate, AcceptanceGate)
- VerificationResult & Evidence formatting
- ReportValidator suite aggregation & enforcement that test pass alone is not sufficient
"""

import pytest
from windagent_verification import (
    VerificationStatus, TestRunnerGate, PolicyEngineGate, IntegrityGate, QualityGates,
    RegressionGate, SecurityGate, AcceptanceGate, ReportValidator
)


@pytest.mark.asyncio
async def test_test_runner_gate_passed_and_failed():
    gate = TestRunnerGate()

    # Passed execution
    res_pass = await gate.execute({"test_results": {"passed": True, "count": 10}})
    assert res_pass.status == VerificationStatus.PASSED
    assert res_pass.is_successful is True
    assert res_pass.evidence.exit_code == 0

    # Failed execution
    res_fail = await gate.execute({"test_results": {"passed": False, "count": 10, "stderr": "AssertionError"}})
    assert res_fail.status == VerificationStatus.FAILED
    assert res_fail.is_successful is False
    assert res_fail.evidence.exit_code == 1


@pytest.mark.asyncio
async def test_all_7_quality_gates():
    context = {
        "test_results": {"passed": True},
        "permissions": {"checked": ["read_file"], "violations": []},
        "integrity_ok": True,
        "checksum_mismatches": [],
        "lint_issues": [],
        "baseline_latency_ms": 100.0,
        "current_latency_ms": 105.0,
        "leaked_secrets": [],
        "disallowed_calls": [],
        "acceptance_criteria": ["criteria_1"],
        "fulfilled_criteria": ["criteria_1"],
    }

    gates = [
        TestRunnerGate(),
        PolicyEngineGate(),
        IntegrityGate(),
        QualityGates(),
        RegressionGate(),
        SecurityGate(),
        AcceptanceGate(),
    ]

    for gate in gates:
        res = await gate.execute(context)
        assert res.status == VerificationStatus.PASSED, f"Gate {gate.name} failed unexpectedly"


@pytest.mark.asyncio
async def test_report_validator_enforces_holistic_quality_and_rejects_test_pass_only():
    validator = ReportValidator()

    # Case A: Tests pass, but security gate fails (leaked secret)
    context_fail_security = {
        "test_results": {"passed": True},
        "permissions": {"checked": ["read_file"], "violations": []},
        "leaked_secrets": ["sk-12345678901234567890"],
        "acceptance_criteria": ["criteria_1"],
        "fulfilled_criteria": ["criteria_1"],
    }

    summary_a = await validator.evaluate_suite(context_fail_security)
    assert summary_a.verdict == VerificationStatus.FAILED
    assert "security" in summary_a.failed_gates
    assert "test_runner" in summary_a.passed_gates

    # Case B: All gates pass
    context_all_pass = {
        "test_results": {"passed": True},
        "permissions": {"checked": ["read_file"], "violations": []},
        "leaked_secrets": [],
        "disallowed_calls": [],
        "acceptance_criteria": ["criteria_1"],
        "fulfilled_criteria": ["criteria_1"],
    }

    summary_b = await validator.evaluate_suite(context_all_pass)
    assert summary_b.verdict == VerificationStatus.PASSED
    assert len(summary_b.failed_gates) == 0
    assert summary_b.is_test_pass_only is False
