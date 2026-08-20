"""
Equivalence Classifier for WindAgent Provider Subsystem V3.

Since Phase 3 the pure classification logic lives in core; this module
re-exports it so provider-internal modules keep a single import site.
"""

from windagent_core.contracts.providers.equivalence import (
    EquivalenceAssessment,
    EquivalenceLevel,
    classify_equivalence,
)

__all__ = ["EquivalenceLevel", "EquivalenceAssessment", "classify_equivalence"]