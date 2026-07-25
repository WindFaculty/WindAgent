"""
Context Pipeline Orchestrator for WindAgent Context Package (Phase 21).
Orchestrates the full context assembly pipeline:
Task → repository discovery → relevant files/symbols → recent tool outputs
→ session context → project memory → token allocation → deduplication
→ compaction → provenance manifest

Each stage produces context items with full provenance tracking.
"""

from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from windagent_context.provenance import (
    ContextItem, ContextItemProvenance, ProvenanceManifest,
    SourceType, SensitivityLevel,
)
from windagent_context.budget import TokenBudgetManager, estimate_tokens
from windagent_context.compaction import ContextCompactor
from windagent_context.repository.index import RepositoryIndex

logger = logging.getLogger("windagent.context.pipeline")

STAGE_REPO_DISCOVERY = "repository_discovery"
STAGE_FILE_RETRIEVAL = "file_retrieval"
STAGE_TOOL_OUTPUTS = "recent_tool_outputs"
STAGE_SESSION_CONTEXT = "session_context"
STAGE_PROJECT_MEMORY = "project_memory"
STAGE_TOKEN_ALLOCATION = "token_allocation"
STAGE_DEDUPLICATION = "deduplication"
STAGE_COMPACTION = "compaction"
STAGE_MANIFEST = "provenance_manifest"


