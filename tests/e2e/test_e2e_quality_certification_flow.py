"""E2E Test: Quality Benchmark dataset creation, rubric evaluation, and certification export."""

from __future__ import annotations

import pytest
from windagent.modules.quality.application.commands import (
    AddDatasetTestCase,
    CreateEvaluationDataset,
    FinalizeEvaluationRun,
    RecordEvaluationMetric,
    StartEvaluationRun,
)
from windagent.modules.quality.application.services import QualityService
from windagent.modules.quality.infrastructure.memory import (
    InMemoryQualityStore,
    InMemoryTransactionScope,
)


@pytest.mark.asyncio
async def test_e2e_quality_certification_generation() -> None:
    store = InMemoryQualityStore()

    def _factory() -> InMemoryTransactionScope:
        return InMemoryTransactionScope(store)

    svc = QualityService(transaction_factory=_factory)

    # 1. Create Benchmark Dataset
    ds_view = await svc.create_dataset(
        CreateEvaluationDataset(
            name="Milestone 4 Golden Certification Benchmark",
            domain="Correctness & Safety",
            description="Certifies all 9 modules and contract invariants",
        )
    )
    assert ds_view.dataset_id is not None
    assert ds_view.name == "Milestone 4 Golden Certification Benchmark"

    # 2. Add Test Cases
    tc_view = await svc.add_test_case(
        AddDatasetTestCase(
            dataset_id=ds_view.dataset_id,
            name="Architecture Boundary Compliance",
            input_payload={"prompt": "verify_no_cross_module_orm_leaks"},
            expected_output={"status": "PASS"},
        )
    )
    assert tc_view.case_id is not None
    assert tc_view.dataset_id == ds_view.dataset_id

    # 3. Start Evaluation Run & Record Metrics
    run_view = await svc.start_evaluation_run(
        StartEvaluationRun(
            execution_id="exec-e2e-1",
            dataset_id=ds_view.dataset_id,
            evaluator_version="2.0.0",
        )
    )
    assert run_view.run_id is not None
    assert run_view.status == "RUNNING"

    metric_view = await svc.record_metric(
        RecordEvaluationMetric(
            run_id=run_view.run_id,
            dimension="correctness",
            metric_name="contract_verification",
            score=1.0,
            threshold=0.8,
            confidence=1.0,
            evidence_refs=("evidence://m4/cert_run_001.json",),
        )
    )
    assert metric_view.passed is True

    # 4. Finalize Evaluation Run
    final_view = await svc.finalize_evaluation_run(
        FinalizeEvaluationRun(
            run_id=run_view.run_id,
        )
    )
    assert final_view.status == "COMPLETED"
    assert final_view.passed is True
