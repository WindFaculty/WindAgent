"""HTTP REST routes for the Quality module (mounted under /api/v4/quality)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from windagent.platform.commands import CommandBus
from windagent.platform.queries import QueryBus

from ..application.commands import (
    AddDatasetTestCase,
    CompareBaseline,
    CreateEvaluationDataset,
    ExecuteDatasetEvaluation,
    FinalizeEvaluationRun,
    RecordEvaluationMetric,
    RunVerificationSuite,
    StartEvaluationRun,
)
from ..application.queries import (
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
from ..application.runtime import QualityServices, bind_services
from ..domain.errors import (
    DatasetNotFoundError,
    QualityError,
    QualityEvaluationNotFoundError,
    QualityGateBlockedError,
    QualityStaleVersionError,
    RegressionDetectedError,
    VerificationSuiteFailedError,
)

MODULE_ID = "quality"
MODULE_VERSION = "1.0.0"
QUALITY_PREFIX = "/quality"


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #


async def _runtime_services(request: Request) -> AsyncIterator[Any]:
    override = getattr(request.app.state, "quality_services_override", None)
    if override is not None:
        with bind_services(override):
            yield override
        return

    db = getattr(request.app.state, "database", None)
    if db is None:
        from ..infrastructure.memory import create_in_memory_scope_factory

        _, scope_factory = create_in_memory_scope_factory()
        services = QualityServices(transaction_factory=scope_factory)
    else:
        from ..infrastructure.repository import sql_scope_factory

        services = QualityServices(transaction_factory=sql_scope_factory(db))

    with bind_services(services):
        yield services



# --------------------------------------------------------------------------- #
# Request DTOs
# --------------------------------------------------------------------------- #


class CreateDatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=100)
    dataset_id: str | None = Field(default=None, max_length=36)
    description: str = Field(default="", max_length=2000)
    version: str = Field(default="1.0.0", max_length=50)
    metadata: dict[str, Any] | None = None


class AddTestCaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    dimension: str = Field(default="task_success")
    case_id: str | None = Field(default=None, max_length=36)
    tags: list[str] = Field(default_factory=list)
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class StartEvaluationRunIn(BaseModel):
    execution_id: str = Field(min_length=1, max_length=100)
    dataset_id: str | None = Field(default=None, max_length=36)
    evaluator_version: str = Field(default="2.0.0", max_length=50)
    run_id: str | None = Field(default=None, max_length=36)
    metadata: dict[str, Any] | None = None


class RecordMetricIn(BaseModel):
    dimension: str = Field(min_length=1, max_length=50)
    metric_name: str = Field(min_length=1, max_length=100)
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    details: dict[str, Any] | None = None
    blocked: bool = False
    evaluation_id: str | None = None


class ExecuteDatasetEvaluationIn(BaseModel):
    execution_id: str = Field(min_length=1, max_length=100)
    dataset_id: str = Field(min_length=1, max_length=36)
    grader_type: str = Field(default="exact_match")
    evaluator_version: str = Field(default="2.0.0")


class RunVerificationSuiteIn(BaseModel):
    suite_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    gate_checks: list[dict[str, Any]] = Field(default_factory=list)


class CompareBaselineIn(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    baseline_id: str = Field(min_length=1, max_length=100)
    candidate_metrics: dict[str, tuple[str, float]]
    baseline_metrics: dict[str, tuple[str, float]]
    regression_threshold: float = Field(default=0.05, ge=0.0)
    min_composite_pass_score: float = Field(default=0.7, ge=0.0, le=1.0)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_buses(request: Request) -> tuple[CommandBus, QueryBus]:
    cmd_bus = getattr(request.app.state, "command_bus", None)
    query_bus = getattr(request.app.state, "query_bus", None)
    if cmd_bus is None or query_bus is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CommandBus or QueryBus not available on app state",
        )
    return cmd_bus, query_bus


def _handle_domain_error(exc: Exception) -> None:
    if isinstance(exc, (QualityEvaluationNotFoundError, DatasetNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, QualityStaleVersionError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, RegressionDetectedError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if isinstance(exc, (QualityGateBlockedError, VerificationSuiteFailedError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, QualityError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


# --------------------------------------------------------------------------- #
# Router factory
# --------------------------------------------------------------------------- #


def create_quality_router() -> APIRouter:
    router = APIRouter(
        prefix=QUALITY_PREFIX,
        tags=["quality"],
        dependencies=[Depends(_runtime_services)],
    )

    # Datasets
    @router.post("/datasets", status_code=status.HTTP_201_CREATED)
    async def create_dataset(body: CreateDatasetIn, request: Request) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = CreateEvaluationDataset(
            name=body.name,
            domain=body.domain,
            dataset_id=body.dataset_id,
            description=body.description,
            version=body.version,
            metadata=body.metadata,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/datasets")
    async def list_datasets(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        views = await query_bus.ask(ListEvaluationDatasets(limit=limit, offset=offset))
        return [v.to_payload() for v in views]

    @router.get("/datasets/{dataset_id}")
    async def get_dataset(dataset_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        view = await query_bus.ask(GetEvaluationDataset(dataset_id=dataset_id))
        if view is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset not found: {dataset_id}"
            )
        return view.to_payload()

    @router.post("/datasets/{dataset_id}/cases", status_code=status.HTTP_201_CREATED)
    async def add_test_case(
        dataset_id: str, body: AddTestCaseIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = AddDatasetTestCase(
            dataset_id=dataset_id,
            name=body.name,
            input_payload=body.input_payload,
            expected_output=body.expected_output,
            dimension=body.dimension,
            case_id=body.case_id,
            tags=tuple(body.tags),
            criteria=tuple(body.criteria),
            metadata=body.metadata,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    # Evaluation Runs
    @router.post("/evaluations/runs", status_code=status.HTTP_201_CREATED)
    async def start_evaluation_run(
        body: StartEvaluationRunIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = StartEvaluationRun(
            execution_id=body.execution_id,
            dataset_id=body.dataset_id,
            evaluator_version=body.evaluator_version,
            run_id=body.run_id,
            metadata=body.metadata,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/evaluations/runs")
    async def list_evaluation_runs(
        request: Request,
        execution_id: str | None = Query(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        views = await query_bus.ask(
            ListEvaluationRuns(
                execution_id=execution_id,
                status=status_filter,
                limit=limit,
                offset=offset,
            )
        )
        return [v.to_payload() for v in views]

    @router.get("/evaluations/runs/{run_id}")
    async def get_evaluation_run(run_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        view = await query_bus.ask(GetEvaluationRun(run_id=run_id))
        if view is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Evaluation run not found: {run_id}"
            )
        return view.to_payload()

    @router.post("/evaluations/runs/{run_id}/metrics", status_code=status.HTTP_201_CREATED)
    async def record_metric(
        run_id: str, body: RecordMetricIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = RecordEvaluationMetric(
            run_id=run_id,
            dimension=body.dimension,
            metric_name=body.metric_name,
            score=body.score,
            threshold=body.threshold,
            confidence=body.confidence,
            evidence_refs=tuple(body.evidence_refs),
            details=body.details,
            blocked=body.blocked,
            evaluation_id=body.evaluation_id,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/evaluations/runs/{run_id}/finalize")
    async def finalize_evaluation_run(run_id: str, request: Request) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        try:
            view = await cmd_bus.dispatch(FinalizeEvaluationRun(run_id=run_id))
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.post("/evaluations/execute-dataset")
    async def execute_dataset_evaluation(
        body: ExecuteDatasetEvaluationIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = ExecuteDatasetEvaluation(
            execution_id=body.execution_id,
            dataset_id=body.dataset_id,
            grader_type=body.grader_type,
            evaluator_version=body.evaluator_version,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    # Verification Suites
    @router.post("/verification/suites/run", status_code=status.HTTP_201_CREATED)
    async def run_verification_suite(
        body: RunVerificationSuiteIn, request: Request
    ) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = RunVerificationSuite(
            suite_id=body.suite_id,
            target_id=body.target_id,
            gate_checks=tuple(body.gate_checks),
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/verification/reports")
    async def list_verification_reports(
        request: Request,
        target_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        views = await query_bus.ask(
            ListVerificationReports(target_id=target_id, limit=limit, offset=offset)
        )
        return [v.to_payload() for v in views]

    @router.get("/verification/reports/{report_id}")
    async def get_verification_report(report_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        view = await query_bus.ask(GetVerificationReport(report_id=report_id))
        if view is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Verification report not found: {report_id}",
            )
        return view.to_payload()

    # Baseline Comparisons
    @router.post("/baselines/compare", status_code=status.HTTP_201_CREATED)
    async def compare_baseline(body: CompareBaselineIn, request: Request) -> dict[str, Any]:
        cmd_bus, _ = _get_buses(request)
        cmd = CompareBaseline(
            candidate_id=body.candidate_id,
            baseline_id=body.baseline_id,
            candidate_metrics=body.candidate_metrics,
            baseline_metrics=body.baseline_metrics,
            regression_threshold=body.regression_threshold,
            min_composite_pass_score=body.min_composite_pass_score,
        )
        try:
            view = await cmd_bus.dispatch(cmd)
            return view.to_payload()
        except Exception as exc:
            _handle_domain_error(exc)
            raise

    @router.get("/baselines/comparisons")
    async def list_baseline_comparisons(
        request: Request,
        candidate_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        _, query_bus = _get_buses(request)
        views = await query_bus.ask(
            ListBaselineComparisons(candidate_id=candidate_id, limit=limit, offset=offset)
        )
        return [v.to_payload() for v in views]

    @router.get("/baselines/comparisons/{comparison_id}")
    async def get_baseline_comparison(comparison_id: str, request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        view = await query_bus.ask(GetBaselineComparison(comparison_id=comparison_id))
        if view is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Baseline comparison not found: {comparison_id}",
            )
        return view.to_payload()

    # Summary & Certificates
    @router.get("/summary")
    async def get_quality_summary(request: Request) -> dict[str, Any]:
        _, query_bus = _get_buses(request)
        view = await query_bus.ask(GetQualitySummary())
        return view.to_payload()

    @router.get("/evaluations/runs/{run_id}/certificate")
    async def get_certification_markdown(run_id: str, request: Request) -> dict[str, str]:
        _, query_bus = _get_buses(request)
        markdown = await query_bus.ask(GetQualityCertificationMarkdown(run_id=run_id))
        if markdown is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation run not found: {run_id}",
            )
        return {"markdown": markdown}

    return router


CreateDatasetIn.model_rebuild()
AddTestCaseIn.model_rebuild()
StartEvaluationRunIn.model_rebuild()
RecordMetricIn.model_rebuild()
ExecuteDatasetEvaluationIn.model_rebuild()
RunVerificationSuiteIn.model_rebuild()
CompareBaselineIn.model_rebuild()

