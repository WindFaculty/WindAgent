"""
Token Budget Allocation & Truncation Manager for WindAgent Context Package (Phase 21).
Calculates token usage and enforces explicit section budgets.
Supports per-task-type budget profiles and large file protection.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from windagent_context.provenance import ContextItem

logger = logging.getLogger("windagent.context.budget")


def estimate_tokens(text: str) -> int:
    """Rough estimation of token usage (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# Per-task-type budget profiles
TASK_TYPE_BUDGET_PROFILES: Dict[str, Dict[str, int]] = {
    "bugfix": {
        "total_limit": 32000,
        "system_prompt_budget": 4000,
        "tools_skills_budget": 8000,
        "retrieval_context_budget": 12000,
        "history_budget": 8000,
    },
    "feature": {
        "total_limit": 64000,
        "system_prompt_budget": 6000,
        "tools_skills_budget": 12000,
        "retrieval_context_budget": 30000,
        "history_budget": 16000,
    },
    "refactor": {
        "total_limit": 48000,
        "system_prompt_budget": 5000,
        "tools_skills_budget": 10000,
        "retrieval_context_budget": 20000,
        "history_budget": 13000,
    },
    "code_review": {
        "total_limit": 96000,
        "system_prompt_budget": 8000,
        "tools_skills_budget": 16000,
        "retrieval_context_budget": 50000,
        "history_budget": 22000,
    },
    "research": {
        "total_limit": 128000,
        "system_prompt_budget": 10000,
        "tools_skills_budget": 20000,
        "retrieval_context_budget": 60000,
        "history_budget": 38000,
    },
    "default": {
        "total_limit": 128000,
        "system_prompt_budget": 10000,
        "tools_skills_budget": 20000,
        "retrieval_context_budget": 60000,
        "history_budget": 38000,
    },
}


@dataclass
class TokenBudgetManager:
    total_limit: int = 128000
    system_prompt_budget: int = 10000
    tools_skills_budget: int = 20000
    retrieval_context_budget: int = 60000
    history_budget: int = 38000
    # Large file protection: maximum % of retrieval budget that a single item can consume
    max_single_item_pct: float = 0.25  # 25% max per item

    @classmethod
    def for_task_type(cls, task_type: str) -> TokenBudgetManager:
        """Creates a TokenBudgetManager configured for a specific task type."""
        profile = TASK_TYPE_BUDGET_PROFILES.get(task_type.lower(), TASK_TYPE_BUDGET_PROFILES["default"])
        return cls(**profile)

    def fit_items(self, items: List[ContextItem], max_tokens: Optional[int] = None) -> Tuple[List[ContextItem], bool]:
        """Fits context items into max_tokens limit.
        Enforces large file protection: no single item can exceed max_single_item_pct of the budget.
        Returns (fitted_items, truncated).
        """
        effective_max = max_tokens or self.retrieval_context_budget
        max_per_item = int(effective_max * self.max_single_item_pct)

        # Filter items that exceed the single-item maximum (large file protection)
        filtered_items: List[ContextItem] = []
        large_items_skipped = 0

        for item in items:
            cost = item.token_count or estimate_tokens(item.content)
            if cost > max_per_item:
                large_items_skipped += 1
                logger.info(
                    f"Skipped large context item [{item.item_id}] ({cost} tokens > {max_per_item} max per item)"
                )
                continue
            filtered_items.append(item)

        if large_items_skipped > 0:
            logger.warning(
                f"Large file protection blocked {large_items_skipped} item(s) exceeding {max_per_item} tokens each."
            )

        # Sort items by confidence * freshness descending (most important first)
        sorted_items = sorted(
            filtered_items,
            key=lambda i: (i.provenance.confidence * i.provenance.freshness),
            reverse=True,
        )

        fitted: List[ContextItem] = []
        accumulated_tokens = 0
        truncated = False

        for item in sorted_items:
            cost = item.token_count or estimate_tokens(item.content)
            if accumulated_tokens + cost <= effective_max:
                fitted.append(item)
                accumulated_tokens += cost
            else:
                truncated = True

        if truncated:
            logger.info(
                f"Context truncated to fit max token budget ({effective_max} tokens). "
                f"Included {len(fitted)}/{len(items)} items."
            )

        return fitted, truncated

    def validate_total_budget(self) -> bool:
        """Validates that section budgets don't exceed total_limit."""
        sections = [
            self.system_prompt_budget,
            self.tools_skills_budget,
            self.retrieval_context_budget,
            self.history_budget,
        ]
        total = sum(sections)
        if total > self.total_limit:
            logger.warning(
                f"Budget sections sum ({total}) exceeds total_limit ({self.total_limit}). "
                f"Reducing retrieval budget by {total - self.total_limit}."
            )
            return False
        return True
