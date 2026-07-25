"""
Context Builder for WindAgent Context Package (Phase 21).
Assembles structured prompt context using the full pipeline:
repository discovery → files/symbols → tool outputs → session context
→ project memory → token budget → dedup → compaction → provenance manifest.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

from windagent_context.provenance import ContextItem, ProvenanceManifest
from windagent_context.budget import TokenBudgetManager
from windagent_context.compaction import ContextCompactor
from windagent_context.repository.index import RepositoryIndex
from windagent_context.pipeline import ContextPipeline, ContextPipelineConfig

logger = logging.getLogger("windagent.context.builder")


class ContextBuilder:
    def __init__(
        self,
        budget_manager: Optional[TokenBudgetManager] = None,
        compactor: Optional[ContextCompactor] = None,
        repo_index: Optional[RepositoryIndex] = None,
        pipeline: Optional[ContextPipeline] = None,
    ):
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.compactor = compactor or ContextCompactor()
        self.repo_index = repo_index or RepositoryIndex()
        self.pipeline = pipeline or ContextPipeline(
            budget_manager=self.budget_manager,
            compactor=self.compactor,
            repo_index=self.repo_index,
        )

    def assemble_context(
        self,
        task_prompt: str,
        retrieved_items: Optional[List[ContextItem]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        file_items: Optional[List[ContextItem]] = None,
        tool_output_items: Optional[List[ContextItem]] = None,
        session_context_items: Optional[List[ContextItem]] = None,
        memory_items: Optional[List[ContextItem]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[ContextItem], bool, Optional[ProvenanceManifest]]:
        """Assembles prompt messages and context items using the full pipeline.
        
        Returns:
            (compacted_msgs, fitted_items, truncated, manifest)
        """
        # 1. Compact conversation history
        compacted_msgs = messages or []
        if messages:
            compacted_msgs = self.compactor.compact_conversation(messages)

        # 2. Run full context pipeline
        pipeline_result = self.pipeline.run(
            task_prompt=task_prompt,
            file_items=file_items,
            tool_output_items=tool_output_items,
            session_context_items=session_context_items,
            memory_items=memory_items,
        )

        fitted_items = pipeline_result["items"]
        truncated = pipeline_result["truncated"]
        manifest = pipeline_result.get("manifest")

        logger.info(
            f"Context assembled: {len(fitted_items)} items, "
            f"{'truncated' if truncated else 'full budget'}, "
            f"profile={pipeline_result['budget_profile']}"
        )

        return compacted_msgs, fitted_items, truncated, manifest

    def assemble_for_task_type(
        self,
        task_prompt: str,
        task_type: str,
        file_items: Optional[List[ContextItem]] = None,
        tool_output_items: Optional[List[ContextItem]] = None,
        session_context_items: Optional[List[ContextItem]] = None,
        memory_items: Optional[List[ContextItem]] = None,
    ) -> Tuple[List[ContextItem], bool, Optional[ProvenanceManifest]]:
        """Assembles context using a budget profile specific to the task type.
        Returns (items, truncated, manifest).
        """
        budget = TokenBudgetManager.for_task_type(task_type)
        config = ContextPipelineConfig(task_type=task_type)
        pipeline = ContextPipeline(
            budget_manager=budget,
            compactor=self.compactor,
            repo_index=self.repo_index,
            config=config,
        )

        result = pipeline.run(
            task_prompt=task_prompt,
            file_items=file_items,
            tool_output_items=tool_output_items,
            session_context_items=session_context_items,
            memory_items=memory_items,
        )

        return result["items"], result["truncated"], result.get("manifest")
