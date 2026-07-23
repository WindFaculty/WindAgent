"""
Equivalence Classifier for WindAgent Provider Subsystem V3 Canonical Model Registry.
Classifies model equivalence levels and enforces strict failover compatibility rules.
"""

from __future__ import annotations
from enum import Enum
from typing import NamedTuple, Optional
from windagent_providers.registry.model_normalizer import NormalizedModelInfo, normalize_model_id


class EquivalenceLevel(str, Enum):
    EXACT_REVISION = "exact_revision"
    EXACT_FAMILY_FLOATING_REVISION = "exact_family_floating_revision"
    COMPATIBLE_ALIAS = "compatible_alias"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class EquivalenceAssessment(NamedTuple):
    level: EquivalenceLevel
    confidence: float
    reason: str
    is_failover_eligible: bool


def classify_equivalence(
    model_a: NormalizedModelInfo,
    model_b: NormalizedModelInfo
) -> EquivalenceAssessment:
    """Classifies equivalence between two normalized model definitions."""
    # 1. Exact Fingerprint Match -> exact_revision
    if model_a.equivalence_fingerprint == model_b.equivalence_fingerprint:
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_REVISION,
            confidence=1.0,
            reason="Fingerprint, revision, and quantization match exactly",
            is_failover_eligible=True,
        )

    # 2. Same family, same revision, different quantization -> exact_family_floating_revision (NOT exact failover eligible!)
    if model_a.family == model_b.family and model_a.revision == model_b.revision and model_a.quantization != model_b.quantization:
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION,
            confidence=0.85,
            reason=f"Quantization differs ({model_a.quantization} vs {model_b.quantization})",
            is_failover_eligible=False,
        )

    # 3. Same family, different/floating revision -> exact_family_floating_revision
    if model_a.family == model_b.family:
        if model_a.revision != model_b.revision:
            return EquivalenceAssessment(
                level=EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION,
                confidence=0.80,
                reason=f"Model revisions differ ({model_a.revision} vs {model_b.revision})",
                is_failover_eligible=False,
            )

    # 4. Cross-vendor alias match (e.g. gpt-4o on OpenAI vs gpt-4o on OpenRouter with same revision)
    a_clean = model_a.raw_model_id.replace("openai/", "").replace("openrouter/", "")
    b_clean = model_b.raw_model_id.replace("openai/", "").replace("openrouter/", "")
    if a_clean == b_clean:
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_REVISION,
            confidence=1.0,
            reason="Cross-vendor exact model ID match",
            is_failover_eligible=True,
        )

    return EquivalenceAssessment(
        level=EquivalenceLevel.UNKNOWN,
        confidence=0.0,
        reason="Model families or parameters do not align",
        is_failover_eligible=False,
    )
