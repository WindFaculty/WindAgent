"""
Context assembly, token budgeting, prompt formatting
"""

from windagent_core.version import PRODUCT_VERSION

__version__ = PRODUCT_VERSION
from windagent_context.builder import ContextBuilder
from windagent_context.budget import TokenBudgetManager
from windagent_context.compaction import ContextCompactor
from windagent_context.provenance import ContextItem, ProvenanceManifest
from windagent_context.pipeline import ContextPipeline, ContextPipelineConfig
from windagent_context.repository.index import RepositoryIndex
from windagent_context.services import ContextService

__all__ = [
    "ContextBuilder",
    "TokenBudgetManager",
    "ContextCompactor",
    "ContextItem",
    "ProvenanceManifest",
    "ContextPipeline",
    "ContextPipelineConfig",
    "RepositoryIndex",
    "ContextService",
]