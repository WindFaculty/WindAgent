"""Verification domain models, gates, and suite reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from windagent.kernel.time import utc_now


class VerificationGateType(StrEnum):
    """Types of verification gates."""

    TEST_RUNNER = "TEST_RUNNER"
    POLICY_ENGINE = "POLICY_ENGINE"
    INTEGRITY = "INTEGRITY"
    LINTER_STYLE = "LINTER_STYLE"
    SECURITY_SCAN = "SECURITY_SCAN"
    REGRESSION_CHECK = "REGRESSION_CHECK"
    ACCEPTANCE = "ACCEPTANCE"


class VerificationStatus(StrEnum):
    """Outcome status of a verification gate or suite."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"



@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    """Audited evidence captured from verification runners."""

    command: str = ""
    exit_code: int | None = 0
    stdout: str = ""
    stderr: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_hash: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationGateResult:
    """Result of evaluating a single verification gate."""

    gate_name: str
    gate_type: VerificationGateType
    status: VerificationStatus
    evidence: ExecutionEvidence
    duration_ms: float = 0.0
    blocking: bool = True
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationSuiteReport:
    """Consolidated verification report across a suite of gates."""

    report_id: str
    suite_id: str
    target_id: str
    overall_status: VerificationStatus
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    blocked_gates: tuple[str, ...]
    gate_results: tuple[VerificationGateResult, ...]
    blocker_reasons: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    duration_ms: float = 0.0
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def evaluate(
        cls,
        report_id: str,
        suite_id: str,
        target_id: str,
        gate_results: list[VerificationGateResult],
    ) -> VerificationSuiteReport:
        passed = [r.gate_name for r in gate_results if r.status == VerificationStatus.PASSED]
        failed = [r.gate_name for r in gate_results if r.status == VerificationStatus.FAILED]
        blocked = [r.gate_name for r in gate_results if r.status == VerificationStatus.BLOCKED]

        blockers: list[str] = []
        for r in gate_results:
            if r.blocking and r.status in (VerificationStatus.FAILED, VerificationStatus.BLOCKED):
                msg = r.error_message or f"Gate {r.gate_name} did not pass ({r.status.value})"
                blockers.append(msg)

        if blocked:
            overall = VerificationStatus.BLOCKED
        elif failed:
            overall = VerificationStatus.FAILED
        elif any(r.status == VerificationStatus.WARNING for r in gate_results):
            overall = VerificationStatus.WARNING
        else:
            overall = VerificationStatus.PASSED

        total_duration = sum(r.duration_ms for r in gate_results)

        recommendations: list[str] = []
        if failed:
            recommendations.append(f"Fix failures in gates: {', '.join(failed)}")
        if blocked:
            recommendations.append(f"Provide missing verification context for: {', '.join(blocked)}")

        return cls(
            report_id=report_id,
            suite_id=suite_id,
            target_id=target_id,
            overall_status=overall,
            passed_gates=tuple(passed),
            failed_gates=tuple(failed),
            blocked_gates=tuple(blocked),
            gate_results=tuple(gate_results),
            blocker_reasons=tuple(blockers),
            recommendations=tuple(recommendations),
            duration_ms=total_duration,
            created_at=utc_now(),
        )
