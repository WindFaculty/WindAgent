"""Context pipeline orchestrator for Agent Runtime context assembly.

Orchestrates the context assembly pipeline:
Task prompt -> file retrieval -> tool outputs -> session context -> memory
-> token allocation -> deduplication -> compaction -> provenance manifest.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from .budget import TokenBudgetManager
from .compaction import ContextCompactor
from .provenance import ContextItem, ProvenanceManifest

logger = logging.getLogger("windagent.agent_runtime.context.pipeline")

STAGE_REPO_DISCOVERY = "repository_discovery"
STAGE_FILE_RETRIEVAL = "file_retrieval"
STAGE_TOOL_OUTPUTS = "recent_tool_outputs"
STAGE_SESSION_CONTEXT = "session_context"
STAGE_PROJECT_MEMORY = "project_memory"
STAGE_TOKEN_ALLOCATION = "token_allocation"
STAGE_DEDUPLICATION = "deduplication"
STAGE_COMPACTION = "compaction"
STAGE_MANIFEST = "provenance_manifest"


@dataclass(slots=True)
class ContextPipelineConfig:
    task_type: str = "default"
    max_repository_items: int = 20
    max_file_items: int = 15
    max_tool_output_items: int = 10
    max_session_context_items: int = 10
    max_memory_items: int = 10
    enable_deduplication: bool = True
    enable_compaction: bool = True
    enable_provenance_manifest: bool = True


class ContextPipeline:
    def __init__(
        self,
        budget_manager: TokenBudgetManager | None = None,
        compactor: ContextCompactor | None = None,
        config: ContextPipelineConfig | None = None,
    ) -> None:
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.compactor = compactor or ContextCompactor()
        self.config = config or ContextPipelineConfig()
        self._pipeline_steps: list[str] = []

    def _record_step(self, step: str) -> None:
        self._pipeline_steps.append(step)
        logger.debug(f"Context pipeline step: {step}")

    def _extract_keywords(self, text: str) -> list[str]:
        words = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text)
        return list(dict.fromkeys(w.lower() for w in words))

    def _deduplicate_items(self, items: list[ContextItem]) -> list[ContextItem]:
        seen_hashes: set[str] = set()
        deduped: list[ContextItem] = []
        for item in items:
            h = item.content_hash or ""
            if h and h in seen_hashes:
                continue
            if h:
                seen_hashes.add(h)
            deduped.append(item)
        return deduped

    def _compact_items(self, items: list[ContextItem]) -> list[ContextItem]:
        compacted: list[ContextItem] = []
        for item in items:
            if len(item.content) > 1200:
                compacted_content, _ = self.compactor.compact_tool_result(
                    tool_name=item.provenance.source,
                    raw_output=item.content,
                    max_chars=800,
                )
                compacted.append(
                    ContextItem(
                        item_id=item.item_id,
                        content=compacted_content,
                        provenance=item.provenance,
                        token_count=max(1, len(compacted_content) // 4),
                        injection_marker=item.injection_marker,
                    )
                )
            else:
                compacted.append(item)
        return compacted

    def run(
        self,
        task_prompt: str,
        file_items: list[ContextItem] | None = None,
        tool_output_items: list[ContextItem] | None = None,
        session_context_items: list[ContextItem] | None = None,
        memory_items: list[ContextItem] | None = None,
        repo_items: list[ContextItem] | None = None,
    ) -> dict[str, Any]:
        """Runs the context assembly pipeline with provenance tracking."""
        self._pipeline_steps = []
        self._record_step("pipeline_start")

        # 1. Repository Discovery Stage
        self._record_step(STAGE_REPO_DISCOVERY)
        discovered_repo = repo_items or []

        # 2. File Retrieval Stage
        self._record_step(STAGE_FILE_RETRIEVAL)
        files = (file_items or [])[: self.config.max_file_items]

        # 3. Tool Outputs Stage
        self._record_step(STAGE_TOOL_OUTPUTS)
        tool_outputs = (tool_output_items or [])[: self.config.max_tool_output_items]

        # 4. Session Context Stage
        self._record_step(STAGE_SESSION_CONTEXT)
        session_items = (session_context_items or [])[: self.config.max_session_context_items]

        # 5. Project Memory Stage
        self._record_step(STAGE_PROJECT_MEMORY)
        memory = (memory_items or [])[: self.config.max_memory_items]

        combined_items: list[ContextItem] = []
        combined_items.extend(discovered_repo)
        combined_items.extend(files)
        combined_items.extend(tool_outputs)
        combined_items.extend(session_items)
        combined_items.extend(memory)

        total_input = len(combined_items)
        total_tokens_input = sum(item.token_count for item in combined_items)

        # 6. Token Allocation Stage
        self._record_step(STAGE_TOKEN_ALLOCATION)
        fitted_items, truncated = self.budget_manager.fit_items(
            items=combined_items,
            max_tokens=self.budget_manager.retrieval_context_budget,
        )

        # 7. Deduplication Stage
        self._record_step(STAGE_DEDUPLICATION)
        if self.config.enable_deduplication:
            fitted_items = self._deduplicate_items(fitted_items)

        # 8. Compaction Stage
        self._record_step(STAGE_COMPACTION)
        if self.config.enable_compaction:
            fitted_items = self._compact_items(fitted_items)

        self._record_step("pipeline_complete")

        result: dict[str, Any] = {
            "items": fitted_items,
            "truncated": truncated,
            "budget_profile": self.config.task_type,
            "pipeline_steps": list(self._pipeline_steps),
            "total_input_count": total_input,
            "total_output_count": len(fitted_items),
            "total_tokens_input": total_tokens_input,
            "total_tokens_output": sum(item.token_count for item in fitted_items),
        }

        # 9. Provenance Manifest Stage
        if self.config.enable_provenance_manifest:
            self._record_step(STAGE_MANIFEST)
            manifest_id = f"manifest_{uuid.uuid4().hex[:12]}"
            manifest = ProvenanceManifest.build(
                manifest_id=manifest_id,
                task_prompt=task_prompt,
                input_items=combined_items,
                output_items=fitted_items,
                truncated=truncated,
                budget_profile=self.config.task_type,
                pipeline_steps=list(self._pipeline_steps),
            )
            result["manifest"] = manifest

        return result
