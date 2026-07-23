"""
Canonical Model Registry & Equivalence Package for WindAgent Provider Subsystem V3.
Exports normalize_model_id, classify_equivalence, EquivalenceLevel, and CanonicalModelRegistryService.
"""

from windagent_providers.registry.model_normalizer import (
    normalize_model_id,
    NormalizedModelInfo,
)
from windagent_providers.registry.equivalence import (
    classify_equivalence,
    EquivalenceLevel,
    EquivalenceAssessment,
)
from windagent_providers.registry.canonical_registry import (
    CanonicalModelRegistryService,
    CanonicalModelRecord,
    EndpointBindingRecord,
    AuditTrailRecord,
)

__all__ = [
    "normalize_model_id",
    "NormalizedModelInfo",
    "classify_equivalence",
    "EquivalenceLevel",
    "EquivalenceAssessment",
    "CanonicalModelRegistryService",
    "CanonicalModelRecord",
    "EndpointBindingRecord",
    "AuditTrailRecord",
]
