"""
Unit Tests for WindAgent Verification System (Phase 24):
- Fail-closed: missing evidence = BLOCKED, not PASSED
- ExecutionEvidence with real command execution
- BLOCKED status in VerificationResult.__post_init__
- ReportValidator with BLOCKED verdict aggregation
- All quality gates with missing evidence detection
"""

import pytest
from windagent_verification import (
    VerificationStatus, VerificationResult, VerificationGate,
    ExecutionEvidence, EvidenceSource,
    CommandRunner, TestRunner, LinterRunner, SecurityScanner, EnvironmentSnapshot,
    TestRunnerGate, PolicyEngineGate, IntegrityGate, QualityGates,
    RegressionGate, SecurityGate, AcceptanceGate,
    ReportValidator, VerificationSummary,
)


# ====================================================================
# 1. Fail-Closed: Missing Evidence = BLOCKED
# ====================================================================

def test_execution_evidence_missing():
    """Evidence without command or exit_code is considered missing."""
    evidence = ExecutionEvidence(command="", exit_code=None)
    assert evidence.is_missing is True


def test_execution_evidence_present():
    evidence = ExecutionEvidence(command="pytest", exit_code=0, stdout="All tests passed")
    assert evidence.is_missing is False


def test_verification_result_fail_closed():
    """VerificationResult auto-sets BLOCKED when evidence is missing."""
    evidence = ExecutionEvidence(command="", exit_code=None)
    result = VerificationResult(
        gate="test_gate", status=VerificationStatus.PASSED, evidence=evidence,
    )
    assert result.status == VerificationStatus.BLOCKED
    assert result.error_message is not None
    assert "BLOCKED" in result.error_message


def test_verification_result_passed_with_evidence():
    evidence = ExecutionEvidence(command="pytest", exit_code=0, stdout="ok")
    result = VerificationResult(
        gate="test_gate", status=VerificationStatus.PASSED, evidence=evidence,
    )
    assert result.status == VerificationStatus.PASSED
    assert result.is_successful is True


# ====================================================================
# 2. Command Runner (unit tests — avoid real subprocess)
# ====================================================================

@pytest.mark.asyncio
async def test_command_runner_empty():
    runner = CommandRunner()
    result = await runner.run("")
    assert result.exit_code == -1
    assert result.stderr == "No command provided"


@pytest.mark.asyncio
async def test_command_runner_to_evidence():
    from windagent_verification.runners import CommandResult
    result = CommandResult(command="pytest", exit_code=0, stdout="All passed", stderr="", duration_seconds=1.5)
    evidence = result.to_evidence()
    assert evidence.exit_code == 0
    assert evidence.stdout == "All passed"
    assert evidence.duration_seconds == 1.5
    assert evidence.is_missing is False


@pytest.mark.asyncio
async def test_command_result_missing():
    from windagent_verification.runners import CommandResult
    result = CommandResult(command="", exit_code=-1, stdout="", stderr="No command", duration_seconds=0.0)
    evidence = result.to_evidence()
    assert evidence.is_missing is True


# ====================================================================
# 3. Report Validator — BLOCKED Verdict
# ====================================================================

@pytest.mark.asyncio
async def test_report_validator_all_passed():
    """When all gates pass, verdict should be PASSED."""
    validator = ReportValidator(gates=[
        AcceptanceGate(),  # Will be BLOCKED without criteria, so test needs context
    ])
    result = await validator.evaluate_suite({
        "acceptance_criteria": ["Test passes"],
        "fulfilled_criteria": ["Test passes"],
    })
    assert result.verdict == VerificationStatus.PASSED


@pytest.mark.asyncio
async def test_report_validator_blocked_on_missing_evidence():
    """Missing acceptance criteria -> BLOCKED."""
    validator = ReportValidator(gates=[AcceptanceGate()])
    result = await validator.evaluate_suite({})
    assert result.verdict == VerificationStatus.BLOCKED
    assert len(result.blocked_gates) > 0
    assert result.all_evidence_present is False


@pytest.mark.asyncio
async def test_report_validator_summary_allowed():
    summary = VerificationSummary(
        verdict=VerificationStatus.PASSED,
        results=[],
        passed_gates=["test"],
        blocked_gates=[],
        failed_gates=[],
        total_duration=1.0,
        is_test_pass_only=False,
    )
    assert summary.is_allowed is True


@pytest.mark.asyncio
async def test_report_validator_summary_blocked():
    summary = VerificationSummary(
        verdict=VerificationStatus.BLOCKED,
        results=[],
        passed_gates=[],
        blocked_gates=["security"],
        failed_gates=[],
        total_duration=1.0,
        is_test_pass_only=False,
        all_evidence_present=False,
    )
    assert summary.is_allowed is False


# ====================================================================
# 4. Quality Gates — Fail-Closed
# ====================================================================

@pytest.mark.asyncio
async def test_acceptance_gate_blocked_no_criteria():
    gate = AcceptanceGate()
    result = await gate.execute({})
    assert result.status == VerificationStatus.BLOCKED
    assert "No acceptance criteria" in (result.error_message or "")


@pytest.mark.asyncio
async def test_acceptance_gate_passed():
    gate = AcceptanceGate()
    result = await gate.execute({
        "acceptance_criteria": ["Criterion A", "Criterion B"],
        "fulfilled_criteria": ["Criterion A", "Criterion B"],
    })
    assert result.status == VerificationStatus.PASSED


@pytest.mark.asyncio
async def test_regression_gate_blocked_no_baseline():
    gate = RegressionGate()
    result = await gate.execute({})
    assert result.status == VerificationStatus.BLOCKED
    assert "Missing regression baseline" in (result.error_message or "")


@pytest.mark.asyncio
async def test_regression_gate_passed():
    gate = RegressionGate(max_latency_increase_pct=20.0)
    result = await gate.execute({
        "baseline_latency_ms": 100.0,
        "current_latency_ms": 110.0,
    })
    assert result.status == VerificationStatus.PASSED


@pytest.mark.asyncio
async def test_regression_gate_failed():
    gate = RegressionGate(max_latency_increase_pct=20.0)
    result = await gate.execute({
        "baseline_latency_ms": 100.0,
        "current_latency_ms": 150.0,  # 50% increase > 20% limit
    })
    assert result.status == VerificationStatus.FAILED


@pytest.mark.asyncio
async def test_policy_gate_blocked_no_context():
    gate = PolicyEngineGate()
    result = await gate.execute({})
    assert result.status == VerificationStatus.BLOCKED


@pytest.mark.asyncio
async def test_policy_gate_passed():
    gate = PolicyEngineGate()
    result = await gate.execute({
        "permissions": {"violations": [], "checked": ["read_file", "write_file"]},
    })
    assert result.status == VerificationStatus.PASSED


# ====================================================================
# 5. Environment Snapshot
# ====================================================================

@pytest.mark.asyncio
async def test_environment_snapshot():
    evidence = await EnvironmentSnapshot.capture()
    assert evidence.exit_code == 0
    assert "python_version" in evidence.metrics
    assert "platform" in evidence.metrics


# ====================================================================
# 6. Verification Summary Properties
# ====================================================================

def test_verification_status_values():
    assert VerificationStatus.BLOCKED.value == "blocked"
    assert VerificationStatus.PASSED.value == "passed"
    assert VerificationStatus.FAILED.value == "failed"
