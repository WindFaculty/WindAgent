"""Evaluation domain models, dimensions, records, and datasets."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now


def _ensure_entity_id(value: EntityId | str) -> EntityId:
    if isinstance(value, EntityId):
        return value
    try:
        return EntityId(value)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"quality.{value}"))


class EvaluationDimension(StrEnum):
    """The 11 core evaluation dimensions of WindAgent."""

    TASK_SUCCESS = "task_success"
    ARTIFACT_QUALITY = "artifact_quality"
    TOOL_CORRECTNESS = "tool_correctness"
    SAFETY = "safety"
    COST = "cost"
    LATENCY = "latency"
    RELIABILITY = "reliability"
    MODEL_ROUTING = "model_routing"
    CONTEXT_EFFICIENCY = "context_efficiency"
    DELEGATION_EFFICIENCY = "delegation_efficiency"
    REGRESSION = "regression"


class EvaluationRunStatus(StrEnum):
    """Lifecycle state of an evaluation run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    """Immutable, typed projection of an evaluation result on an execution run.

    Fail-closed invariant: If evidence_refs is empty or blocked is True,
    passed is strictly False and the record is flagged as blocked.
    """

    evaluation_id: str
    run_id: str
    execution_id: str
    dimension: EvaluationDimension
    metric_name: str
    score: float  # Normalized 0.0 to 1.0
    threshold: float = 0.7
    confidence: float = 1.0
    evidence_refs: tuple[str, ...] = ()
    passed: bool = False
    blocked: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    evaluator_version: str = "2.0.0"
    created_at: datetime = field(default_factory=utc_now)

    def has_evidence(self) -> bool:
        return len(self.evidence_refs) > 0 and not self.blocked


@dataclass(frozen=True, slots=True)
class RubricCriterion:
    """A grading rubric criterion for qualitative or multi-criteria evaluation."""

    criterion_id: str
    name: str
    description: str
    weight: float = 1.0
    min_score: float = 0.0
    max_score: float = 1.0


@dataclass(frozen=True, slots=True)
class TestCase:
    """A deterministic test case within an evaluation dataset."""

    case_id: str
    name: str
    input_payload: dict[str, Any]
    expected_output: dict[str, Any] = field(default_factory=dict)
    dimension: EvaluationDimension = EvaluationDimension.TASK_SUCCESS
    tags: tuple[str, ...] = ()
    criteria: tuple[RubricCriterion, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    """A gold-standard benchmark evaluation dataset."""

    dataset_id: str
    name: str
    domain: str
    description: str = ""
    version: str = "1.0.0"
    test_cases: tuple[TestCase, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class EvaluationRunAggregate:
    """Aggregate coordinating a suite of evaluation records against an execution run."""

    id: EntityId
    execution_id: str
    dataset_id: str | None
    evaluator_version: str
    status: EvaluationRunStatus = EvaluationRunStatus.PENDING
    records: list[EvaluationRecord] = field(default_factory=list)
    composite_score: float = 0.0
    passed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    optimistic_version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        run_id: EntityId | str,
        execution_id: str,
        dataset_id: str | None = None,
        evaluator_version: str = "2.0.0",
        metadata: Mapping[str, Any] | None = None,
    ) -> EvaluationRunAggregate:
        now = utc_now()
        return cls(
            id=_ensure_entity_id(run_id),
            execution_id=execution_id.strip(),
            dataset_id=dataset_id.strip() if dataset_id else None,
            evaluator_version=evaluator_version,
            status=EvaluationRunStatus.PENDING,
            records=[],
            composite_score=0.0,
            passed=False,
            metadata=dict(metadata or {}),
            optimistic_version=1,
            created_at=now,
            updated_at=now,
        )

    def start(self) -> None:
        self.status = EvaluationRunStatus.RUNNING
        self.touch()

    def record_metric(
        self,
        evaluation_id: str,
        dimension: EvaluationDimension,
        metric_name: str,
        score: float,
        threshold: float = 0.7,
        confidence: float = 1.0,
        evidence_refs: tuple[str, ...] = (),
        details: Mapping[str, Any] | None = None,
        blocked: bool = False,
    ) -> EvaluationRecord:
        # Enforce fail-closed evidence requirement
        clamped_score = max(0.0, min(1.0, score))
        has_ev = len(evidence_refs) > 0 and not blocked
        passed = (clamped_score >= threshold) if has_ev else False
        is_blocked = blocked or not has_ev

        rec = EvaluationRecord(
            evaluation_id=evaluation_id,
            run_id=str(self.id),
            execution_id=self.execution_id,
            dimension=dimension,
            metric_name=metric_name,
            score=clamped_score if not is_blocked else 0.0,
            threshold=threshold,
            confidence=confidence,
            evidence_refs=evidence_refs,
            passed=passed,
            blocked=is_blocked,
            details=dict(details or {}),
            evaluator_version=self.evaluator_version,
            created_at=utc_now(),
        )
        self.records.append(rec)
        self.touch()
        return rec

    def finalize(self) -> None:
        if not self.records:
            self.status = EvaluationRunStatus.BLOCKED
            self.composite_score = 0.0
            self.passed = False
            self.touch()
            return

        total_score = sum(r.score for r in self.records)
        self.composite_score = total_score / len(self.records)
        any_blocked = any(r.blocked for r in self.records)
        all_passed = all(r.passed for r in self.records)

        if any_blocked:
            self.status = EvaluationRunStatus.BLOCKED
            self.passed = False
        elif all_passed:
            self.status = EvaluationRunStatus.COMPLETED
            self.passed = True
        else:
            self.status = EvaluationRunStatus.FAILED
            self.passed = False
        self.touch()

    def touch(self) -> None:
        self.optimistic_version += 1
        self.updated_at = utc_now()