@dataclass
class ContextPipelineConfig:
    """Configuration for the context pipeline."""
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
    """Orchestrates the full context assembly pipeline with provenance tracking."""

    def __init__(
        self,
        budget_manager: Optional[TokenBudgetManager] = None,
        compactor: Optional[ContextCompactor] = None,
        repo_index: Optional[RepositoryIndex] = None,
        config: Optional[ContextPipelineConfig] = None,
    ):
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.compactor = compactor or ContextCompactor()
        self.repo_index = repo_index or RepositoryIndex()
        self.config = config or ContextPipelineConfig()
        self._pipeline_steps: List[str] = []

    def _record_step(self, step: str) -> None:
        self._pipeline_steps.append(step)
        logger.debug(f"Pipeline step: {step}")

    def run(
        self,
        task_prompt: str,
        file_items: Optional[List[ContextItem]] = None,
        tool_output_items: Optional[List[ContextItem]] = None,
        session_context_items: Optional[List[ContextItem]] = None,
        memory_items: Optional[List[ContextItem]] = None,
    ) -> Dict[str, Any]:
        """Runs the full context assembly pipeline.
        
        Args:
            task_prompt: The original task prompt.
            file_items: Context items from file/symbol retrieval.
            tool_output_items: Context items from recent tool outputs.
            session_context_items: Context items from session history.
            memory_items: Context items from memory (project/session/working).
            
        Returns:
            Dict with keys:
                - items: final list of ContextItems
                - manifest: ProvenanceManifest (if enabled)
                - truncated: bool
                - budget_profile: str
                - pipeline_steps: List[str]
        """
        self._pipeline_steps = []
        self._record_step("pipeline_start")

        # 1. Repository Discovery Stage
        self._record_step(STAGE_REPO_DISCOVERY)
        repo_items = self._discover_repository_items(task_prompt)

        # 2. File Retrieval Stage
        self._record_step(STAGE_FILE_RETRIEVAL)
        files = file_items or []

        # 3. Tool Outputs Stage
        self._record_step(STAGE_TOOL_OUTPUTS)
        tool_outputs = tool_output_items or []

        # 4. Session Context Stage
        self._record_step(STAGE_SESSION_CONTEXT)
        session_items = session_context_items or []

        # 5. Project Memory Stage
        self._record_step(STAGE_PROJECT_MEMORY)
        memory = memory_items or []

        # Combine all items with their source stage tags
        all_items: List[Tuple[ContextItem, str]] = []
        for item in repo_items:
            all_items.append((item, STAGE_REPO_DISCOVERY))
        for item in files:
            all_items.append((item, STAGE_FILE_RETRIEVAL))
        for item in tool_outputs:
            all_items.append((item, STAGE_TOOL_OUTPUTS))
        for item in session_items:
            all_items.append((item, STAGE_SESSION_CONTEXT))
        for item in memory:
            all_items.append((item, STAGE_PROJECT_MEMORY))

        total_input = len(all_items)
        total_tokens_input = sum(item.token_count for item, _ in all_items)

        # Extract just the items
        combined_items = [item for item, _ in all_items]

        # 6. Token Allocation Stage (budget fitting with large file protection)
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

        # 9. Provenance Manifest Stage
        result: Dict[str, Any] = {
            "items": fitted_items,
            "truncated": truncated,
            "budget_profile": self.config.task_type,
            "pipeline_steps": list(self._pipeline_steps),
            "total_input_count": total_input,
            "total_output_count": len(fitted_items),
            "total_tokens_input": total_tokens_input,
            "total_tokens_output": sum(item.token_count for item in fitted_items),
        }

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

    # ------------------------------------------------------------------
    # Pipeline Stages
    # ------------------------------------------------------------------

    def _discover_repository_items(self, task_prompt: str) -> List[ContextItem]:
        """Stage 1: Repository discovery from task prompt.
        Uses repository index to find relevant symbols and files.
        """
        items = []

        # Discover symbols from task prompt keywords
        for keyword in self._extract_keywords(task_prompt):
            symbol_items = self.repo_index.retrieve_symbol(keyword, max_results=self.config.max_repository_items)
            items.extend(symbol_items)

        # Trim to configured max
        return items[:self.config.max_repository_items]

    def _deduplicate_items(self, items: List[ContextItem]) -> List[ContextItem]:
        """Stage 7: Deduplicate context items by content_hash.
        When duplicates are found, keep the one with higher freshness.
        """
        seen_hashes: Dict[str, ContextItem] = {}
        deduped: List[ContextItem] = []

        for item in items:
            h = item.content_hash
            if h and h in seen_hashes:
                existing = seen_hashes[h]
                if item.provenance.freshness > existing.provenance.freshness:
                    # Replace with fresher version
                    deduped.remove(existing)
                    deduped.append(item)
                    seen_hashes[h] = item
                else:
                    logger.debug(f"Deduplicated item [{item.item_id}] (hash: {h[:12]}...)")
            else:
                if h:
                    seen_hashes[h] = item
                deduped.append(item)

        if len(deduped) < len(items):
            logger.info(f"Deduplication removed {len(items) - len(deduped)} duplicate item(s).")

        return deduped

    def _compact_items(self, items: List[ContextItem]) -> List[ContextItem]:
        """Stage 8: Compact individual items if their content exceeds thresholds."""
        compacted_items = []

        for item in items:
            content_len = len(item.content)
            if content_len > 2000:  # Only compact items > 2000 chars
                compacted_text, ref = self.compactor.compact_tool_result(
                    tool_name=item.provenance.source,
                    raw_output=item.content,
                    max_chars=800,
                )
                # Create a new item with compacted content
                compacted_item = ContextItem(
                    item_id=item.item_id,
                    content=compacted_text,
                    provenance=item.provenance,
                    content_hash=item.content_hash,
                    token_count=estimate_tokens(compacted_text),
                    injection_marker=item.injection_marker,
                )
                compacted_items.append(compacted_item)
            else:
                compacted_items.append(item)

        return compacted_items

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_keywords(self, text: str) -> List[str]:
        """Extracts keywords from task prompt for repository discovery.
        Splits on common separators and filters out noise words.
        """
        import re
        # Split on whitespace, punctuation, and camelCase
        words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)', text)
        # Filter noise words and short words
        noise = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "this", "that", "these", "those", "it", "its", "to", "of",
                 "in", "for", "on", "with", "as", "at", "by", "from", "and",
                 "or", "but", "not", "we", "i", "you", "he", "she", "they",
                 "what", "how", "why", "when", "where", "which", "who",
                 "please", "can", "could", "would", "should", "will", "may",
                 "might", "do", "does", "did", "has", "have", "had", "need"}
        keywords = [w.lower() for w in words if len(w) >= 3 and w.lower() not in noise]
        return list(set(keywords))[:10]  # Return at most 10 unique keywords
