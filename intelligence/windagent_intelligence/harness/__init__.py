"""Continual Harness Package (Phase 10 — ban_ke_hoach_v1 §15, §16)."""

from windagent_intelligence.harness.diff_engine import DiffEngine
from windagent_intelligence.harness.harness_assembler import AssembledHarnessContext, HarnessAssembler
from windagent_intelligence.harness.harness_service import HarnessService
from windagent_intelligence.harness.immutable_base_guard import (
    FORBIDDEN_IMMUTABLE_PATTERNS,
    PROTECTED_POLICY_NAMES,
    ImmutableBaseGuard,
    ImmutableBaseViolationError,
)
from windagent_intelligence.harness.refinement_engine import RefinementEngine

__all__ = [
    "DiffEngine",
    "HarnessAssembler",
    "AssembledHarnessContext",
    "HarnessService",
    "ImmutableBaseGuard",
    "ImmutableBaseViolationError",
    "FORBIDDEN_IMMUTABLE_PATTERNS",
    "PROTECTED_POLICY_NAMES",
    "RefinementEngine",
]

