"""
Context Builder for WindAgent Context Package.
Assembles structured prompt context with provenance, token budgeting, and compaction.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple

from windagent_context.provenance import ContextItem
from windagent_context.budget import TokenBudgetManager
from windagent_context.compaction import ContextCompactor
from windagent_context.repository.index import RepositoryIndex

logger = logging.getLogger("windagent.context.builder")


class ContextBuilder:
    def __init__(
        self,
        budget_manager: Optional[TokenBudgetManager] = None,
        compactor: Optional[ContextCompactor] = None,
        repo_index: Optional[RepositoryIndex] = None,
    ):
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.compactor = compactor or ContextCompactor()
        self.repo_index = repo_index or RepositoryIndex()

    def assemble_context(
        self,
        task_prompt: str,
        retrieved_items: List[ContextItem],
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[ContextItem], bool]:
        """Assembles prompt messages and context items within token budget limits."""
        # 1. Compact conversation history
        compacted_msgs = self.compactor.compact_conversation(messages)

        # 2. Fit retrieval context items within token budget
        fitted_items, truncated = self.budget_manager.fit_items(
            items=retrieved_items,
            max_tokens=self.budget_manager.retrieval_context_budget,
        )

        return compacted_msgs, fitted_items, truncated
