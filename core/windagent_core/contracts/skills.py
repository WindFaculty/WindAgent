"""Skill Subsystem Ports and Contracts (Phase 12 — ban_ke_hoach_v1 §18, §25).

Defines abstract protocols for skill security scanning, dependency validation,
benchmark evaluation, and runtime management, enabling orchestration and application
layers to interact with skill evolution subsystems without concrete package coupling.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from windagent_core.domain.skill_evolution import (
    SkillCandidate,
    SkillEvaluationResult,
    SkillSecurityAuditResult,
)


class SkillScannerPort(Protocol):
    """Protocol for scanning skill source code and manifests for security violations and secrets."""

    def audit(
        self,
        source_code: Optional[str] = None,
        manifest_dict: Optional[Dict[str, Any]] = None,
        dependency_passed: bool = True,
        permission_passed: bool = True,
        dependency_violations: Optional[List[str]] = None,
        permission_violations: Optional[List[str]] = None,
    ) -> SkillSecurityAuditResult:
        ...


class SkillValidatorPort(Protocol):
    """Protocol for validating skill manifests, dependency resolution, and permissions."""

    def validate_manifest(self, manifest_dict: Dict[str, Any]) -> tuple[bool, Any, List[str]]:
        ...

    def validate_dependencies(
        self,
        required_tools: List[str],
        required_workflows: List[str],
    ) -> tuple[bool, List[str]]:
        ...

    def audit_permissions(self, required_permissions: List[str]) -> tuple[bool, List[str]]:
        ...


class SkillEvaluatorPort(Protocol):
    """Protocol for running functional test suites and evaluation benchmarks on skill candidates."""

    def evaluate(
        self,
        candidate: SkillCandidate,
        test_cases: Optional[List[Any]] = None,
        baseline_token_usage: int = 2000,
        baseline_latency_ms: float = 150.0,
    ) -> SkillEvaluationResult:
        ...


class SkillManagerPort(Protocol):
    """Protocol for runtime skill installation, activation, and rollback in the content root."""

    def install_skill_code(self, manifest: Any, code: Optional[str] = None) -> str:
        ...

    def rollback_skill_version(self, manifest: Any, code: Optional[str] = None) -> str:
        ...

    def list_skills(self) -> List[Any]:
        ...

    def get_skill(self, skill_id: str) -> Any:
        ...


__all__ = [
    "SkillScannerPort",
    "SkillValidatorPort",
    "SkillEvaluatorPort",
    "SkillManagerPort",
]

