"""
Model ID Parser & Normalizer for WindAgent Provider Subsystem V3.

Since Phase 3 the pure normalization logic lives in core; this module re-exports
it so provider-internal modules keep a single import site.
"""

from windagent_core.contracts.providers.model_normalizer import (
    NormalizedModelInfo,
    normalize_model_id,
)

__all__ = ["NormalizedModelInfo", "normalize_model_id"]