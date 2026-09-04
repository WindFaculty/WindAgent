"""Context builder for Agent Runtime context assembly.

Assembles structured prompt context and messages using token budgeting,
compaction, deduplication, and provenance manifests.
"""

from __future__ import annotations

import logging
from typing import Any

from .budget import TokenBudgetManager
from .compaction import ContextCompactor
from .pipeline import ContextPipeline, ContextPipelineConfig
from .provenance import ContextItem, ContextItemProvenance, ProvenanceManifest, SourceType

logger = logging.getLogger("windagent.agent_runtime.context.builder")


class ContextBuilder:
    def __init__(
        self,
        budget_manager: TokenBudgetManager | None = None,
        compactor: ContextCompactor | None = None,
        pipeline: ContextPipeline | None = None,
    ) -> None:
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.compactor = compactor or ContextCompactor()
        self.pipeline = pipeline or ContextPipeline(
            budget_manager=self.budget_manager,
            compactor=self.compactor,
        )

    def create_context_item(
        self,
        item_id: str,
        content: str,
        source: str = "",
        source_type: str | SourceType = SourceType.FILE_CONTENT,
        retrieval_reason: str = "",
        confidence: float = 1.0,
        file_path: str | None = None,
        line_range: str | None = None,
        is_external: bool = False,
    ) -> ContextItem:
        if isinstance(source_type, SourceType):
            stype = source_type
        else:
            try:
                stype = SourceType(source_type)
            except ValueError:
                stype = SourceType.FILE_CONTENT

        return ContextItem(
            item_id=item_id,
            content=content,
            provenance=ContextItemProvenance(
                source=source,
                source_type=stype,
                retrieval_reason=retrieval_reason,
                confidence=confidence,
                file_path=file_path,
                line_range=line_range,
                is_external_content=is_external,
            ),
        )

    def assemble_context(
        self,
        task_prompt: str,
        messages: list[dict[str, Any]] | None = None,
        file_items: list[ContextItem] | None = None,
        tool_output_items: list[ContextItem] | None = None,
        session_context_items: list[ContextItem] | None = None,
        memory_items: list[ContextItem] | None = None,
        repo_items: list[ContextItem] | None = None,
    ) -> tuple[list[dict[str, Any]], list[ContextItem], bool, ProvenanceManifest | None]:
        """Assembles conversation messages and context items with compaction and budgeting.

        Returns:
            (compacted_messages, fitted_items, truncated, manifest)
        """
        # 1. Compact conversation history if messages provided
        compacted_msgs: list[dict[str, Any]] = []
        if messages:
            compacted_msgs = self.compactor.compact_conversation(messages)

        # 2. Run context pipeline
        pipeline_result = self.pipeline.run(
            task_prompt=task_prompt,
            file_items=file_items,
            tool_output_items=tool_output_items,
            session_context_items=session_context_items,
            memory_items=memory_items,
            repo_items=repo_items,
        )

        fitted_items = pipeline_result["items"]
        truncated = pipeline_result["truncated"]
        manifest = pipeline_result.get("manifest")

        logger.info(
            f"Context assembled: {len(fitted_items)} items, "
            f"{'truncated' if truncated else 'within budget'}, "
            f"profile={pipeline_result['budget_profile']}"
        )

        return compacted_msgs, fitted_items, truncated, manifest

    def assemble_for_task_type(
        self,
        task_prompt: str,
        task_type: str,
        file_items: list[ContextItem] | None = None,
        tool_output_items: list[ContextItem] | None = None,
        session_context_items: list[ContextItem] | None = None,
        memory_items: list[ContextItem] | None = None,
        repo_items: list[ContextItem] | None = None,
    ) -> tuple[list[ContextItem], bool, ProvenanceManifest | None]:
        """Assembles context items using a specific task type profile."""
        budget = TokenBudgetManager.for_task_type(task_type)
        config = ContextPipelineConfig(task_type=task_type)
        pipeline = ContextPipeline(
            budget_manager=budget,
            compactor=self.compactor,
            config=config,
        )

        result = pipeline.run(
            task_prompt=task_prompt,
            file_items=file_items,
            tool_output_items=tool_output_items,
            session_context_items=session_context_items,
            memory_items=memory_items,
            repo_items=repo_items,
        )

        return result["items"], result["truncated"], result.get("manifest")
