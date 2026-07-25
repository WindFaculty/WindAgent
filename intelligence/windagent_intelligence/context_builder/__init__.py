"""
Context Builder Component for WindAgent Intelligence (Phase 22).
Intelligence facade that calls windagent_context for pipeline orchestration.
Does NOT create its own repository index or memory store.
"""

from windagent_intelligence.context_builder.builder import (
    IntelligenceContextBuilder, ContextAssemblyResult,
)

__all__ = ["IntelligenceContextBuilder", "ContextAssemblyResult"]
