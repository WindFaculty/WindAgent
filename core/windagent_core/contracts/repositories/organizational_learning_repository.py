"""Abstract repository protocol for Organizational Learning & Learned Rules persistence (Phase 14 — ban_ke_hoach_v1 §20, §23, §24, §25).

Decouples core orchestration, intelligence, and evals from concrete SQL storage implementations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.organizational_learning import (
    ConflictResolutionRecord,
    KnowledgeVisibilityScope,
    LearnedRule,
    LearnedRuleState,
    MultiAgentAttributionRecord,
)


class OrganizationalLearningRepositoryProtocol(Protocol):
    """Async repository protocol for Learned Rules, Conflict Resolutions, and Multi-Agent Attributions."""

    # Learned Rule Operations
    async def get_rule(self, rule_id: str) -> Optional[LearnedRule]:
        """Retrieves a learned rule by its unique rule ID."""
        ...

    async def save_rule(self, rule: LearnedRule) -> None:
        """Persists or updates a learned rule."""
        ...

    async def list_rules(
        self,
        domain: Optional[str] = None,
        state: Optional[LearnedRuleState] = None,
        scope: Optional[KnowledgeVisibilityScope] = None,
        target_role: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[LearnedRule]:
        """Lists learned rules matching optional filters."""
        ...

    async def query_active_rules(
        self,
        domain: str,
        target_role: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[LearnedRule]:
        """Queries all PROMOTED active rules applicable to a domain, role, and project."""
        ...

    # Conflict Resolution Records
    async def get_conflict_resolution(self, resolution_id: str) -> Optional[ConflictResolutionRecord]:
        """Retrieves a conflict resolution audit record by ID."""
        ...

    async def save_conflict_resolution(self, record: ConflictResolutionRecord) -> None:
        """Persists a conflict resolution audit record."""
        ...

    async def list_conflict_resolutions(
        self,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[ConflictResolutionRecord]:
        """Lists recent conflict resolutions."""
        ...

    # Multi-Agent Attribution Records
    async def get_attribution(self, attribution_id: str) -> Optional[MultiAgentAttributionRecord]:
        """Retrieves a multi-agent attribution record by ID."""
        ...

    async def save_attribution(self, record: MultiAgentAttributionRecord) -> None:
        """Persists a multi-agent performance attribution record."""
        ...

    async def list_attributions(
        self,
        episode_id: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[MultiAgentAttributionRecord]:
        """Lists multi-agent attribution records."""
        ...

