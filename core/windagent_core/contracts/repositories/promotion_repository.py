"""Abstract repository protocol for PromotionDecision persistence (Phase 11).

Maintains domain decoupling: orchestration & API interact with
this protocol rather than concrete storage implementations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.promotion import PromotionDecision


class PromotionRepositoryProtocol(Protocol):
    """Async repository protocol for PromotionDecision persistence and queries."""

    async def get_decision(self, decision_id: str) -> Optional[PromotionDecision]:
        """Retrieves a promotion decision by ID."""
        ...

    async def save_decision(self, decision: PromotionDecision) -> None:
        """Persists or updates a promotion decision."""
        ...

    async def list_decisions(
        self,
        candidate_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[PromotionDecision]:
        """Lists promotion decisions matching criteria."""
        ...

