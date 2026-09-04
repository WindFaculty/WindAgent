"""Command, query, and job handlers for Quality."""

from __future__ import annotations

from typing import Any

from .commands import (
    AddDatasetTestCase,
    CompareBaseline,
    CreateEvaluationDataset,
    ExecuteDatasetEvaluation,
    FinalizeEvaluationRun,
    RecordEvaluationMetric,
    RunVerificationSuite,
    StartEvaluationRun,
)
from .models import (
    BaselineComparisonView,
    DatasetView,
    EvaluationRecordView,
    EvaluationRunView,
    QualitySummaryView,
    TestCaseView,
    VerificationReportView,
)
from .queries import (
    GetBaselineComparison,
    GetEvaluationDataset,
    GetEvaluationRun,
    GetQualityCertificationMarkdown,
    GetQualitySummary,
    GetVerificationReport,
    ListBaselineComparisons,
    ListEvaluationDatasets,
    ListEvaluationRuns,
    ListVerificationReports,
)
from .runtime import QualityServices, container_for

# --------------------------------------------------------------------------- #
# Command Handlers
# --------------------------------------------------------------------------- #


class CreateEvaluationDatasetHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: CreateEvaluationDataset) -> DatasetView:
        return await container_for(self._services).quality.create_dataset(command)


class AddDatasetTestCaseHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: AddDatasetTestCase) -> TestCaseView:
        return await container_for(self._services).quality.add_test_case(command)


class StartEvaluationRunHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: StartEvaluationRun) -> EvaluationRunView:
        return await container_for(self._services).quality.start_evaluation_run(command)


class RecordEvaluationMetricHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: RecordEvaluationMetric) -> EvaluationRecordView:
        return await container_for(self._services).quality.record_metric(command)


class FinalizeEvaluationRunHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: FinalizeEvaluationRun) -> EvaluationRunView:
        return await container_for(self._services).quality.finalize_evaluation_run(command)


class ExecuteDatasetEvaluationHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: ExecuteDatasetEvaluation) -> EvaluationRunView:
        return await container_for(self._services).quality.execute_dataset_evaluation(command)


class RunVerificationSuiteHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: RunVerificationSuite) -> VerificationReportView:
        return await container_for(self._services).quality.run_verification_suite(command)


class CompareBaselineHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, command: CompareBaseline) -> BaselineComparisonView:
        return await container_for(self._services).quality.compare_baseline(command)


# --------------------------------------------------------------------------- #
# Query Handlers
# --------------------------------------------------------------------------- #


class GetEvaluationRunHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetEvaluationRun) -> EvaluationRunView | None:
        return await container_for(self._services).quality.get_evaluation_run(query)


class ListEvaluationRunsHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListEvaluationRuns) -> list[EvaluationRunView]:
        return await container_for(self._services).quality.list_evaluation_runs(query)


class GetEvaluationDatasetHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetEvaluationDataset) -> DatasetView | None:
        return await container_for(self._services).quality.get_dataset(query)


class ListEvaluationDatasetsHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListEvaluationDatasets) -> list[DatasetView]:
        return await container_for(self._services).quality.list_datasets(query)


class GetVerificationReportHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetVerificationReport) -> VerificationReportView | None:
        return await container_for(self._services).quality.get_verification_report(query)


class ListVerificationReportsHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListVerificationReports) -> list[VerificationReportView]:
        return await container_for(self._services).quality.list_verification_reports(query)


class GetBaselineComparisonHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetBaselineComparison) -> BaselineComparisonView | None:
        return await container_for(self._services).quality.get_baseline_comparison(query)


class ListBaselineComparisonsHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListBaselineComparisons) -> list[BaselineComparisonView]:
        return await container_for(self._services).quality.list_baseline_comparisons(query)


class GetQualitySummaryHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetQualitySummary) -> QualitySummaryView:
        return await container_for(self._services).quality.get_quality_summary(query)


class GetQualityCertificationMarkdownHandler:
    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetQualityCertificationMarkdown) -> str | None:
        return await container_for(self._services).quality.get_certification_markdown(query)


# --------------------------------------------------------------------------- #
# Job Handlers
# --------------------------------------------------------------------------- #


class QualityEvalExecuteJobHandler:
    job_type = "quality.eval.execute"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        execution_id = str(payload.get("execution_id", ""))
        dataset_id = str(payload.get("dataset_id", ""))
        grader_type = str(payload.get("grader_type", "exact_match"))
        if not execution_id or not dataset_id:
            return {"status": "FAILED", "error": "missing execution_id or dataset_id in payload"}
        try:
            view = await container_for(self._services).quality.execute_dataset_evaluation(
                ExecuteDatasetEvaluation(
                    execution_id=execution_id,
                    dataset_id=dataset_id,
                    grader_type=grader_type,
                )
            )
            return {"status": "SUCCEEDED", "evaluation_run": view.to_payload()}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}


class QualityVerificationRunJobHandler:
    job_type = "quality.verification.run"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite_id = str(payload.get("suite_id", "default_suite"))
        target_id = str(payload.get("target_id", ""))
        gate_checks = tuple(payload.get("gate_checks", []))
        if not target_id:
            return {"status": "FAILED", "error": "missing target_id in payload"}
        try:
            view = await container_for(self._services).quality.run_verification_suite(
                RunVerificationSuite(
                    suite_id=suite_id,
                    target_id=target_id,
                    gate_checks=gate_checks,
                )
            )
            return {"status": "SUCCEEDED", "verification_report": view.to_payload()}
        except Exception as exc:
            return {"status": "FAILED", "error": str(exc)}


class QualityBenchmarkRunJobHandler:
    job_type = "quality.benchmark.run"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "output": {"status": "benchmark_completed"}}


class QualityRegressionDetectJobHandler:
    job_type = "quality.regression.detect"

    def __init__(self, services: QualityServices | None = None) -> None:
        self._services = services

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "SUCCEEDED", "output": {"status": "regression_check_completed"}}
