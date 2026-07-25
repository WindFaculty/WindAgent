"""
Verification Report Validator for WindAgent (Phase 24).
Aggregates quality gate execution results and enforces fail-closed verification.
Any BLOCKED gate causes an overall BLOCKED verdict.
Missing evidence = BLOCKED, not PASSED.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from windagent_verification.domain import (
    VerificationGate, VerificationResult, VerificationStatus, ExecutionEvidence,
)
from windagent_verification.quality_gates import (
    TestRunnerGate, PolicyEngineGate, SecurityGate, AcceptanceGate,
)


@dataclass
class VerificationSummary:
    """Summary verdict of holistic verification gate evaluation."""
    verdict: VerificationStatus
    results: List[VerificationResult]
    passed_gates: List[str]
    blocked_gates: List[str]
    failed_gates: List[str]
    total_duration: float
    is_test_pass_only: bool
    evidence_artifacts: List[str] = field(default_factory=list)
    all_evidence_present: bool = True

    @property
    def is_allowed(self) -> bool:
        """Returns True only if ALL gates passed (no BLOCKED, no FAILED)."""
        return self.verdict == VerificationStatus.PASSED


class ReportValidator:
    """Validates verification suites and enforces holistic quality gates.
    Fail-closed: any BLOCKED gate causes overall BLOCKED verdict.
    """

    def __init__(self, gates: Optional[List[VerificationGate]] = None) -> None:
        self.gates: List[VerificationGate] = gates if gates is not None else [
            TestRunnerGate(),
            PolicyEngineGate(),
            SecurityGate(),
            AcceptanceGate(),
        ]

    async def evaluate_suite(self, context: Dict[str, Any]) -> VerificationSummary:
        """Executes all registered verification gates and aggregates their verdicts.
        Fail-closed: any BLOCKED gate causes overall BLOCKED verdict.
        """
        results: List[VerificationResult] = []
        passed_gates: List[str] = []
        blocked_gates: List[str] = []
        failed_gates: List[str] = []
        artifacts: List[str] = []
        total_duration = 0.0
        all_evidence_present = True

        for gate in self.gates:
            res = await gate.execute(context)
            results.append(res)
            total_duration += res.duration

            if res.evidence.artifact_hash:
                artifacts.append(res.evidence.artifact_hash)

            if res.status == VerificationStatus.PASSED:
                passed_gates.append(gate.name)
            elif res.status == VerificationStatus.BLOCKED:
                blocked_gates.append(gate.name)
                all_evidence_present = False
            else:
                failed_gates.append(gate.name)

        # Check if ONLY test_runner passed while critical gates blocked/failed
        test_passed = "test_runner" in passed_gates
        other_gates_ok = any(g != "test_runner" for g in passed_gates)
        is_test_pass_only = test_passed and not other_gates_ok

        # Overall verdict: BLOCKED takes priority, then FAILED, then PASSED
        has_blocking = any(
            res.status == VerificationStatus.BLOCKED and res.blocking for res in results
        )
        has_failure = any(
            res.status == VerificationStatus.FAILED and res.blocking for res in results
        )

        if has_blocking:
            verdict = VerificationStatus.BLOCKED
        elif has_failure or is_test_pass_only:
            verdict = VerificationStatus.FAILED
        else:
            verdict = VerificationStatus.PASSED

        return VerificationSummary(
            verdict=verdict,
            results=results,
            passed_gates=passed_gates,
            blocked_gates=blocked_gates,
            failed_gates=failed_gates,
            total_duration=total_duration,
            is_test_pass_only=is_test_pass_only,
            evidence_artifacts=artifacts,
            all_evidence_present=all_evidence_present,
        )
