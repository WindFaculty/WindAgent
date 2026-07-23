"""
Domain models and contracts for WindAgent Verification (Phase 11).
Defines VerificationStatus, VerificationEvidence, VerificationResult, and VerificationGate interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class VerificationStatus(str, Enum):
    """Status of a verification gate execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class VerificationEvidence:
    """Evidence collected during verification execution."""
    command: str = ""
    exit_code: int = 0
    artifact: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result returned by a single verification gate."""
    gate: str
    status: VerificationStatus
    evidence: VerificationEvidence
    duration: float = 0.0
    blocking: bool = True
    error_message: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        return self.status == VerificationStatus.PASSED


class VerificationGate(ABC):
    """Abstract Base Class for all Quality and Verification Gates."""

    def __init__(self, name: str, blocking: bool = True) -> None:
        self.name = name
        self.blocking = blocking

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> VerificationResult:
        """Executes verification check against the provided task/workflow context."""
        pass
