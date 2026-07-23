"""
Legacy import shim for windagent_providers.capabilities.
Re-exports capabilities from windagent_providers.base.capabilities.
"""

from windagent_providers.base.capabilities import (
    ModelCapability,
    ModelCapabilityProfile,
    KNOWN_MODEL_PROFILES,
)

__all__ = [
    "ModelCapability",
    "ModelCapabilityProfile",
    "KNOWN_MODEL_PROFILES",
]
