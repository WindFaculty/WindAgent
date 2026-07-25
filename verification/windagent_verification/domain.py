"""
Domain models and contracts for WindAgent Verification (Phase 24).
Defines VerificationStatus with BLOCKED state, EvidenceSource for provenance tracking,
ExecutionEvidence for real command output, and fail-closed VerificationGate interface.
Missing evidence = BLOCKED, not PASSED.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class VerificationStatus(str, Enum):
    """Status of a verification gate execution.
    BLOCKED = missing evidence (fail-closed).
    """
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Missing evidence — fail-closed
    ERROR = "error"


class EvidenceSource(str, Enum):
    """Source of verification evidence."""
    COMMAND_EXECUTION = "command_execution"
    TEST_RUNNER = "test_runner"
    LINTER = "linter"
    SECURITY_SCANNER = "security_scanner"
    ACCEPTANCE_EVALUATOR = "acceptance_evaluator"
    ENVIRONMENT_SNAPSHOT = "environment_snapshot"
    ARTIFACT_HASH = "artifact_hash"
    PROVIDED_CONTEXT = "provided_context"  # Legacy fallback


@dataclass
class ExecutionEvidence:
    """Real evidence collected from command execution.
    Unlike the old VerificationEvidence, this requires actual execution data.
    An evidence with empty command is considered MISSING.
    """
    command: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    artifact_hash: Optional[str] = None
    source: EvidenceSource = EvidenceSource.COMMAND_EXECUTION
    environment: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_missing(self) -> bool:
        """Returns True if no real execution occurred (fail-closed condition)."""
        return not self.command or self.exit_code is None


@dataclass
class VerificationResult:
    """Result returned by a single verification gate.
    Fail-closed: if evidence is missing, status is BLOCKED.
    """
    gate: str
    status: VerificationStatus
    evidence: ExecutionEvidence
    duration: float = 0.0
    blocking: bool = True
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        """Fail-closed: missing evidence -> BLOCKED status."""
        if self.evidence.is_missing:
            if self.status != VerificationStatus.BLOCKED:
                self.status = VerificationStatus.BLOCKED
                self.error_message = self.error_message or f"Gate [{self.gate}]: missing execution evidence — BLOCKED"

    @property
    def is_successful(self) -> bool:
        return self.status == VerificationStatus.PASSED


class VerificationGate(ABC):
    """Abstract Base Class for all Quality and Verification Gates.
    Fail-closed: execute() MUST return BLOCKED status when evidence is missing.
    """

    def __init__(self, name: str, blocking: bool = True) -> None:
        self.name = name
        self.blocking = blocking

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        """Executes verification check against the provided task/workflow context.
        Must return BLOCKED if the required evidence cannot be collected.
        """
        pass
