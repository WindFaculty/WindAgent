"""Composition-only adapters for the subagent-evolution HTTP surface."""

from __future__ import annotations

from windagent_core.contracts.subagents import (
    SubagentEvaluatorPort,
    SubagentScannerPort,
)
from windagent_evals.subagent_evaluator import SubagentEvaluator
from windagent_skills.security.subagent_security_scanner import SubagentSecurityScanner


def make_subagent_evolution_adapters() -> tuple[
    SubagentScannerPort, SubagentEvaluatorPort
]:
    """Wire concrete adapters at the API composition boundary only."""
    return SubagentSecurityScanner(), SubagentEvaluator()
