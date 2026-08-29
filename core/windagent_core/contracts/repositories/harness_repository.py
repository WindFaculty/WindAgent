"""Abstract repository protocol for Continual Harness snapshots and proposals.

Maintains domain decoupling: intelligence & orchestration interact with
this protocol rather than concrete storage implementations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.harness import HarnessVersion, RefinementProposal


class HarnessRepositoryProtocol(Protocol):
    """Async repository protocol for HarnessVersion and RefinementProposal persistence."""

    async def get_version(self, version_id: str) -> Optional[HarnessVersion]:
        """Retrieves a harness version by ID."""
        ...

    async def get_active_version(
        self,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Optional[HarnessVersion]:
        """Retrieves currently active harness version for scope."""
        ...

    async def save_version(self, version: HarnessVersion) -> None:
        """Persists or updates a harness version snapshot."""
        ...

    async def set_active_version(self, version_id: str) -> None:
        """Sets target version as active and deactivates prior active versions in scope."""
        ...

    async def list_versions(
        self,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[HarnessVersion]:
        """Lists harness versions in reverse chronological order."""
        ...

    async def save_proposal(self, proposal: RefinementProposal) -> None:
        """Persists or updates a refinement proposal."""
        ...

    async def get_proposal(self, refinement_id: str) -> Optional[RefinementProposal]:
        """Retrieves a refinement proposal by ID."""
        ...

    async def list_proposals(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[RefinementProposal]:
        """Lists refinement proposals."""
        ...

