"""In-memory quality store and transaction scope for testing."""

from __future__ import annotations

import copy

from windagent.kernel.events import EventEnvelope

from ..application.ports import QualityStore, TransactionScope
from ..domain.errors import QualityStaleVersionError
from ..domain.evals import (
    EvaluationDataset,
    EvaluationRunAggregate,
)
from ..domain.regression import BaselineComparison
from ..domain.verification import VerificationSuiteReport


class InMemoryQualityStore(QualityStore):
    """In-memory implementation of QualityStore."""

    def __init__(
        self,
        runs: dict[str, EvaluationRunAggregate] | None = None,
        datasets: dict[str, EvaluationDataset] | None = None,
        reports: dict[str, VerificationSuiteReport] | None = None,
        comparisons: dict[str, BaselineComparison] | None = None,
    ) -> None:
        self._runs: dict[str, EvaluationRunAggregate] = runs if runs is not None else {}
        self._datasets: dict[str, EvaluationDataset] = datasets if datasets is not None else {}
        self._reports: dict[str, VerificationSuiteReport] = reports if reports is not None else {}
        self._comparisons: dict[str, BaselineComparison] = comparisons if comparisons is not None else {}

    async def get_evaluation_run(self, run_id: str) -> EvaluationRunAggregate | None:
        agg = self._runs.get(run_id)
        return copy.deepcopy(agg) if agg else None

    async def list_evaluation_runs(
        self,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvaluationRunAggregate]:
        res: list[EvaluationRunAggregate] = []
        for agg in self._runs.values():
            if execution_id and agg.execution_id != execution_id:
                continue
            if status and agg.status.value != status:
                continue
            res.append(copy.deepcopy(agg))
        return res[offset : offset + limit]

    async def save_evaluation_run(
        self, aggregate: EvaluationRunAggregate, expected_version: int | None = None
    ) -> None:
        run_id = str(aggregate.id)
        existing = self._runs.get(run_id)
        if existing and expected_version is not None:
            if existing.optimistic_version != expected_version:
                raise QualityStaleVersionError(run_id, expected_version, existing.optimistic_version)
        self._runs[run_id] = copy.deepcopy(aggregate)

    async def get_dataset(self, dataset_id: str) -> EvaluationDataset | None:
        ds = self._datasets.get(dataset_id)
        return copy.deepcopy(ds) if ds else None

    async def list_datasets(self, limit: int = 50, offset: int = 0) -> list[EvaluationDataset]:
        res = [copy.deepcopy(d) for d in self._datasets.values()]
        return res[offset : offset + limit]

    async def save_dataset(self, dataset: EvaluationDataset) -> None:
        self._datasets[dataset.dataset_id] = copy.deepcopy(dataset)

    async def get_verification_report(self, report_id: str) -> VerificationSuiteReport | None:
        rep = self._reports.get(report_id)
        return copy.deepcopy(rep) if rep else None

    async def list_verification_reports(
        self, target_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[VerificationSuiteReport]:
        res: list[VerificationSuiteReport] = []
        for rep in self._reports.values():
            if target_id and rep.target_id != target_id:
                continue
            res.append(copy.deepcopy(rep))
        return res[offset : offset + limit]

    async def save_verification_report(self, report: VerificationSuiteReport) -> None:
        self._reports[report.report_id] = copy.deepcopy(report)

    async def get_baseline_comparison(self, comparison_id: str) -> BaselineComparison | None:
        comp = self._comparisons.get(comparison_id)
        return copy.deepcopy(comp) if comp else None

    async def list_baseline_comparisons(
        self, candidate_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[BaselineComparison]:
        res: list[BaselineComparison] = []
        for comp in self._comparisons.values():
            if candidate_id and comp.candidate_id != candidate_id:
                continue
            res.append(copy.deepcopy(comp))
        return res[offset : offset + limit]

    async def save_baseline_comparison(self, comparison: BaselineComparison) -> None:
        self._comparisons[comparison.comparison_id] = copy.deepcopy(comparison)


class InMemoryTransactionScope(TransactionScope):
    """In-memory transaction scope recording outbox events."""

    def __init__(self, store: InMemoryQualityStore) -> None:
        self._store = store
        self._events: list[EventEnvelope] = []
        self._committed = False

    @property
    def store(self) -> QualityStore:
        return self._store

    @property
    def recorded_events(self) -> list[EventEnvelope]:
        return list(self._events)

    def record_event(self, envelope: EventEnvelope) -> None:
        self._events.append(envelope)

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        self._events.clear()

    async def __aenter__(self) -> InMemoryTransactionScope:
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            await self.rollback()


def create_in_memory_scope_factory(
    initial_runs: dict[str, EvaluationRunAggregate] | None = None,
    initial_datasets: dict[str, EvaluationDataset] | None = None,
) -> tuple[InMemoryQualityStore, type[TransactionScope]]:
    store = InMemoryQualityStore(runs=initial_runs, datasets=initial_datasets)

    def _factory() -> TransactionScope:
        return InMemoryTransactionScope(store)

    return store, _factory  # type: ignore[return-value]
