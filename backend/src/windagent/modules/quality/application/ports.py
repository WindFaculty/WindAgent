"""Persistence and transaction scope ports for Quality."""

from __future__ import annotations

from typing import Protocol, Self, runtime_checkable

from windagent.kernel.events import EventEnvelope

from ..domain.evals import (
    EvaluationDataset,
    EvaluationRunAggregate,
)
from ..domain.regression import BaselineComparison
from ..domain.verification import VerificationSuiteReport


@runtime_checkable
class QualityStore(Protocol):
    """Repository port for persisting quality evaluation data."""

    async def get_evaluation_run(self, run_id: str) -> EvaluationRunAggregate | None:
        """Fetch evaluation run aggregate by ID."""

    async def list_evaluation_runs(
        self,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvaluationRunAggregate]:
        """List evaluation runs with optional filtering."""

    async def save_evaluation_run(
        self, aggregate: EvaluationRunAggregate, expected_version: int | None = None
    ) -> None:
        """Persist evaluation run aggregate with CAS check."""

    async def get_dataset(self, dataset_id: str) -> EvaluationDataset | None:
        """Fetch evaluation dataset by ID."""

    async def list_datasets(self, limit: int = 50, offset: int = 0) -> list[EvaluationDataset]:
        """List benchmark datasets."""

    async def save_dataset(self, dataset: EvaluationDataset) -> None:
        """Persist evaluation dataset."""

    async def get_verification_report(self, report_id: str) -> VerificationSuiteReport | None:
        """Fetch verification report by ID."""

    async def list_verification_reports(
        self, target_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[VerificationSuiteReport]:
        """List verification reports."""

    async def save_verification_report(self, report: VerificationSuiteReport) -> None:
        """Persist verification suite report."""

    async def get_baseline_comparison(self, comparison_id: str) -> BaselineComparison | None:
        """Fetch baseline comparison by ID."""

    async def list_baseline_comparisons(
        self, candidate_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[BaselineComparison]:
        """List baseline comparisons."""

    async def save_baseline_comparison(self, comparison: BaselineComparison) -> None:
        """Persist baseline comparison record."""


@runtime_checkable
class TransactionScope(Protocol):
    """Transaction boundary with outbox support for Quality."""

    @property
    def store(self) -> QualityStore:
        """Access the scoped quality store."""

    def record_event(self, envelope: EventEnvelope) -> None:
        """Queue an outbox event to be atomically committed."""

    async def commit(self) -> None:
        """Commit store mutations and recorded outbox events."""

    async def rollback(self) -> None:
        """Rollback uncommitted mutations."""

    async def __aenter__(self) -> Self:
        """Enter transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool | None:
        """Exit transaction scope."""
