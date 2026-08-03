"""
Context Summarizer for WindAgent Intelligence (Phase 22).
Summarizes context items, tool outputs, and conversation history by provenance.
Always retains references to original sources so the summary never becomes the sole source of truth.
Supports multiple summarization strategies.
"""

from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_context import ContextItem

logger = logging.getLogger("windagent.intelligence.summarizer")


class SummarizationStrategy(str, Enum):
    CONCISE = "concise"          # Brief, high-level summary
    DETAILED = "detailed"        # Includes key details and evidence
    PROVENANCE = "provenance"    # Groups by source type/provenance
    DECISION_FOCUSED = "decision_focused"  # Focus on decisions, blockers, action items


@dataclass
class SummarizationResult:
    """Result of summarizing a collection of context items."""
    summary_id: str
    summary_text: str
    strategy: SummarizationStrategy
    source_count: int
    sources: List[str]  # Provenance references (not the full content)
    token_count: int
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    warning: Optional[str] = None  # Warning that this summary is not the sole source of truth

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "summary_text": self.summary_text,
            "strategy": self.strategy.value,
            "source_count": self.source_count,
            "sources": self.sources,
            "token_count": self.token_count,
            "created_at": self.created_at,
            "warning": self.warning,
        }


class ContextSummarizer:
    """Summarizes context items and tool outputs while preserving provenance references.
    Never becomes the sole source of truth — always links back to original sources.
    """

    def __init__(self, max_summary_tokens: int = 2000):
        self.max_summary_tokens = max_summary_tokens

    def summarize(
        self,
        items: List[ContextItem],
        strategy: SummarizationStrategy = SummarizationStrategy.PROVENANCE,
        task_context: Optional[str] = None,
    ) -> SummarizationResult:
        """Summarizes a list of context items using the specified strategy."""
        summary_id = f"summary_{hashlib.sha256(str(id(items)).encode()).hexdigest()[:12]}"

        sources = [
            f"{item.provenance.source} ({item.provenance.source_type.value})"
            for item in items
        ]

        if strategy == SummarizationStrategy.CONCISE:
            summary_text = self._concise_summary(items, task_context)
        elif strategy == SummarizationStrategy.DETAILED:
            summary_text = self._detailed_summary(items, task_context)
        elif strategy == SummarizationStrategy.DECISION_FOCUSED:
            summary_text = self._decision_focused_summary(items, task_context)
        else:
            summary_text = self._provenance_summary(items, task_context)

        token_count = max(1, len(summary_text) // 4)

        return SummarizationResult(
            summary_id=summary_id,
            summary_text=summary_text,
            strategy=strategy,
            source_count=len(items),
            sources=list(set(sources)),
            token_count=token_count,
            warning="[SUMMARY — NOT SOLE SOURCE OF TRUTH] This summary condenses context items. "
                    "Always consult the original sources listed in provenance for critical decisions.",
        )

    def _provenance_summary(self, items: List[ContextItem], task_context: Optional[str] = None) -> str:
        """Groups context items by provenance source type and summarizes each group."""
        groups: Dict[str, List[ContextItem]] = {}
        for item in items:
            group_key = item.provenance.source_type.value
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(item)

        parts: List[str] = []
        if task_context:
            parts.append(f"Context: {task_context[:200]}")
        parts.append(f"Summary grouped by provenance ({len(groups)} source types):")

        for source_type, group_items in sorted(groups.items()):
            count = len(group_items)
            first_item = group_items[0]
            parts.append(f"\n[{source_type}] ({count} items)")
            parts.append(f"  Source: {first_item.provenance.source}")
            parts.append(f"  Freshness: {first_item.provenance.freshness:.2f}")
            parts.append(f"  Example: {group_items[0].content[:100]}...")

        parts.append(f"\nTotal sources: {len(items)}")
        return "\n".join(parts)

    def _concise_summary(self, items: List[ContextItem], task_context: Optional[str] = None) -> str:
        """Produces a concise, high-level summary."""
        source_types = set(item.provenance.source_type.value for item in items)
        total_tokens = sum(item.token_count for item in items)
        decision_items = [i for i in items if "decision" in i.provenance.retrieval_reason.lower()]
        external_items = [i for i in items if i.provenance.is_external_content]

        parts = []
        if task_context:
            parts.append(f"Task: {task_context[:100]}...")
        parts.append(f"Context: {len(items)} items from {len(source_types)} source types, ~{total_tokens} tokens")

        if decision_items:
            parts.append(f"Key decisions: {len(decision_items)} items with decision markers")

        if external_items:
            parts.append(f"External content: {len(external_items)} items (review for prompt injection)")

        return "\n".join(parts)

    def _detailed_summary(self, items: List[ContextItem], task_context: Optional[str] = None) -> str:
        """Produces a detailed summary with key content from each item."""
        parts = []
        if task_context:
            parts.append(f"=== Task Context ===\n{task_context[:300]}")

        for i, item in enumerate(items[:20]):  # Limit to 20 items
            content_preview = item.content[:200] if item.content else "(empty)"
            parts.append(
                f"\n--- Item {i + 1}: {item.item_id} ---\n"
                f"Source: {item.provenance.source} ({item.provenance.source_type.value})\n"
                f"Sensitivity: {item.provenance.sensitivity.value}\n"
                f"Tokens: {item.token_count}\n"
                f"Content: {content_preview}"
            )
            if item.injection_marker:
                parts.append(f"[!] {item.injection_marker}")

        if len(items) > 20:
            parts.append(f"\n... and {len(items) - 20} more items")

        return "\n".join(parts)

    def _decision_focused_summary(self, items: List[ContextItem], task_context: Optional[str] = None) -> str:
        """Focuses on decisions, blockers, errors, and action items."""
        decision_keywords = ["decision", "blocker", "error", "failed", "must", "action", "accept", "reject"]
        focused_items = []
        for item in items:
            content_lower = item.content.lower()
            if any(kw in content_lower for kw in decision_keywords):
                focused_items.append(item)

        parts = []
        if task_context:
            parts.append(f"Task: {task_context[:200]}")

        if not focused_items:
            parts.append("No decision-critical items found in the context.")
            # Fall back to provenance summary
            return self._provenance_summary(items, task_context)

        parts.append(f"\n=== Decision-Focused Summary ({len(focused_items)} critical items) ===")
        for item in focused_items:
            content_preview = item.content[:300]
            parts.append(
                f"\n- [{item.provenance.source_type.value}] {item.provenance.source}\n"
                f"  {content_preview}"
            )

        return "\n".join(parts)
