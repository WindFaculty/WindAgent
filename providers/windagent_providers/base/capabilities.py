"""
Model Capabilities Matrix and Matching Engine for WindAgent Provider Subsystem V3.

Since Phase 3 the neutral capability/profile types live in core
(``windagent_core.contracts.providers.model_capabilities``); this module
re-exports them so provider-internal modules keep a single import site.
"""

from windagent_core.contracts.providers.model_capabilities import (
    KNOWN_MODEL_PROFILES,
    ModelCapability,
    ModelCapabilityProfile,
)

__all__ = [
    "ModelCapability",
    "ModelCapabilityProfile",
    "KNOWN_MODEL_PROFILES",
]
