"""Unit tests for Quality application services and CQRS workflows."""

import pytest
from windagent.modules.quality.application.commands import (
    AddDatasetTestCase,
    CompareBaseline,
    CreateEvaluationDataset,
    ExecuteDatasetEvaluation,
    FinalizeEvaluationRun,
    RecordEvaluationMetric,
    RunVerificationSuite,
    StartEvaluationRun,
)
from windagent.modules.quality.application.queries import (
    GetBaselineComparison,
    GetEvaluationDataset,
    GetQualitySummary,
    GetVerificationReport,
    ListEvaluationDatasets,
)
from windagent.modules.quality.application.services import QualityService
from windagent.modules.quality.infrastructure.memory import (
    InMemoryQualityStore,
    InMemoryTransactionScope,
)


@pytest.fixture
def quality_service() -> tuple[QualityService, InMemoryQualityStore]:
    store = InMemoryQualityStore()

    def _factory() -> InMemoryTransactionScope:
        return InMemoryTransactionScope(store)

    svc = QualityService(transaction_factory=_factory)
    return svc, store


@pytest.mark.asyncio
async def test_dataset_and_test_case_management(
    quality_service: tuple[QualityService, InMemoryQualityStore],
) -> None:
    svc, store = quality_service

    # Create dataset
    ds = await svc.create_dataset(
        CreateEvaluationDataset(
            name="Screenplay QA Benchmark",
            domain="studio_story",
            description="Benchmark for story generation quality",
            version="1.0.0",
        )
    )
    assert ds.name == "Screenplay QA Benchmark"
    assert ds.domain == "studio_story"

    # Add test case
    tc = await svc.add_test_case(
        AddDatasetTestCase(
            dataset_id=ds.dataset_id,
            name="logline_generation_case",
            input_payload={"prompt": "Sci-fi time travel story", "output": "Logline generated"},
            expected_output={"output": "Logline generated"},
            dimension="task_success",
            tags=("sci-fi", "logline"),
        )
    )
    assert tc.name == "logline_generation_case"
    assert tc.dimension == "task_success"

    # Get dataset
    fetched = await svc.get_dataset(GetEvaluationDataset(dataset_id=ds.dataset_id))
    assert fetched is not None
    assert len(fetched.test_cases) == 1

    # List datasets
    all_ds = await svc.list_datasets(ListEvaluationDatasets())
    assert len(all_ds) == 1


@pytest.mark.asyncio
async def test_evaluation_run_execution_flow(
    quality_service: tuple[QualityService, InMemoryQualityStore],
) -> None:
    svc, store = quality_service

    # Start run
    run = await svc.start_evaluation_run(
        StartEvaluationRun(
            execution_id="run_12345",
            evaluator_version="2.0.0",
        )
    )
    assert run.execution_id == "run_12345"
    assert run.status == "RUNNING"

    # Record metric with evidence
    rec = await svc.record_metric(
        RecordEvaluationMetric(
            run_id=run.run_id,
            dimension="task_success",
            metric_name="completion_rate",
            score=0.95,
            evidence_refs=("artifact://output/res.json",),
        )
    )
    assert rec.passed is True
    assert rec.blocked is False

    # Record metric without evidence (fail-closed)
    rec_blocked = await svc.record_metric(
        RecordEvaluationMetric(
            run_id=run.run_id,
            dimension="safety",
            metric_name="policy_check",
            score=1.0,
            evidence_refs=(),  # No evidence
        )
    )
    assert rec_blocked.blocked is True
    assert rec_blocked.passed is False

    # Finalize
    final = await svc.finalize_evaluation_run(FinalizeEvaluationRun(run_id=run.run_id))
    assert final.status == "BLOCKED"  # Blocked due to fail-closed metric
    assert final.passed is False


@pytest.mark.asyncio
async def test_automated_dataset_evaluation(
    quality_service: tuple[QualityService, InMemoryQualityStore],
) -> None:
    svc, store = quality_service

    ds = await svc.create_dataset(
        CreateEvaluationDataset(
            name="Exact Match Benchmark",
            domain="tools",
        )
    )
    await svc.add_test_case(
        AddDatasetTestCase(
            dataset_id=ds.dataset_id,
            name="case_1",
            input_payload={"output": "MATCH_VALUE"},
            expected_output={"output": "MATCH_VALUE"},
        )
    )

    run_view = await svc.execute_dataset_evaluation(
        ExecuteDatasetEvaluation(
            execution_id="exec_auto_1",
            dataset_id=ds.dataset_id,
            grader_type="exact_match",
        )
    )
    assert run_view.status == "COMPLETED"
    assert run_view.passed is True
    assert run_view.composite_score == 1.0


@pytest.mark.asyncio
async def test_verification_suite_service(
    quality_service: tuple[QualityService, InMemoryQualityStore],
) -> None:
    svc, store = quality_service

    checks = (
        {
            "gate_name": "pytest_unit",
            "gate_type": "TEST_RUNNER",
            "command": "pytest tests/unit",
            "exit_code": 0,
            "stdout": "100 passed",
            "blocking": True,
        },
        {
            "gate_name": "ruff_linter",
            "gate_type": "LINTER_STYLE",
            "command": "ruff check",
            "exit_code": 0,
            "stdout": "All checks passed",
            "blocking": True,
        },
    )

    report = await svc.run_verification_suite(
        RunVerificationSuite(
            suite_id="ci_gate_v1",
            target_id="commit_abc123",
            gate_checks=checks,
        )
    )
    assert report.overall_status == "PASSED"
    assert len(report.passed_gates) == 2

    # Get report
    fetched = await svc.get_verification_report(
        GetVerificationReport(report_id=report.report_id)
    )
    assert fetched is not None
    assert fetched.report_id == report.report_id


@pytest.mark.asyncio
async def test_baseline_comparison_service(
    quality_service: tuple[QualityService, InMemoryQualityStore],
) -> None:
    svc, store = quality_service

    cand = {"task_success": ("task_success", 0.95), "cost": ("cost", 0.80)}
    base = {"task_success": ("task_success", 0.90), "cost": ("cost", 0.85)}

    comp = await svc.compare_baseline(
        CompareBaseline(
            candidate_id="model_candidate",
            baseline_id="model_baseline",
            candidate_metrics=cand,
            baseline_metrics=base,
            regression_threshold=0.10,
        )
    )

    assert comp.candidate_id == "model_candidate"
    assert comp.passed is True
    assert comp.regression_detected is False

    # Get comparison
    fetched = await svc.get_baseline_comparison(
        GetBaselineComparison(comparison_id=comp.comparison_id)
    )
    assert fetched is not None
    assert fetched.comparison_id == comp.comparison_id

    # Summary
    summary = await svc.get_quality_summary(GetQualitySummary())
    assert summary.total_evaluations >= 0
