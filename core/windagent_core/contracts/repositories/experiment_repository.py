"""Abstract repository protocol for Experiment persistence (Phase 11).

Maintains domain decoupling: evals & orchestration interact with
this protocol rather than concrete storage implementations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.experiment import Experiment


class ExperimentRepositoryProtocol(Protocol):
    """Async repository protocol for Experiment persistence and queries."""

    async def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Retrieves an experiment by ID."""
        ...

    async def save_experiment(self, experiment: Experiment) -> None:
        """Persists or updates an experiment record."""
        ...

    async def list_experiments(
        self,
        candidate_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Experiment]:
        """Lists experiments matching criteria in reverse chronological order."""
        ...

