"""Intelligence Pipeline Facade for WindAgent Intelligence Package (Phase 2).

Provides application service composition for intelligence capabilities (task classification,
planning, context building, model routing).
"""

from __future__ import annotations
import logging
from typing import Any, Optional

from windagent_intelligence.task_classifier import TaskClassifier
from windagent_intelligence.planner import TaskPlanner
from windagent_intelligence.context_builder import IntelligenceContextBuilder

logger = logging.getLogger("windagent.intelligence.pipeline")


class IntelligencePipeline:
    """Intelligence pipeline facade for composition roots."""

    def __init__(
        self,
        provider_registry: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
    ):
        self.provider_registry = provider_registry
        self.tool_registry = tool_registry
        self.classifier = TaskClassifier()
        self.planner = TaskPlanner()
        self.context_builder = IntelligenceContextBuilder()

    async def run_pipeline(self, prompt: str, **kwargs: Any) -> dict:
        """Executes classification and planning pipeline over user prompt."""
        classification = self.classifier.classify(prompt)
        return {
            "classification": classification,
            "prompt": prompt,
        }

    async def close(self) -> None:
        """Closes pipeline and releases resources."""
        return None


__all__ = ["IntelligencePipeline"]
