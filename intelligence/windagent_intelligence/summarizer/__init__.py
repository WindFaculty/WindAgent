"""
Summarizer Component for WindAgent Intelligence (Phase 22).
Summarizes context items and tool outputs by provenance, without becoming the sole source of truth.
"""

from windagent_intelligence.summarizer.summarizer import (
    ContextSummarizer, SummarizationResult, SummarizationStrategy,
)

__all__ = ["ContextSummarizer", "SummarizationResult", "SummarizationStrategy"]
