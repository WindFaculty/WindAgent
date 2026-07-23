"""
Verification Report Validator for WindAgent (Phase 11).
Aggregates quality gate execution results and enforces holistic verification criteria.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from windagent_verification.domain import (
    VerificationGate, VerificationResult, VerificationStatus
)
from windagent_verification.quality_gates import (
    TestRunnerGate, PolicyEngineGate, SecurityGate, AcceptanceGate
)


@dataclass
class VerificationSummary:
    """Summary verdict of holistic verification gate evaluation."""
    verdict: VerificationStatus
    results: List[VerificationResult]
    passed_gates: List[str]
    failed_gates: List[str]
    total_duration: float
    is_test_pass_only: bool
    evidence_artifacts: List[str] = field(default_factory=list)


class ReportValidator:
    """Validates verification suites and enforces holistic quality gates."""

    def __init__(self, gates: Optional[List[VerificationGate]] = None) -> None:
        self.gates: List[VerificationGate] = gates if gates is not None else [
            TestRunnerGate(),
            PolicyEngineGate(),
            SecurityGate(),
            AcceptanceGate(),
        ]

    async def evaluate_suite(self, context: Dict[str, Any]) -> VerificationSummary:
        """Executes all registered verification gates and aggregates their verdicts."""
        results: List[VerificationResult] = []
        passed_gates: List[str] = []
        failed_gates: List[str] = []
        artifacts: List[str] = []
        total_duration = 0.0

        for gate in self.gates:
            res = await gate.execute(context)
            results.append(res)
            total_duration += res.duration

            if res.evidence.artifact:
                artifacts.append(res.evidence.artifact)

            if res.is_successful:
                passed_gates.append(gate.name)
            else:
                failed_gates.append(gate.name)

        # Check if ONLY test_runner passed while critical gates (security, acceptance, policy) failed or skipped
        test_passed = "test_runner" in passed_gates
        other_gates_passed = any(g != "test_runner" for g in passed_gates)
        is_test_pass_only = test_passed and not other_gates_passed

        # Overall verdict calculation: failure of ANY blocking gate causes FAILED verdict
        has_blocking_failure = any(
            res.status != VerificationStatus.PASSED and res.blocking for res in results
        )

        if has_blocking_failure or is_test_pass_only:
            verdict = VerificationStatus.FAILED
        else:
            verdict = VerificationStatus.PASSED

        return VerificationSummary(
            verdict=verdict,
            results=results,
            passed_gates=passed_gates,
            failed_gates=failed_gates,
            total_duration=total_duration,
            is_test_pass_only=is_test_pass_only,
            evidence_artifacts=artifacts,
        )
