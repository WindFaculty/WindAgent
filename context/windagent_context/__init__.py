"""
WindAgent Context Package (V2 Architecture — Phase 21).
Context assembly pipeline, provenance tracking, token budgeting,
repository intelligence, compaction, and provenance manifest.
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_context.provenance import (
    ContextItemProvenance, ContextItem,
    SensitivityLevel, SourceType,
    ProvenanceManifest, ProvenanceManifestEntry,
)
from windagent_context.budget import TokenBudgetManager, estimate_tokens, TASK_TYPE_BUDGET_PROFILES
from windagent_context.repository.index import RepositoryIndex
from windagent_context.compaction import ContextCompactor
from windagent_context.builder import ContextBuilder
from windagent_context.pipeline import ContextPipeline, ContextPipelineConfig

__version__ = PRODUCT_VERSION
__all__ = [
    "ContextItemProvenance", "ContextItem",
    "SensitivityLevel", "SourceType",
    "ProvenanceManifest", "ProvenanceManifestEntry",
    "TokenBudgetManager", "estimate_tokens", "TASK_TYPE_BUDGET_PROFILES",
    "RepositoryIndex",
    "ContextCompactor",
    "ContextBuilder",
    "ContextPipeline", "ContextPipelineConfig",
]
