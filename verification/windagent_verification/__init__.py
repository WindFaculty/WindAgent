"""
Quality gates, verification runners, report validator for WindAgent (Phase 24).
Fail-closed: missing evidence = BLOCKED, not PASSED.
"""

from windagent_verification.domain import (
    VerificationStatus, VerificationGate, VerificationResult,
    ExecutionEvidence, EvidenceSource,
)
from windagent_verification.runners import (
    CommandRunner, TestRunner, LinterRunner, SecurityScanner, EnvironmentSnapshot, CommandResult,
)
from windagent_verification.quality_gates import (
    TestRunnerGate, PolicyEngineGate, IntegrityGate, QualityGates,
    RegressionGate, SecurityGate, AcceptanceGate,
)
from windagent_verification.report_validator import ReportValidator, VerificationSummary

__all__ = [
    "VerificationStatus",
    "VerificationGate",
    "VerificationResult",
    "ExecutionEvidence",
    "EvidenceSource",
    "CommandRunner",
    "TestRunner",
    "LinterRunner",
    "SecurityScanner",
    "EnvironmentSnapshot",
    "CommandResult",
    "TestRunnerGate",
    "PolicyEngineGate",
    "IntegrityGate",
    "QualityGates",
    "RegressionGate",
    "SecurityGate",
    "AcceptanceGate",
    "ReportValidator",
    "VerificationSummary",
]

__version__ = "0.4.0"
