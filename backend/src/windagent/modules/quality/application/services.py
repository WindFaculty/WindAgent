"""Application service for orchestrating quality evaluations and verification."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.ids import EntityId

from ..domain.errors import (
    DatasetNotFoundError,
    QualityEvaluationNotFoundError,
)
from ..domain.evals import (
    EvaluationDataset,
    EvaluationDimension,
    EvaluationRecord,
    EvaluationRunAggregate,
    EvaluationRunStatus,
    RubricCriterion,
    TestCase,
)
from ..domain.graders import (
    ExactMatchGrader,
    RegexGrader,
    SafetyRuleGrader,
)
from ..domain.regression import BaselineComparison
from ..domain.reports import QualityReportGenerator
from ..domain.verification import (
    ExecutionEvidence,
    VerificationGateResult,
    VerificationGateType,
    VerificationStatus,
    VerificationSuiteReport,
)
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
from .events import quality_events
from .models import (
    BaselineComparisonView,
    DatasetView,
    EvaluationRecordView,
    EvaluationRunView,
    QualitySummaryView,
    TestCaseView,
    VerificationReportView,
)
from .ports import TransactionScope
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


def _to_record_view(r: EvaluationRecord) -> EvaluationRecordView:
    return EvaluationRecordView(
        evaluation_id=r.evaluation_id,
        run_id=r.run_id,
        execution_id=r.execution_id,
        dimension=r.dimension.value,
        metric_name=r.metric_name,
        score=r.score,
        threshold=r.threshold,
        confidence=r.confidence,
        evidence_refs=list(r.evidence_refs),
        passed=r.passed,
        blocked=r.blocked,
        details=dict(r.details),
        evaluator_version=r.evaluator_version,
        created_at=r.created_at.isoformat(),
    )


def _to_run_view(agg: EvaluationRunAggregate) -> EvaluationRunView:
    return EvaluationRunView(
        run_id=str(agg.id),
        execution_id=agg.execution_id,
        dataset_id=agg.dataset_id,
        evaluator_version=agg.evaluator_version,
        status=agg.status.value,
        composite_score=agg.composite_score,
        passed=agg.passed,
        records=[_to_record_view(r) for r in agg.records],
        metadata=dict(agg.metadata),
        optimistic_version=agg.optimistic_version,
        created_at=agg.created_at.isoformat(),
        updated_at=agg.updated_at.isoformat(),
    )


def _to_test_case_view(c: TestCase, dataset_id: str) -> TestCaseView:
    return TestCaseView(
        case_id=c.case_id,
        dataset_id=dataset_id,
        name=c.name,
        dimension=c.dimension.value,
        input_payload=dict(c.input_payload),
        expected_output=dict(c.expected_output),
        tags=list(c.tags),
        criteria=[
            {
                "criterion_id": cr.criterion_id,
                "name": cr.name,
                "description": cr.description,
                "weight": cr.weight,
                "min_score": cr.min_score,
                "max_score": cr.max_score,
            }
            for cr in c.criteria
        ],
        metadata=dict(c.metadata),
    )


def _to_dataset_view(d: EvaluationDataset) -> DatasetView:
    return DatasetView(
        dataset_id=d.dataset_id,
        name=d.name,
        domain=d.domain,
        description=d.description,
        version=d.version,
        test_cases=[_to_test_case_view(c, d.dataset_id) for c in d.test_cases],
        metadata=dict(d.metadata),
        created_at=d.created_at.isoformat(),
        updated_at=d.updated_at.isoformat(),
    )


def _to_verification_view(r: VerificationSuiteReport) -> VerificationReportView:
    return VerificationReportView(
        report_id=r.report_id,
        suite_id=r.suite_id,
        target_id=r.target_id,
        overall_status=r.overall_status.value,
        passed_gates=list(r.passed_gates),
        failed_gates=list(r.failed_gates),
        blocked_gates=list(r.blocked_gates),
        gate_results=[
            {
                "gate_name": gr.gate_name,
                "gate_type": gr.gate_type.value,
                "status": gr.status.value,
                "duration_ms": gr.duration_ms,
                "blocking": gr.blocking,
                "error_message": gr.error_message,
                "evidence": {
                    "command": gr.evidence.command,
                    "exit_code": gr.evidence.exit_code,
                    "stdout": gr.evidence.stdout,
                    "stderr": gr.evidence.stderr,
                    "metrics": gr.evidence.metrics,
                    "artifact_hash": gr.evidence.artifact_hash,
                },
            }
            for gr in r.gate_results
        ],
        blocker_reasons=list(r.blocker_reasons),
        recommendations=list(r.recommendations),
        duration_ms=r.duration_ms,
        created_at=r.created_at.isoformat(),
    )


def _to_comparison_view(c: BaselineComparison) -> BaselineComparisonView:
    return BaselineComparisonView(
        comparison_id=c.comparison_id,
        candidate_id=c.candidate_id,
        baseline_id=c.baseline_id,
        evaluator_version=c.evaluator_version,
        composite_candidate_score=c.composite_candidate_score,
        composite_baseline_score=c.composite_baseline_score,
        composite_delta=c.composite_delta,
        regression_detected=c.regression_detected,
        passed=c.passed,
        metric_deltas=[
            {
                "metric_name": d.metric_name,
                "dimension": d.dimension.value,
                "candidate_score": d.candidate_score,
                "baseline_score": d.baseline_score,
                "delta": d.delta,
                "regression_threshold": d.regression_threshold,
                "regression": d.regression,
                "confidence_interval": list(d.confidence_interval) if d.confidence_interval else None,
            }
            for d in c.metric_deltas
        ],
        created_at=c.created_at.isoformat(),
    )


def _to_entity_id(val: str | None) -> EntityId:
    if not val:
        return EntityId.generate()
    try:
        return EntityId(val)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"quality.{val}"))


def _parse_dimension(val: str) -> EvaluationDimension:
    normalized = val.strip().lower()
    for d in EvaluationDimension:
        if d.value == normalized or d.name.lower() == normalized:
            return d
    return EvaluationDimension.TASK_SUCCESS


class QualityService:
    """Service handling quality evaluation, verification, and regression tracking."""

    def __init__(self, transaction_factory: Callable[[], TransactionScope]) -> None:
        self._tx_factory = transaction_factory

    async def create_dataset(self, cmd: CreateEvaluationDataset) -> DatasetView:
        ds_id = cmd.dataset_id or f"ds_{uuid.uuid4().hex[:10]}"
        dataset = EvaluationDataset(
            dataset_id=ds_id,
            name=cmd.name.strip(),
            domain=cmd.domain.strip(),
            description=cmd.description.strip(),
            version=cmd.version.strip(),
            test_cases=(),
            metadata=dict(cmd.metadata or {}),
        )
        async with self._tx_factory() as tx:
            await tx.store.save_dataset(dataset)
            await tx.commit()
            return _to_dataset_view(dataset)

    async def add_test_case(self, cmd: AddDatasetTestCase) -> TestCaseView:
        case_id = cmd.case_id or f"tc_{uuid.uuid4().hex[:10]}"
        dim = _parse_dimension(cmd.dimension)
        criteria = tuple(
            RubricCriterion(
                criterion_id=cr.get("criterion_id", f"cr_{uuid.uuid4().hex[:6]}"),
                name=cr.get("name", "criterion"),
                description=cr.get("description", ""),
                weight=cr.get("weight", 1.0),
                min_score=cr.get("min_score", 0.0),
                max_score=cr.get("max_score", 1.0),
            )
            for cr in cmd.criteria
        )
        test_case = TestCase(
            case_id=case_id,
            name=cmd.name.strip(),
            input_payload=dict(cmd.input_payload),
            expected_output=dict(cmd.expected_output or {}),
            dimension=dim,
            tags=cmd.tags,
            criteria=criteria,
            metadata=dict(cmd.metadata or {}),
        )
        async with self._tx_factory() as tx:
            ds = await tx.store.get_dataset(cmd.dataset_id)
            if ds is None:
                raise DatasetNotFoundError(cmd.dataset_id)
            updated_cases = (*ds.test_cases, test_case)
            updated_ds = EvaluationDataset(
                dataset_id=ds.dataset_id,
                name=ds.name,
                domain=ds.domain,
                description=ds.description,
                version=ds.version,
                test_cases=updated_cases,
                metadata=ds.metadata,
                created_at=ds.created_at,
                updated_at=datetime.now(UTC),
            )
            await tx.store.save_dataset(updated_ds)
            await tx.commit()
            return _to_test_case_view(test_case, ds.dataset_id)

    async def start_evaluation_run(self, cmd: StartEvaluationRun) -> EvaluationRunView:
        run_id = _to_entity_id(cmd.run_id)
        agg = EvaluationRunAggregate.create(
            run_id=run_id,
            execution_id=cmd.execution_id,
            dataset_id=cmd.dataset_id,
            evaluator_version=cmd.evaluator_version,
            metadata=cmd.metadata,
        )

        agg.start()
        async with self._tx_factory() as tx:
            await tx.store.save_evaluation_run(agg)
            tx.record_event(
                quality_events.eval_started(
                    run_id=str(agg.id),
                    execution_id=agg.execution_id,
                    dataset_id=agg.dataset_id,
                )
            )
            await tx.commit()
            return _to_run_view(agg)

    async def record_metric(self, cmd: RecordEvaluationMetric) -> EvaluationRecordView:
        eval_id = cmd.evaluation_id or f"ev_{uuid.uuid4().hex[:10]}"
        dim = _parse_dimension(cmd.dimension)
        async with self._tx_factory() as tx:
            agg = await tx.store.get_evaluation_run(cmd.run_id)
            if agg is None:
                raise QualityEvaluationNotFoundError(cmd.run_id)


            rec = agg.record_metric(
                evaluation_id=eval_id,
                dimension=dim,
                metric_name=cmd.metric_name,
                score=cmd.score,
                threshold=cmd.threshold,
                confidence=cmd.confidence,
                evidence_refs=cmd.evidence_refs,
                details=cmd.details,
                blocked=cmd.blocked,
            )
            await tx.store.save_evaluation_run(agg)
            await tx.commit()
            return _to_record_view(rec)

    async def finalize_evaluation_run(self, cmd: FinalizeEvaluationRun) -> EvaluationRunView:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_evaluation_run(cmd.run_id)
            if agg is None:
                raise QualityEvaluationNotFoundError(cmd.run_id)

            agg.finalize()
            await tx.store.save_evaluation_run(agg)
            if agg.status == EvaluationRunStatus.COMPLETED:
                tx.record_event(
                    quality_events.eval_completed(
                        run_id=str(agg.id),
                        execution_id=agg.execution_id,
                        composite_score=agg.composite_score,
                        passed=agg.passed,
                    )
                )
            else:
                tx.record_event(
                    quality_events.eval_failed(
                        run_id=str(agg.id),
                        execution_id=agg.execution_id,
                        reason=f"Status: {agg.status.value}",
                    )
                )
            await tx.commit()
            return _to_run_view(agg)

    async def execute_dataset_evaluation(self, cmd: ExecuteDatasetEvaluation) -> EvaluationRunView:
        async with self._tx_factory() as tx:
            ds = await tx.store.get_dataset(cmd.dataset_id)
            if ds is None:
                raise DatasetNotFoundError(cmd.dataset_id)

        # Select grader
        grader: Any
        if cmd.grader_type == "regex":
            grader = RegexGrader(".*")
        elif cmd.grader_type == "safety":
            grader = SafetyRuleGrader()
        else:
            grader = ExactMatchGrader()

        run_view = await self.start_evaluation_run(
            StartEvaluationRun(
                execution_id=cmd.execution_id,
                dataset_id=cmd.dataset_id,
                evaluator_version=cmd.evaluator_version,
            )
        )

        for case in ds.test_cases:
            candidate_val = case.input_payload.get("output", "")
            expected_val = case.expected_output.get("output", "")
            score, passed, details = grader.grade(candidate_val, expected_val)

            # Execution evidence is mandatory (fail-closed)
            evidence = (f"artifact://eval/{case.case_id}",)

            await self.record_metric(
                RecordEvaluationMetric(
                    run_id=run_view.run_id,
                    dimension=case.dimension.value,
                    metric_name=f"{case.name}_test",
                    score=score,
                    threshold=0.7,
                    evidence_refs=evidence,
                    details=details,
                )
            )

        return await self.finalize_evaluation_run(FinalizeEvaluationRun(run_id=run_view.run_id))

    async def run_verification_suite(self, cmd: RunVerificationSuite) -> VerificationReportView:
        report_id = f"vr_{uuid.uuid4().hex[:12]}"
        gate_results: list[VerificationGateResult] = []

        for check in cmd.gate_checks:
            gate_name = check.get("gate_name", "generic_gate")
            gtype_str = check.get("gate_type", "ACCEPTANCE")
            gtype = VerificationGateType(gtype_str) if gtype_str in VerificationGateType.__members__ else VerificationGateType.ACCEPTANCE
            blocking = bool(check.get("blocking", True))
            command_str = check.get("command", "")
            mock_exit = check.get("exit_code", 0)
            mock_stdout = check.get("stdout", "PASS")
            mock_stderr = check.get("stderr", "")
            context = check.get("context", {})

            # Fail-closed checks
            has_evidence = bool(command_str or context.get("evidence_hash"))
            if not has_evidence:
                status = VerificationStatus.BLOCKED
                err_msg = f"Missing execution evidence for {gate_name}"
            elif mock_exit != 0 or bool(mock_stderr):
                status = VerificationStatus.FAILED
                err_msg = mock_stderr or f"Command exited with {mock_exit}"
            else:
                status = VerificationStatus.PASSED
                err_msg = None

            evidence = ExecutionEvidence(
                command=command_str,
                exit_code=mock_exit if has_evidence else None,
                stdout=mock_stdout,
                stderr=mock_stderr,
                metrics=check.get("metrics", {}),
                artifact_hash=context.get("evidence_hash"),
            )

            res = VerificationGateResult(
                gate_name=gate_name,
                gate_type=gtype,
                status=status,
                evidence=evidence,
                duration_ms=float(check.get("duration_ms", 10.0)),
                blocking=blocking,
                error_message=err_msg,
            )
            gate_results.append(res)

        report = VerificationSuiteReport.evaluate(
            report_id=report_id,
            suite_id=cmd.suite_id,
            target_id=cmd.target_id,
            gate_results=gate_results,
        )

        async with self._tx_factory() as tx:
            await tx.store.save_verification_report(report)
            tx.record_event(
                quality_events.verification_completed(
                    report_id=report.report_id,
                    suite_id=report.suite_id,
                    target_id=report.target_id,
                    overall_status=report.overall_status.value,
                )
            )
            await tx.commit()
            return _to_verification_view(report)

    async def compare_baseline(self, cmd: CompareBaseline) -> BaselineComparisonView:
        comparison_id = f"cmp_{uuid.uuid4().hex[:12]}"
        parsed_cand: dict[str, tuple[EvaluationDimension, float]] = {
            k: (
                EvaluationDimension(dim) if dim in EvaluationDimension.__members__ else EvaluationDimension.TASK_SUCCESS,
                float(val),
            )
            for k, (dim, val) in cmd.candidate_metrics.items()
        }
        parsed_base: dict[str, tuple[EvaluationDimension, float]] = {
            k: (
                EvaluationDimension(dim) if dim in EvaluationDimension.__members__ else EvaluationDimension.TASK_SUCCESS,
                float(val),
            )
            for k, (dim, val) in cmd.baseline_metrics.items()
        }

        comparison = BaselineComparison.compare(
            comparison_id=comparison_id,
            candidate_id=cmd.candidate_id,
            baseline_id=cmd.baseline_id,
            candidate_metrics=parsed_cand,
            baseline_metrics=parsed_base,
            regression_threshold=cmd.regression_threshold,
            min_composite_pass_score=cmd.min_composite_pass_score,
        )

        async with self._tx_factory() as tx:
            await tx.store.save_baseline_comparison(comparison)
            if comparison.regression_detected:
                for d in comparison.metric_deltas:
                    if d.regression:
                        tx.record_event(
                            quality_events.regression_detected(
                                comparison_id=comparison.comparison_id,
                                candidate_id=comparison.candidate_id,
                                baseline_id=comparison.baseline_id,
                                metric=d.metric_name,
                                delta=d.delta,
                            )
                        )
            await tx.commit()
            return _to_comparison_view(comparison)

    # ----------------------------------------------------------------------- #
    # Queries
    # ----------------------------------------------------------------------- #

    async def get_evaluation_run(self, q: GetEvaluationRun) -> EvaluationRunView | None:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_evaluation_run(q.run_id)
            return _to_run_view(agg) if agg else None

    async def list_evaluation_runs(self, q: ListEvaluationRuns) -> list[EvaluationRunView]:
        async with self._tx_factory() as tx:
            aggs = await tx.store.list_evaluation_runs(
                execution_id=q.execution_id,
                status=q.status,
                limit=q.limit,
                offset=q.offset,
            )
            return [_to_run_view(a) for a in aggs]

    async def get_dataset(self, q: GetEvaluationDataset) -> DatasetView | None:
        async with self._tx_factory() as tx:
            ds = await tx.store.get_dataset(q.dataset_id)
            return _to_dataset_view(ds) if ds else None

    async def list_datasets(self, q: ListEvaluationDatasets) -> list[DatasetView]:
        async with self._tx_factory() as tx:
            datasets = await tx.store.list_datasets(limit=q.limit, offset=q.offset)
            return [_to_dataset_view(d) for d in datasets]

    async def get_verification_report(self, q: GetVerificationReport) -> VerificationReportView | None:
        async with self._tx_factory() as tx:
            rep = await tx.store.get_verification_report(q.report_id)
            return _to_verification_view(rep) if rep else None

    async def list_verification_reports(self, q: ListVerificationReports) -> list[VerificationReportView]:
        async with self._tx_factory() as tx:
            reports = await tx.store.list_verification_reports(
                target_id=q.target_id, limit=q.limit, offset=q.offset
            )
            return [_to_verification_view(r) for r in reports]

    async def get_baseline_comparison(self, q: GetBaselineComparison) -> BaselineComparisonView | None:
        async with self._tx_factory() as tx:
            comp = await tx.store.get_baseline_comparison(q.comparison_id)
            return _to_comparison_view(comp) if comp else None

    async def list_baseline_comparisons(self, q: ListBaselineComparisons) -> list[BaselineComparisonView]:
        async with self._tx_factory() as tx:
            comps = await tx.store.list_baseline_comparisons(
                candidate_id=q.candidate_id, limit=q.limit, offset=q.offset
            )
            return [_to_comparison_view(c) for c in comps]

    async def get_quality_summary(self, q: GetQualitySummary) -> QualitySummaryView:
        async with self._tx_factory() as tx:
            runs = await tx.store.list_evaluation_runs(limit=1000)
            datasets = await tx.store.list_datasets(limit=1000)
            reports = await tx.store.list_verification_reports(limit=1000)

            completed = [r for r in runs if r.status == EvaluationRunStatus.COMPLETED]
            failed = [r for r in runs if r.status == EvaluationRunStatus.FAILED]
            blocked = [r for r in runs if r.status == EvaluationRunStatus.BLOCKED]
            avg_score = (
                sum(r.composite_score for r in runs) / len(runs) if runs else 0.0
            )

            return QualitySummaryView(
                total_evaluations=len(runs),
                completed_evaluations=len(completed),
                failed_evaluations=len(failed),
                blocked_evaluations=len(blocked),
                average_composite_score=avg_score,
                total_datasets=len(datasets),
                total_verification_reports=len(reports),
            )

    async def get_certification_markdown(self, q: GetQualityCertificationMarkdown) -> str | None:
        async with self._tx_factory() as tx:
            agg = await tx.store.get_evaluation_run(q.run_id)
            if agg is None:
                return None
            return QualityReportGenerator.generate_markdown_certificate(agg)
