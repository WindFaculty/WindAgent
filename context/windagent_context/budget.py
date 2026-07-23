"""
Token Budget Allocation & Truncation Manager for WindAgent Context Package.
Calculates token usage and enforces explicit section budgets.
"""

from __future__ import annotations
import logging
from typing import List, Tuple

from windagent_context.provenance import ContextItem

logger = logging.getLogger("windagent.context.budget")


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count (~4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class TokenBudgetManager:
    def __init__(
        self,
        total_limit: int = 128000,
        system_prompt_budget: int = 10000,
        tools_skills_budget: int = 20000,
        retrieval_context_budget: int = 60000,
        history_budget: int = 38000,
    ):
        self.total_limit = total_limit
        self.system_prompt_budget = system_prompt_budget
        self.tools_skills_budget = tools_skills_budget
        self.retrieval_context_budget = retrieval_context_budget
        self.history_budget = history_budget

    def fit_items(self, items: List[ContextItem], max_tokens: int) -> Tuple[List[ContextItem], bool]:
        """Fits context items into max_tokens limit sorted by confidence/freshness. Returns (fitted_items, truncated)."""
        # Sort items by confidence * freshness descending
        sorted_items = sorted(items, key=lambda i: (i.provenance.confidence * i.provenance.freshness), reverse=True)
        
        fitted: List[ContextItem] = []
        accumulated_tokens = 0
        truncated = False

        for item in sorted_items:
            cost = item.provenance.token_cost or estimate_tokens(item.content)
            if accumulated_tokens + cost <= max_tokens:
                fitted.append(item)
                accumulated_tokens += cost
            else:
                truncated = True

        if truncated:
            logger.info(f"Context truncated to fit max token budget ({max_tokens} tokens). Included {len(fitted)}/{len(items)} items.")

        return fitted, truncated
