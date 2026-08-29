"""Abstract repository protocol for Skill Evolution persistence (Phase 12 — ban_ke_hoach_v1 §18, §24, §25).

Maintains domain decoupling: orchestration, evals, and API interact with
this protocol rather than concrete storage implementations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.skill_evolution import (
    SkillCandidate,
    SkillPromotionDecision,
    SkillVersion,
)


class SkillEvolutionRepositoryProtocol(Protocol):
    """Async repository protocol for Skill Candidate, Version, and Promotion persistence and queries."""

    # Candidate operations
    async def get_candidate(self, candidate_id: str) -> Optional[SkillCandidate]:
        """Retrieves a skill candidate by ID."""
        ...

    async def save_candidate(self, candidate: SkillCandidate) -> None:
        """Persists or updates a skill candidate."""
        ...

    async def list_candidates(
        self,
        skill_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillCandidate]:
        """Lists skill candidates matching filtering criteria."""
        ...

    # Version operations
    async def get_version(self, version_id: str) -> Optional[SkillVersion]:
        """Retrieves a skill version by ID."""
        ...

    async def get_version_by_semver(self, skill_id: str, version: str) -> Optional[SkillVersion]:
        """Retrieves a skill version by skill_id and semver version string."""
        ...

    async def get_active_version(self, skill_id: str) -> Optional[SkillVersion]:
        """Retrieves the current active version for a given skill_id."""
        ...

    async def save_version(self, version: SkillVersion) -> None:
        """Persists or updates a skill version."""
        ...

    async def list_versions(
        self,
        skill_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillVersion]:
        """Lists skill versions matching filtering criteria."""
        ...

    # Promotion operations
    async def get_promotion(self, decision_id: str) -> Optional[SkillPromotionDecision]:
        """Retrieves a skill promotion decision by ID."""
        ...

    async def save_promotion(self, decision: SkillPromotionDecision) -> None:
        """Persists or updates a skill promotion decision."""
        ...

    async def list_promotions(
        self,
        skill_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillPromotionDecision]:
        """Lists skill promotion decisions matching filtering criteria."""
        ...

