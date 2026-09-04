"""SQL adapter for the Quality store."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.ports import QualityStore, TransactionScope
from ..domain.errors import QualityStaleVersionError
from ..domain.evals import (
    EvaluationDataset,
    EvaluationDimension,
    EvaluationRecord,
    EvaluationRunAggregate,
    EvaluationRunStatus,
    RubricCriterion,
    TestCase,
)
from ..domain.regression import BaselineComparison, MetricDelta
from ..domain.verification import (
    ExecutionEvidence,
    VerificationGateResult,
    VerificationGateType,
    VerificationStatus,
    VerificationSuiteReport,
)
from .tables import (
    quality_baseline_comparisons_table,
    quality_datasets_table,
    quality_evaluation_records_table,
    quality_evaluation_runs_table,
    quality_test_cases_table,
    quality_verification_reports_table,
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class SqlQualityStore(QualityStore):
    """SQLAlchemy implementation of QualityStore."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_evaluation_run(self, run_id: str) -> EvaluationRunAggregate | None:
        stmt = select(quality_evaluation_runs_table).where(
            quality_evaluation_runs_table.c.run_id == run_id
        )
        res = await self._session.execute(stmt)
        row = res.mappings().first()
        if not row:
            return None
        return await self._hydrate_run(row)

    async def list_evaluation_runs(
        self,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvaluationRunAggregate]:
        stmt = select(quality_evaluation_runs_table)
        if execution_id:
            stmt = stmt.where(quality_evaluation_runs_table.c.execution_id == execution_id)
        if status:
            stmt = stmt.where(quality_evaluation_runs_table.c.status == status)
        stmt = stmt.limit(limit).offset(offset).order_by(quality_evaluation_runs_table.c.created_at.desc())

        res = await self._session.execute(stmt)
        rows = res.mappings().all()
        return [await self._hydrate_run(row) for row in rows]

    async def save_evaluation_run(
        self, aggregate: EvaluationRunAggregate, expected_version: int | None = None
    ) -> None:
        run_id = str(aggregate.id)
        existing_stmt = select(quality_evaluation_runs_table.c.optimistic_version).where(
            quality_evaluation_runs_table.c.run_id == run_id
        )
        existing_res = await self._session.execute(existing_stmt)
        existing_row = existing_res.first()

        if existing_row is None:
            ins = insert(quality_evaluation_runs_table).values(
                run_id=run_id,
                execution_id=aggregate.execution_id,
                dataset_id=aggregate.dataset_id,
                evaluator_version=aggregate.evaluator_version,
                status=aggregate.status.value,
                composite_score=aggregate.composite_score,
                passed=aggregate.passed,
                metadata_json=_dump(aggregate.metadata),
                optimistic_version=aggregate.optimistic_version,
                created_at=aggregate.created_at,
                updated_at=aggregate.updated_at,
            )
            await self._session.execute(ins)
        else:
            cur_ver = existing_row[0]
            if expected_version is not None and cur_ver != expected_version:
                raise QualityStaleVersionError(run_id, expected_version, cur_ver)

            upd = (
                update(quality_evaluation_runs_table)
                .where(quality_evaluation_runs_table.c.run_id == run_id)
                .values(
                    status=aggregate.status.value,
                    composite_score=aggregate.composite_score,
                    passed=aggregate.passed,
                    metadata_json=_dump(aggregate.metadata),
                    optimistic_version=aggregate.optimistic_version,
                    updated_at=aggregate.updated_at,
                )
            )
            if expected_version is not None:
                upd = upd.where(quality_evaluation_runs_table.c.optimistic_version == expected_version)
            res = await self._session.execute(upd)
            if expected_version is not None and getattr(res, "rowcount", 0) == 0:
                raise QualityStaleVersionError(run_id, expected_version, cur_ver)

        # Sync records
        await self._session.execute(
            delete(quality_evaluation_records_table).where(
                quality_evaluation_records_table.c.run_id == run_id
            )
        )
        if aggregate.records:
            record_values = [
                {
                    "evaluation_id": r.evaluation_id,
                    "run_id": run_id,
                    "execution_id": r.execution_id,
                    "dimension": r.dimension.value,
                    "metric_name": r.metric_name,
                    "score": r.score,
                    "threshold": r.threshold,
                    "confidence": r.confidence,
                    "evidence_refs_json": _dump(list(r.evidence_refs)),
                    "passed": r.passed,
                    "blocked": r.blocked,
                    "details_json": _dump(r.details),
                    "evaluator_version": r.evaluator_version,
                    "created_at": r.created_at,
                }
                for r in aggregate.records
            ]
            await self._session.execute(insert(quality_evaluation_records_table).values(record_values))

    async def get_dataset(self, dataset_id: str) -> EvaluationDataset | None:
        stmt = select(quality_datasets_table).where(quality_datasets_table.c.dataset_id == dataset_id)
        res = await self._session.execute(stmt)
        row = res.mappings().first()
        if not row:
            return None
        return await self._hydrate_dataset(row)

    async def list_datasets(self, limit: int = 50, offset: int = 0) -> list[EvaluationDataset]:
        stmt = (
            select(quality_datasets_table)
            .limit(limit)
            .offset(offset)
            .order_by(quality_datasets_table.c.created_at.desc())
        )
        res = await self._session.execute(stmt)
        rows = res.mappings().all()
        return [await self._hydrate_dataset(r) for r in rows]

    async def save_dataset(self, dataset: EvaluationDataset) -> None:
        ds_id = dataset.dataset_id
        existing_stmt = select(quality_datasets_table.c.dataset_id).where(
            quality_datasets_table.c.dataset_id == ds_id
        )
        existing_res = await self._session.execute(existing_stmt)
        if existing_res.first() is None:
            ins = insert(quality_datasets_table).values(
                dataset_id=ds_id,
                name=dataset.name,
                domain=dataset.domain,
                description=dataset.description,
                version=dataset.version,
                metadata_json=_dump(dataset.metadata),
                created_at=dataset.created_at,
                updated_at=dataset.updated_at,
            )
            await self._session.execute(ins)
        else:
            upd = (
                update(quality_datasets_table)
                .where(quality_datasets_table.c.dataset_id == ds_id)
                .values(
                    name=dataset.name,
                    domain=dataset.domain,
                    description=dataset.description,
                    version=dataset.version,
                    metadata_json=_dump(dataset.metadata),
                    updated_at=dataset.updated_at,
                )
            )
            await self._session.execute(upd)

        # Sync test cases
        await self._session.execute(
            delete(quality_test_cases_table).where(quality_test_cases_table.c.dataset_id == ds_id)
        )
        if dataset.test_cases:
            case_values = [
                {
                    "case_id": c.case_id,
                    "dataset_id": ds_id,
                    "name": c.name,
                    "dimension": c.dimension.value,
                    "input_payload_json": _dump(c.input_payload),
                    "expected_output_json": _dump(c.expected_output),
                    "tags_json": _dump(list(c.tags)),
                    "criteria_json": _dump(
                        [
                            {
                                "criterion_id": cr.criterion_id,
                                "name": cr.name,
                                "description": cr.description,
                                "weight": cr.weight,
                                "min_score": cr.min_score,
                                "max_score": cr.max_score,
                            }
                            for cr in c.criteria
                        ]
                    ),
                    "metadata_json": _dump(c.metadata),
                }
                for c in dataset.test_cases
            ]
            await self._session.execute(insert(quality_test_cases_table).values(case_values))

    async def get_verification_report(self, report_id: str) -> VerificationSuiteReport | None:
        stmt = select(quality_verification_reports_table).where(
            quality_verification_reports_table.c.report_id == report_id
        )
        res = await self._session.execute(stmt)
        row = res.mappings().first()
        if not row:
            return None
        return self._hydrate_verification_report(row)

    async def list_verification_reports(
        self, target_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[VerificationSuiteReport]:
        stmt = select(quality_verification_reports_table)
        if target_id:
            stmt = stmt.where(quality_verification_reports_table.c.target_id == target_id)
        stmt = (
            stmt.limit(limit)
            .offset(offset)
            .order_by(quality_verification_reports_table.c.created_at.desc())
        )
        res = await self._session.execute(stmt)
        rows = res.mappings().all()
        return [self._hydrate_verification_report(r) for r in rows]

    async def save_verification_report(self, report: VerificationSuiteReport) -> None:
        ins = insert(quality_verification_reports_table).values(
            report_id=report.report_id,
            suite_id=report.suite_id,
            target_id=report.target_id,
            overall_status=report.overall_status.value,
            passed_gates_json=_dump(list(report.passed_gates)),
            failed_gates_json=_dump(list(report.failed_gates)),
            blocked_gates_json=_dump(list(report.blocked_gates)),
            gate_results_json=_dump(
                [
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
                    for gr in report.gate_results
                ]
            ),
            blocker_reasons_json=_dump(list(report.blocker_reasons)),
            recommendations_json=_dump(list(report.recommendations)),
            duration_ms=report.duration_ms,
            created_at=report.created_at,
        )
        await self._session.execute(ins)

    async def get_baseline_comparison(self, comparison_id: str) -> BaselineComparison | None:
        stmt = select(quality_baseline_comparisons_table).where(
            quality_baseline_comparisons_table.c.comparison_id == comparison_id
        )
        res = await self._session.execute(stmt)
        row = res.mappings().first()
        if not row:
            return None
        return self._hydrate_baseline_comparison(row)

    async def list_baseline_comparisons(
        self, candidate_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[BaselineComparison]:
        stmt = select(quality_baseline_comparisons_table)
        if candidate_id:
            stmt = stmt.where(quality_baseline_comparisons_table.c.candidate_id == candidate_id)
        stmt = (
            stmt.limit(limit)
            .offset(offset)
            .order_by(quality_baseline_comparisons_table.c.created_at.desc())
        )
        res = await self._session.execute(stmt)
        rows = res.mappings().all()
        return [self._hydrate_baseline_comparison(r) for r in rows]

    async def save_baseline_comparison(self, comparison: BaselineComparison) -> None:
        ins = insert(quality_baseline_comparisons_table).values(
            comparison_id=comparison.comparison_id,
            candidate_id=comparison.candidate_id,
            baseline_id=comparison.baseline_id,
            evaluator_version=comparison.evaluator_version,
            composite_candidate_score=comparison.composite_candidate_score,
            composite_baseline_score=comparison.composite_baseline_score,
            composite_delta=comparison.composite_delta,
            regression_detected=comparison.regression_detected,
            passed=comparison.passed,
            metric_deltas_json=_dump(
                [
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
                    for d in comparison.metric_deltas
                ]
            ),
            metadata_json=_dump(comparison.metadata),
            created_at=comparison.created_at,
        )
        await self._session.execute(ins)

    # ----------------------------------------------------------------------- #
    # Hydration helpers
    # ----------------------------------------------------------------------- #

    async def _hydrate_run(self, row: Any) -> EvaluationRunAggregate:
        run_id = row["run_id"]
        # Fetch records
        stmt = select(quality_evaluation_records_table).where(
            quality_evaluation_records_table.c.run_id == run_id
        )
        res = await self._session.execute(stmt)
        r_rows = res.mappings().all()

        records = [
            EvaluationRecord(
                evaluation_id=r["evaluation_id"],
                run_id=r["run_id"],
                execution_id=r["execution_id"],
                dimension=EvaluationDimension(r["dimension"]),
                metric_name=r["metric_name"],
                score=r["score"],
                threshold=r["threshold"],
                confidence=r["confidence"],
                evidence_refs=tuple(json.loads(r["evidence_refs_json"] or "[]")),
                passed=r["passed"],
                blocked=r["blocked"],
                details=json.loads(r["details_json"] or "{}"),
                evaluator_version=r["evaluator_version"],
                created_at=_as_utc(r["created_at"]) or datetime.now(UTC),
            )
            for r in r_rows
        ]

        meta = json.loads(row["metadata_json"] or "{}")
        return EvaluationRunAggregate(
            id=EntityId(run_id),
            execution_id=row["execution_id"],
            dataset_id=row["dataset_id"],
            evaluator_version=row["evaluator_version"],
            status=EvaluationRunStatus(row["status"]),
            records=records,
            composite_score=row["composite_score"],
            passed=row["passed"],
            metadata=meta,
            optimistic_version=row["optimistic_version"],
            created_at=_as_utc(row["created_at"]) or datetime.now(UTC),
            updated_at=_as_utc(row["updated_at"]) or datetime.now(UTC),
        )

    async def _hydrate_dataset(self, row: Any) -> EvaluationDataset:
        ds_id = row["dataset_id"]
        stmt = select(quality_test_cases_table).where(quality_test_cases_table.c.dataset_id == ds_id)
        res = await self._session.execute(stmt)
        c_rows = res.mappings().all()

        cases = [
            TestCase(
                case_id=c["case_id"],
                name=c["name"],
                dimension=EvaluationDimension(c["dimension"]),
                input_payload=json.loads(c["input_payload_json"] or "{}"),
                expected_output=json.loads(c["expected_output_json"] or "{}"),
                tags=tuple(json.loads(c["tags_json"] or "[]")),
                criteria=tuple(
                    RubricCriterion(
                        criterion_id=cr["criterion_id"],
                        name=cr["name"],
                        description=cr["description"],
                        weight=cr["weight"],
                        min_score=cr["min_score"],
                        max_score=cr["max_score"],
                    )
                    for cr in json.loads(c["criteria_json"] or "[]")
                ),
                metadata=json.loads(c["metadata_json"] or "{}"),
            )
            for c in c_rows
        ]

        meta = json.loads(row["metadata_json"] or "{}")
        return EvaluationDataset(
            dataset_id=ds_id,
            name=row["name"],
            domain=row["domain"],
            description=row["description"],
            version=row["version"],
            test_cases=tuple(cases),
            metadata=meta,
            created_at=_as_utc(row["created_at"]) or datetime.now(UTC),
            updated_at=_as_utc(row["updated_at"]) or datetime.now(UTC),
        )

    def _hydrate_verification_report(self, row: Any) -> VerificationSuiteReport:
        results_data = json.loads(row["gate_results_json"] or "[]")
        gate_results = [
            VerificationGateResult(
                gate_name=gr["gate_name"],
                gate_type=VerificationGateType(gr["gate_type"]),
                status=VerificationStatus(gr["status"]),
                evidence=ExecutionEvidence(
                    command=gr["evidence"].get("command", ""),
                    exit_code=gr["evidence"].get("exit_code"),
                    stdout=gr["evidence"].get("stdout", ""),
                    stderr=gr["evidence"].get("stderr", ""),
                    metrics=gr["evidence"].get("metrics", {}),
                    artifact_hash=gr["evidence"].get("artifact_hash"),
                ),
                duration_ms=gr.get("duration_ms", 0.0),
                blocking=gr.get("blocking", True),
                error_message=gr.get("error_message"),
            )
            for gr in results_data
        ]

        return VerificationSuiteReport(
            report_id=row["report_id"],
            suite_id=row["suite_id"],
            target_id=row["target_id"],
            overall_status=VerificationStatus(row["overall_status"]),
            passed_gates=tuple(json.loads(row["passed_gates_json"] or "[]")),
            failed_gates=tuple(json.loads(row["failed_gates_json"] or "[]")),
            blocked_gates=tuple(json.loads(row["blocked_gates_json"] or "[]")),
            gate_results=tuple(gate_results),
            blocker_reasons=tuple(json.loads(row["blocker_reasons_json"] or "[]")),
            recommendations=tuple(json.loads(row["recommendations_json"] or "[]")),
            duration_ms=row["duration_ms"],
            created_at=_as_utc(row["created_at"]) or datetime.now(UTC),
        )

    def _hydrate_baseline_comparison(self, row: Any) -> BaselineComparison:
        deltas_data = json.loads(row["metric_deltas_json"] or "[]")
        deltas = [
            MetricDelta(
                metric_name=d["metric_name"],
                dimension=EvaluationDimension(d["dimension"]),
                candidate_score=d["candidate_score"],
                baseline_score=d["baseline_score"],
                delta=d["delta"],
                regression_threshold=d["regression_threshold"],
                regression=d["regression"],
                confidence_interval=tuple(d["confidence_interval"]) if d.get("confidence_interval") else None,
            )
            for d in deltas_data
        ]

        meta = json.loads(row["metadata_json"] or "{}")
        return BaselineComparison(
            comparison_id=row["comparison_id"],
            candidate_id=row["candidate_id"],
            baseline_id=row["baseline_id"],
            evaluator_version=row["evaluator_version"],
            composite_candidate_score=row["composite_candidate_score"],
            composite_baseline_score=row["composite_baseline_score"],
            composite_delta=row["composite_delta"],
            regression_detected=row["regression_detected"],
            passed=row["passed"],
            metric_deltas=tuple(deltas),
            metadata=meta,
            created_at=_as_utc(row["created_at"]) or datetime.now(UTC),
        )


class SqlTransactionScope(TransactionScope):
    """SQL unit of work transaction scope for Quality with outbox event recording."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None
        self._events: list[EventEnvelope] = []

    @property
    def store(self) -> QualityStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return SqlQualityStore(self._uow.session)

    def record_event(self, envelope: EventEnvelope) -> None:
        self._events.append(envelope)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        if self._events:
            outbox = TransactionalOutbox(self._uow)
            for env in self._events:
                await outbox.record_next(env)
        await self._uow.commit()

    async def rollback(self) -> None:
        if self._uow is not None:
            await self._uow.rollback()

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):
            raise TypeError("transaction scope requires a SQL unit of work")
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_val, None)
            self._uow = None
        return False


def sql_scope_factory(database: Database) -> Callable[[], TransactionScope]:
    return lambda: SqlTransactionScope(database)


