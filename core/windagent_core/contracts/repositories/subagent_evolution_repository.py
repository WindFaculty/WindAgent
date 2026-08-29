"""Abstract repository protocol for Subagent Evolution persistence (Phase 13 — ban_ke_hoach_v1 §19, §24, §25).

Maintains domain decoupling: orchestration, evals, and API interact with
this protocol rather than concrete storage implementations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.subagent_evolution import (
    SubagentCandidate,
    SubagentPromotionDecision,
    SubagentSpecVersion,
)


class SubagentEvolutionRepositoryProtocol(Protocol):
    """Async repository protocol for Subagent Candidate, SpecVersion, and Promotion persistence and queries."""

    # Candidate operations
    async def get_candidate(self, candidate_id: str) -> Optional[SubagentCandidate]:
        """Retrieves a subagent candidate by ID."""
        ...

    async def save_candidate(self, candidate: SubagentCandidate) -> None:
        """Persists or updates a subagent candidate."""
        ...

    async def list_candidates(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SubagentCandidate]:
        """Lists subagent candidates matching filtering criteria."""
        ...

    # Spec operations
    async def get_spec(self, spec_id: str) -> Optional[SubagentSpecVersion]:
        """Retrieves a subagent spec version by ID."""
        ...

    async def get_spec_by_semver(self, role: str, version: str) -> Optional[SubagentSpecVersion]:
        """Retrieves a subagent spec version by role and semver string."""
        ...

    async def get_active_spec(self, role: str) -> Optional[SubagentSpecVersion]:
        """Retrieves the current active spec for a given subagent role."""
        ...

    async def save_spec(self, spec: SubagentSpecVersion) -> None:
        """Persists or updates a subagent spec version."""
        ...

    async def list_specs(
        self,
        role: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SubagentSpecVersion]:
        """Lists subagent specs matching filtering criteria."""
        ...

    # Promotion operations
    async def get_promotion(self, decision_id: str) -> Optional[SubagentPromotionDecision]:
        """Retrieves a subagent promotion decision by ID."""
        ...

    async def save_promotion(self, decision: SubagentPromotionDecision) -> None:
        """Persists or updates a subagent promotion decision."""
        ...

    async def list_promotions(
        self,
        role: Optional[str] = None,
        candidate_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SubagentPromotionDecision]:
        """Lists subagent promotion decisions matching filtering criteria."""
        ...

