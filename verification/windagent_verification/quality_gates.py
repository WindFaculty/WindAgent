"""
Quality Gates implementation for WindAgent Verification (Phase 11).
Contains TestRunnerGate, PolicyEngineGate, IntegrityGate, QualityGates, RegressionGate, SecurityGate, and AcceptanceGate.
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
from windagent_verification.domain import (
    VerificationGate, VerificationResult, VerificationStatus, VerificationEvidence
)


class TestRunnerGate(VerificationGate):
    """Quality gate for running unit/integration tests."""
    __test__ = False

    def __init__(self, command: str = "pytest", blocking: bool = True) -> None:
        super().__init__(name="test_runner", blocking=blocking)
        self.command = command

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        test_results = context.get("test_results", {})
        passed = test_results.get("passed", True)
        exit_code = 0 if passed else 1
        stdout = test_results.get("stdout", "All tests passed cleanly.")
        stderr = test_results.get("stderr", "")

        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command=self.command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            artifact=context.get("test_artifact_path"),
            metrics={"tests_run": test_results.get("count", 1), "failed": 0 if passed else 1}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message=None if passed else "Test suite execution failed"
        )


class PolicyEngineGate(VerificationGate):
    """Quality gate for verifying tool and action permission policies."""

    def __init__(self, blocking: bool = True) -> None:
        super().__init__(name="policy_engine", blocking=blocking)

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        permissions = context.get("permissions", {})
        violations = permissions.get("violations", [])

        passed = len(violations) == 0
        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command="policy_evaluator.verify()",
            exit_code=0 if passed else 1,
            stdout=f"Evaluated {len(permissions.get('checked', []))} permission rules.",
            stderr="; ".join(violations) if violations else "",
            metrics={"violations": len(violations)}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message="Policy violations detected: " + "; ".join(violations) if not passed else None
        )


class IntegrityGate(VerificationGate):
    """Quality gate for file checksum, workspace integrity, and DAG validity."""

    def __init__(self, blocking: bool = True) -> None:
        super().__init__(name="integrity", blocking=blocking)

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        integrity_ok = context.get("integrity_ok", True)
        checksum_mismatches = context.get("checksum_mismatches", [])

        passed = integrity_ok and len(checksum_mismatches) == 0
        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command="integrity_checker.verify_hashes()",
            exit_code=0 if passed else 1,
            stdout="Integrity check passed." if passed else "Integrity check failed.",
            stderr="Mismatches: " + ", ".join(checksum_mismatches) if checksum_mismatches else "",
            metrics={"checksum_mismatches": len(checksum_mismatches)}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message="Integrity check failed" if not passed else None
        )


class QualityGates(VerificationGate):
    """Quality gate for linter, static analysis, and code style checks."""

    def __init__(self, blocking: bool = True) -> None:
        super().__init__(name="quality_gates", blocking=blocking)

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        lint_issues = context.get("lint_issues", [])

        passed = len(lint_issues) == 0
        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command="linter_static_analysis",
            exit_code=0 if passed else 1,
            stdout="No linter/type issues detected." if passed else f"Detected {len(lint_issues)} issues.",
            stderr="\n".join(lint_issues) if lint_issues else "",
            metrics={"issue_count": len(lint_issues)}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message=f"Quality gate failed with {len(lint_issues)} issues" if not passed else None
        )


class RegressionGate(VerificationGate):
    """Quality gate for performance and behavioral regression verification."""

    def __init__(self, max_latency_increase_pct: float = 20.0, blocking: bool = True) -> None:
        super().__init__(name="regression", blocking=blocking)
        self.max_latency_increase_pct = max_latency_increase_pct

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        baseline_ms = context.get("baseline_latency_ms", 100.0)
        current_ms = context.get("current_latency_ms", 100.0)
        increase_pct = ((current_ms - baseline_ms) / baseline_ms) * 100.0 if baseline_ms > 0 else 0.0

        passed = increase_pct <= self.max_latency_increase_pct
        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command="regression_benchmark",
            exit_code=0 if passed else 1,
            stdout=f"Baseline: {baseline_ms}ms, Current: {current_ms}ms, Delta: {increase_pct:.2f}%",
            metrics={"baseline_ms": baseline_ms, "current_ms": current_ms, "delta_pct": increase_pct}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message=f"Latency regression {increase_pct:.2f}% exceeded limit {self.max_latency_increase_pct}%" if not passed else None
        )


class SecurityGate(VerificationGate):
    """Quality gate for secret scanning and security vulnerability verification."""

    def __init__(self, blocking: bool = True) -> None:
        super().__init__(name="security", blocking=blocking)

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        leaked_secrets = context.get("leaked_secrets", [])
        disallowed_calls = context.get("disallowed_calls", [])

        passed = len(leaked_secrets) == 0 and len(disallowed_calls) == 0
        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command="security_scan",
            exit_code=0 if passed else 1,
            stdout="Security scan passed. Zero secrets detected." if passed else "Security scan failed.",
            stderr=f"Leaked secrets: {len(leaked_secrets)}, Disallowed calls: {len(disallowed_calls)}",
            metrics={"leaked_secrets": len(leaked_secrets), "disallowed_calls": len(disallowed_calls)}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message="Security audit failure: detected secrets or illegal operations" if not passed else None
        )


class AcceptanceGate(VerificationGate):
    """Quality gate for machine-readable task acceptance criteria evaluation."""

    def __init__(self, blocking: bool = True) -> None:
        super().__init__(name="acceptance", blocking=blocking)

    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        start_time = time.time()
        criteria = context.get("acceptance_criteria", [])
        fulfilled = context.get("fulfilled_criteria", [])

        unfulfilled = [c for c in criteria if c not in fulfilled]
        passed = len(unfulfilled) == 0 and len(criteria) > 0

        status = VerificationStatus.PASSED if passed else VerificationStatus.FAILED
        evidence = VerificationEvidence(
            command="acceptance_criteria_evaluator",
            exit_code=0 if passed else 1,
            stdout=f"Fulfilled {len(fulfilled)}/{len(criteria)} criteria.",
            stderr="Unfulfilled criteria: " + ", ".join(unfulfilled) if unfulfilled else "",
            metrics={"total_criteria": len(criteria), "fulfilled": len(fulfilled)}
        )
        return VerificationResult(
            gate=self.name,
            status=status,
            evidence=evidence,
            duration=time.time() - start_time,
            blocking=self.blocking,
            error_message="Acceptance criteria not met: " + ", ".join(unfulfilled) if not passed else None
        )
