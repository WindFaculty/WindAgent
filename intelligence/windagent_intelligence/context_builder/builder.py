"""
Intelligence Context Builder Facade (Phase 22).
Calls windagent_context for context assembly, retrieval, and provenance manifest generation.
Does NOT create its own repository index or memory store — delegates to context and memory packages.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_context import (
    ContextBuilder, ContextPipeline, ContextPipelineConfig,
    ContextItem, ProvenanceManifest, TokenBudgetManager,
)

logger = logging.getLogger("windagent.intelligence.context_builder")


@dataclass
class ContextAssemblyResult:
    """Result of intelligence context assembly."""
    items: List[ContextItem]
    truncated: bool
    budget_profile: str
    manifest: Optional[ProvenanceManifest] = None
    pipeline_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "item_count": len(self.items),
            "truncated": self.truncated,
            "budget_profile": self.budget_profile,
            "pipeline_steps": self.pipeline_steps,
        }
        if self.manifest:
            base["manifest"] = self.manifest.to_dict()
        return base


class IntelligenceContextBuilder:
    """Facade that delegates context assembly to windagent_context.
    Does NOT manage its own repository index or memory store.
    """

    def __init__(
        self,
        context_builder: Optional[ContextBuilder] = None,
        pipeline: Optional[ContextPipeline] = None,
    ):
        self._context_builder = context_builder or ContextBuilder()
        self._pipeline = pipeline or self._context_builder.pipeline

    def assemble(
        self,
        task_prompt: str,
        task_type: str = "default",
        file_items: Optional[List[ContextItem]] = None,
        tool_output_items: Optional[List[ContextItem]] = None,
        session_context_items: Optional[List[ContextItem]] = None,
        memory_items: Optional[List[ContextItem]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        include_manifest: bool = True,
    ) -> ContextAssemblyResult:
        """Assembles context for intelligence using the context pipeline.
        Delegates to windagent_context.ContextPipeline for all pipeline stages.
        """
        config = ContextPipelineConfig(
            task_type=task_type,
            enable_provenance_manifest=include_manifest,
        )
        pipeline = ContextPipeline(
            budget_manager=TokenBudgetManager.for_task_type(task_type),
            config=config,
        )

        result = pipeline.run(
            task_prompt=task_prompt,
            file_items=file_items,
            tool_output_items=tool_output_items,
            session_context_items=session_context_items,
            memory_items=memory_items,
        )

        return ContextAssemblyResult(
            items=result["items"],
            truncated=result["truncated"],
            budget_profile=result["budget_profile"],
            manifest=result.get("manifest"),
            pipeline_steps=result["pipeline_steps"],
        )

    def assemble_for_classification(self, task_prompt: str, task_type: str) -> ContextAssemblyResult:
        """Quick context assembly using task type budget profile.
        Suitable for pre-classification context gathering.
        """
        budget = TokenBudgetManager.for_task_type(task_type)
        config = ContextPipelineConfig(task_type=task_type, max_file_items=5)
        pipeline = ContextPipeline(budget_manager=budget, config=config)

        result = pipeline.run(task_prompt=task_prompt)
        return ContextAssemblyResult(
            items=result["items"],
            truncated=result["truncated"],
            budget_profile=result["budget_profile"],
            manifest=result.get("manifest"),
            pipeline_steps=result["pipeline_steps"],
        )

    def get_budget_profile_names(self) -> List[str]:
        """Returns available task type budget profile names."""
        from windagent_context.budget import TASK_TYPE_BUDGET_PROFILES
        return list(TASK_TYPE_BUDGET_PROFILES.keys())
