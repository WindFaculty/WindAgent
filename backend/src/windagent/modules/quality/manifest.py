"""Module manifest for the Quality bounded context."""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_quality_router
from .application.commands import (
    AddDatasetTestCase,
    CompareBaseline,
    CreateEvaluationDataset,
    ExecuteDatasetEvaluation,
    FinalizeEvaluationRun,
    RecordEvaluationMetric,
    RunVerificationSuite,
    StartEvaluationRun,
)
from .application.handlers import (
    AddDatasetTestCaseHandler,
    CompareBaselineHandler,
    CreateEvaluationDatasetHandler,
    ExecuteDatasetEvaluationHandler,
    FinalizeEvaluationRunHandler,
    GetBaselineComparisonHandler,
    GetEvaluationDatasetHandler,
    GetEvaluationRunHandler,
    GetQualityCertificationMarkdownHandler,
    GetQualitySummaryHandler,
    GetVerificationReportHandler,
    ListBaselineComparisonsHandler,
    ListEvaluationDatasetsHandler,
    ListEvaluationRunsHandler,
    ListVerificationReportsHandler,
    QualityBenchmarkRunJobHandler,
    QualityEvalExecuteJobHandler,
    QualityRegressionDetectJobHandler,
    QualityVerificationRunJobHandler,
    RecordEvaluationMetricHandler,
    RunVerificationSuiteHandler,
    StartEvaluationRunHandler,
)
from .application.queries import (
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
from .application.runtime import QualityServices


def build_quality_manifest(services: QualityServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(CreateEvaluationDataset, CreateEvaluationDatasetHandler(services)),
            CommandRegistration(AddDatasetTestCase, AddDatasetTestCaseHandler(services)),
            CommandRegistration(StartEvaluationRun, StartEvaluationRunHandler(services)),
            CommandRegistration(RecordEvaluationMetric, RecordEvaluationMetricHandler(services)),
            CommandRegistration(FinalizeEvaluationRun, FinalizeEvaluationRunHandler(services)),
            CommandRegistration(ExecuteDatasetEvaluation, ExecuteDatasetEvaluationHandler(services)),
            CommandRegistration(RunVerificationSuite, RunVerificationSuiteHandler(services)),
            CommandRegistration(CompareBaseline, CompareBaselineHandler(services)),
        ),
        queries=(
            QueryRegistration(GetEvaluationRun, GetEvaluationRunHandler(services)),
            QueryRegistration(ListEvaluationRuns, ListEvaluationRunsHandler(services)),
            QueryRegistration(GetEvaluationDataset, GetEvaluationDatasetHandler(services)),
            QueryRegistration(ListEvaluationDatasets, ListEvaluationDatasetsHandler(services)),
            QueryRegistration(GetVerificationReport, GetVerificationReportHandler(services)),
            QueryRegistration(ListVerificationReports, ListVerificationReportsHandler(services)),
            QueryRegistration(GetBaselineComparison, GetBaselineComparisonHandler(services)),
            QueryRegistration(ListBaselineComparisons, ListBaselineComparisonsHandler(services)),
            QueryRegistration(GetQualitySummary, GetQualitySummaryHandler(services)),
            QueryRegistration(GetQualityCertificationMarkdown, GetQualityCertificationMarkdownHandler(services)),
        ),
        jobs=(
            JobRegistration("quality.eval.execute", QualityEvalExecuteJobHandler(services)),
            JobRegistration("quality.verification.run", QualityVerificationRunJobHandler(services)),
            JobRegistration("quality.benchmark.run", QualityBenchmarkRunJobHandler(services)),
            JobRegistration("quality.regression.detect", QualityRegressionDetectJobHandler(services)),
        ),
        routers=(create_quality_router(),),
        capabilities=(
            "quality",
            "evals",
            "verification",
            "graders",
            "regression",
            "benchmarks",
            "quality_gates",
            "certification",
        ),
    )


manifest = build_quality_manifest()
