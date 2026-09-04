"""Outbox event factory for the Quality bounded context."""

from __future__ import annotations

import uuid

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.types import Version


def _eid(value: str) -> EntityId:
    try:
        return EntityId(value)
    except (ValueError, TypeError):
        return EntityId(uuid.uuid5(uuid.NAMESPACE_DNS, f"quality.{value}"))


class QualityEventFactory:
    """Produces canonical quality.* event envelopes."""

    def eval_started(
        self,
        run_id: str,
        execution_id: str,
        dataset_id: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.eval.started",
            aggregate_type="evaluation_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={
                "run_id": run_id,
                "execution_id": execution_id,
                "dataset_id": dataset_id,
            },
            event_version=Version(1),
        )

    def eval_completed(
        self,
        run_id: str,
        execution_id: str,
        composite_score: float,
        passed: bool,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.eval.completed",
            aggregate_type="evaluation_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={
                "run_id": run_id,
                "execution_id": execution_id,
                "composite_score": composite_score,
                "passed": passed,
            },
            event_version=Version(1),
        )

    def eval_failed(
        self,
        run_id: str,
        execution_id: str,
        reason: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.eval.failed",
            aggregate_type="evaluation_run",
            aggregate_id=_eid(run_id),
            sequence=0,
            payload={
                "run_id": run_id,
                "execution_id": execution_id,
                "reason": reason,
            },
            event_version=Version(1),
        )

    def gate_evaluated(
        self,
        gate_name: str,
        target_id: str,
        status: str,
        blocking: bool,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.gate.evaluated",
            aggregate_type="verification_gate",
            aggregate_id=_eid(f"{gate_name}_{target_id}"),
            sequence=0,
            payload={
                "gate_name": gate_name,
                "target_id": target_id,
                "status": status,
                "blocking": blocking,
            },
            event_version=Version(1),
        )

    def verification_completed(
        self,
        report_id: str,
        suite_id: str,
        target_id: str,
        overall_status: str,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.verification.completed",
            aggregate_type="verification_report",
            aggregate_id=_eid(report_id),
            sequence=0,
            payload={
                "report_id": report_id,
                "suite_id": suite_id,
                "target_id": target_id,
                "overall_status": overall_status,
            },
            event_version=Version(1),
        )

    def regression_detected(
        self,
        comparison_id: str,
        candidate_id: str,
        baseline_id: str,
        metric: str,
        delta: float,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.regression.detected",
            aggregate_type="baseline_comparison",
            aggregate_id=_eid(comparison_id),
            sequence=0,
            payload={
                "comparison_id": comparison_id,
                "candidate_id": candidate_id,
                "baseline_id": baseline_id,
                "metric": metric,
                "delta": delta,
            },
            event_version=Version(1),
        )

    def baseline_promoted(
        self,
        candidate_id: str,
        promoted_to_baseline_id: str,
        composite_score: float,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type="quality.baseline.promoted",
            aggregate_type="baseline",
            aggregate_id=_eid(promoted_to_baseline_id),
            sequence=0,
            payload={
                "candidate_id": candidate_id,
                "promoted_to_baseline_id": promoted_to_baseline_id,
                "composite_score": composite_score,
            },
            event_version=Version(1),
        )


quality_events = QualityEventFactory()
