"""Subagent Subsystem Ports and Contracts (Phase 13 — ban_ke_hoach_v1 §19, §25).

Defines abstract protocols for subagent security scanning, benchmark evaluation,
and runtime spec registry management, maintaining architectural boundary decoupling.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol

from windagent_core.domain.subagent_evolution import (
    SubagentCandidate,
    SubagentEvaluationResult,
    SubagentSecurityAuditResult,
    SubagentSpecVersion,
)


class SubagentScannerPort(Protocol):
    """Protocol for scanning subagent specs for tool safety, memory permissions, prompt safety, and budget/depth boundaries."""

    def audit(
        self,
        candidate: SubagentCandidate,
        registered_tools: Optional[List[str]] = None,
        registered_skills: Optional[List[str]] = None,
    ) -> SubagentSecurityAuditResult:
        """Runs security and policy audit on proposed subagent candidate."""
        ...


class SubagentEvaluatorPort(Protocol):
    """Protocol for running benchmark task suites and output contract verification on subagent candidates."""

    def evaluate(
        self,
        candidate: SubagentCandidate,
        test_cases: Optional[List[Any]] = None,
        baseline_token_usage: int = 3000,
        baseline_latency_ms: float = 250.0,
    ) -> SubagentEvaluationResult:
        """Runs task suites and computes accuracy, safety, and contract conformance scores."""
        ...


class SubagentSpecRegistryPort(Protocol):
    """Protocol for runtime subagent specification registration and lookup."""

    def register_spec(self, spec: SubagentSpecVersion) -> None:
        """Registers or activates a SubagentSpecVersion in runtime registry."""
        ...

    def get_active_spec(self, role: str) -> Optional[SubagentSpecVersion]:
        """Retrieves currently active spec for a specialized subagent role."""
        ...

    def unregister_spec(self, role: str, version: str) -> None:
        """Deactivates a spec version from runtime registry."""
        ...

