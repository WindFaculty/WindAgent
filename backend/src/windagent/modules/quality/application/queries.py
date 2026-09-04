"""Query definitions for the Quality bounded context."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

from .models import (
    BaselineComparisonView,
    DatasetView,
    EvaluationRunView,
    QualitySummaryView,
    VerificationReportView,
)


@dataclass(frozen=True, slots=True)
class GetEvaluationRun(Query[EvaluationRunView | None]):
    """Fetch an evaluation run with its records."""

    run_id: str


@dataclass(frozen=True, slots=True)
class ListEvaluationRuns(Query[list[EvaluationRunView]]):
    """List evaluation runs with optional execution and status filtering."""

    execution_id: str | None = None
    status: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetEvaluationDataset(Query[DatasetView | None]):
    """Fetch benchmark dataset by ID."""

    dataset_id: str


@dataclass(frozen=True, slots=True)
class ListEvaluationDatasets(Query[list[DatasetView]]):
    """List all evaluation benchmark datasets."""

    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetVerificationReport(Query[VerificationReportView | None]):
    """Fetch verification suite report by ID."""

    report_id: str


@dataclass(frozen=True, slots=True)
class ListVerificationReports(Query[list[VerificationReportView]]):
    """List verification reports with optional target filter."""

    target_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetBaselineComparison(Query[BaselineComparisonView | None]):
    """Fetch baseline comparison by ID."""

    comparison_id: str


@dataclass(frozen=True, slots=True)
class ListBaselineComparisons(Query[list[BaselineComparisonView]]):
    """List baseline comparisons."""

    candidate_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetQualitySummary(Query[QualitySummaryView]):
    """Fetch high-level aggregate quality metrics summary."""


@dataclass(frozen=True, slots=True)
class GetQualityCertificationMarkdown(Query[str | None]):
    """Generate markdown certification report for an evaluation run."""

    run_id: str
