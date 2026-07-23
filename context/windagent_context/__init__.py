"""
WindAgent Context Package (V2 Architecture).
Context assembly, provenance tracking, token budgeting, repository intelligence, and compaction.
"""

from windagent_context.provenance import ContextItemProvenance, ContextItem
from windagent_context.budget import TokenBudgetManager, estimate_tokens
from windagent_context.repository.index import RepositoryIndex
from windagent_context.compaction import ContextCompactor
from windagent_context.builder import ContextBuilder

__version__ = "0.3.0"

__all__ = [
    "ContextItemProvenance", "ContextItem",
    "TokenBudgetManager", "estimate_tokens",
    "RepositoryIndex",
    "ContextCompactor",
    "ContextBuilder",
]
