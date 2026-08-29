"""Evaluation Engine V2 (Phase 7 — ban_ke_hoach_v1 §12).

Orchestrates multi-dimensional evaluation of agent execution trajectories,
fail-closed grading, durable EvaluationRecord generation, and candidate vs baseline
comparisons with statistical confidence intervals.
"""

from __future__ import annotations

import math
import statistics
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from windagent_core.domain.evaluation import (
    BaselineComparison,
    EvaluationDimension,
    EvaluationRecord,
    MetricDelta,
)
from windagent_core.domain.trajectory import ExecutionTrajectory
from windagent_evals.datasets import EvalTestCase
from windagent_evals.graders import (
    ArtifactQualityGrader,
    ContextEfficiencyGrader,
    CostEfficiencyGrader,
    DelegationEfficiencyGrader,
    Grader,
    GradingResult,
    LatencyGrader,
    ModelRoutingGrader,
    RegressionGrader,
    ReliabilityGrader,
    SafetyGrader,
    TaskSuccessGrader,
    ToolCorrectnessGrader,
)


class EvaluationEngineV2:
    """Evaluation Engine V2 authority for WindAgent.

    Evaluates execution trajectories across 11 dimensions, enforces strict fail-closed
    rules, generates immutable EvaluationRecords, and computes statistical baseline comparisons.
    """

    def __init__(
        self,
        evaluator_version: str = "2.0.0",
        graders: Optional[List[Grader]] = None,
        default_regression_threshold: float = 0.05,
    ) -> None:
        self.evaluator_version = evaluator_version
        self.regression_threshold = default_regression_threshold
        self.graders: List[Grader] = graders if graders is not None else [
            TaskSuccessGrader(),
            ArtifactQualityGrader(),
            ToolCorrectnessGrader(),
            SafetyGrader(),
            CostEfficiencyGrader(),
            LatencyGrader(),
            ReliabilityGrader(),
            ModelRoutingGrader(),
            ContextEfficiencyGrader(),
            DelegationEfficiencyGrader(),
            RegressionGrader(regression_threshold=default_regression_threshold),
        ]

    def _trajectory_to_execution_data(self, trajectory: ExecutionTrajectory) -> Dict[str, Any]:
        """Converts an ExecutionTrajectory domain model into a structured evaluation payload."""
        output = ""
        used_tools = []
        steps_list = []
        artifacts_list = []
        policy_violations = []
        leaked_secrets = []

        for step in trajectory.steps:
            steps_list.append({
                "identifier": step.identifier,
                "kind": step.kind,
                "sequence": step.sequence,
                "status": step.status,
                "details": step.details,
            })
            if step.kind == "tool_execution":
                tool_name = step.details.get("tool_name") or step.identifier
                used_tools.append(tool_name)
            if step.kind in ("agent_turn", "conversation_event"):
                text = step.details.get("output") or step.details.get("content") or ""
                if text:
                    output += "\n" + str(text)

        for art in trajectory.artifacts:
            artifacts_list.append({
                "artifact_id": art.artifact_id,
                "kind": art.kind,
                "content_redacted_preview": art.content_redacted_preview,
                "failure_reason": art.failure_reason,
            })

        outcome_dict = {
            "succeeded": trajectory.outcome.succeeded,
            "terminal_state": trajectory.outcome.terminal_state,
            "error_class": trajectory.outcome.error_class,
            "error_message": trajectory.outcome.error_message,
        }

        cost_usd = trajectory.metrics.cost_usd if trajectory.metrics else 0.0
        prompt_tokens = trajectory.metrics.prompt_tokens if trajectory.metrics else 0
        completion_tokens = trajectory.metrics.completion_tokens if trajectory.metrics else 0
        latency_ms = trajectory.metrics.latency_ms if trajectory.metrics else 0
        retry_count = trajectory.metrics.retry_count if trajectory.metrics else 0

        # Scan for secret patterns or policy violations in step details
        for step in trajectory.steps:
            text_repr = str(step.details)
            if "sk-" in text_repr or "ghp_" in text_repr or "BEGIN PRIVATE KEY" in text_repr:
                leaked_secrets.append(f"Secret detected in step {step.identifier}")

        return {
            "execution_id": trajectory.execution_id,
            "trajectory_id": trajectory.execution_id,
            "output": output.strip(),
            "used_tools": used_tools,
            "steps": steps_list,
            "artifacts": artifacts_list,
            "outcome": outcome_dict,
            "cost_usd": cost_usd or 0.0,
            "prompt_tokens": prompt_tokens or 0,
            "completion_tokens": completion_tokens or 0,
            "latency_sec": (latency_ms or 0) / 1000.0,
            "retry_count": retry_count or 0,
            "policy_violations": policy_violations,
            "leaked_secrets": leaked_secrets,
            "model": trajectory.agent_type or "",
        }

    def evaluate_case(
        self,
        test_case: EvalTestCase,
        execution_data: Dict[str, Any],
        harness_version: Optional[str] = None,
        trajectory_id: Optional[str] = None,
    ) -> List[EvaluationRecord]:
        """Evaluates a test case against all configured dimension graders.

        Fail-closed: if execution evidence is missing or invalid, marks blocked=True.
        """
        records: List[EvaluationRecord] = []
        exec_id = execution_data.get("execution_id") or test_case.execution_id or f"exec_{uuid.uuid4().hex[:8]}"
        traj_id = trajectory_id or execution_data.get("trajectory_id") or exec_id

        # Fail-closed check: if test_case has no execution_id and no real execution data
        if not test_case.has_execution and not execution_data.get("output") and not execution_data.get("steps"):
            for grader in self.graders:
                records.append(EvaluationRecord(
                    evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
                    execution_id=exec_id,
                    trajectory_id=traj_id,
                    evaluator_version=self.evaluator_version,
                    harness_version=harness_version,
                    dimension=grader.dimension,
                    metric_name=grader.metric_name,
                    score=0.0,
                    threshold=grader.threshold,
                    confidence=1.0,
                    evidence_refs=[],
                    passed=False,
                    blocked=True,
                    details={"reason": f"Execution evidence missing for test case {test_case.id}"},
                    created_at=datetime.now(timezone.utc),
                ))
            return records

        for grader in self.graders:
            result: GradingResult = grader.grade(test_case, execution_data)
            record = result.to_evaluation_record(
                execution_id=exec_id,
                trajectory_id=traj_id,
                evaluator_version=self.evaluator_version,
                harness_version=harness_version,
                threshold=grader.threshold,
            )
            records.append(record)

        return records

    def evaluate_trajectory(
        self,
        trajectory: ExecutionTrajectory,
        test_case: Optional[EvalTestCase] = None,
        harness_version: Optional[str] = None,
    ) -> List[EvaluationRecord]:
        """Evaluates an ExecutionTrajectory domain object directly."""
        # Fail-closed check: if trajectory is marked incomplete or has no steps
        if trajectory.is_incomplete() and not trajectory.steps:
            return [
                EvaluationRecord(
                    evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
                    execution_id=trajectory.execution_id,
                    trajectory_id=trajectory.execution_id,
                    evaluator_version=self.evaluator_version,
                    harness_version=harness_version or trajectory.harness_version,
                    dimension=grader.dimension,
                    metric_name=grader.metric_name,
                    score=0.0,
                    threshold=grader.threshold,
                    confidence=1.0,
                    evidence_refs=[],
                    passed=False,
                    blocked=True,
                    details={"reason": "Incomplete trajectory with zero steps"},
                    created_at=datetime.now(timezone.utc),
                )
                for grader in self.graders
            ]

        execution_data = self._trajectory_to_execution_data(trajectory)
        if test_case is None:
            test_case = EvalTestCase(
                id=f"case_{trajectory.execution_id}",
                domain=trajectory.agent_type or "general",
                prompt=f"Execute {trajectory.execution_id}",
                expected_output="",
                execution_id=trajectory.execution_id,
                expected_tools=execution_data.get("used_tools", []),
            )

        return self.evaluate_case(
            test_case=test_case,
            execution_data=execution_data,
            harness_version=harness_version or trajectory.harness_version,
            trajectory_id=trajectory.execution_id,
        )

    def compare_with_baseline(
        self,
        candidate_records: Sequence[EvaluationRecord],
        baseline_records: Union[Sequence[EvaluationRecord], Dict[str, float]],
        candidate_id: str,
        baseline_id: str,
        regression_threshold: Optional[float] = None,
    ) -> BaselineComparison:
        """Compares candidate evaluation records against production baseline records.

        Calculates per-metric deltas, confidence intervals (95% CI), and flags regressions.
        """
        threshold = regression_threshold if regression_threshold is not None else self.regression_threshold
        baseline_scores_map: Dict[str, List[float]] = {}

        if isinstance(baseline_records, dict):
            for k, v in baseline_records.items():
                baseline_scores_map[k] = [float(v)]
        else:
            for rec in baseline_records:
                if not rec.blocked:
                    baseline_scores_map.setdefault(rec.metric_name, []).append(rec.score)

        candidate_scores_map: Dict[str, List[float]] = {}
        candidate_dimension_map: Dict[str, EvaluationDimension] = {}
        for rec in candidate_records:
            if not rec.blocked:
                candidate_scores_map.setdefault(rec.metric_name, []).append(rec.score)
                candidate_dimension_map[rec.metric_name] = rec.dimension

        metric_deltas: List[MetricDelta] = []
        all_candidate_scores: List[float] = []
        all_baseline_scores: List[float] = []
        confidence_intervals: Dict[str, Tuple[float, float]] = {}

        all_metrics = set(candidate_scores_map.keys()).union(set(baseline_scores_map.keys()))

        for metric in sorted(all_metrics):
            cand_list = candidate_scores_map.get(metric, [0.0])
            base_list = baseline_scores_map.get(metric, [0.8])  # Default baseline if missing

            cand_avg = sum(cand_list) / len(cand_list) if cand_list else 0.0
            base_avg = sum(base_list) / len(base_list) if base_list else 0.0
            all_candidate_scores.extend(cand_list)
            all_baseline_scores.extend(base_list)

            delta = cand_avg - base_avg
            regression = delta < -threshold

            ci: Optional[Tuple[float, float]] = None
            if len(cand_list) >= 2:
                mean = statistics.mean(cand_list)
                stdev = statistics.stdev(cand_list)
                margin = 1.96 * (stdev / math.sqrt(len(cand_list)))
                ci = (round(mean - margin, 4), round(mean + margin, 4))
                confidence_intervals[metric] = ci

            dim = candidate_dimension_map.get(metric, EvaluationDimension.TASK_SUCCESS)
            metric_deltas.append(MetricDelta(
                metric_name=metric,
                dimension=dim,
                candidate_score=round(cand_avg, 4),
                baseline_score=round(base_avg, 4),
                delta=round(delta, 4),
                regression_threshold=threshold,
                regression=regression,
                confidence_interval=ci,
            ))

        composite_candidate = (
            sum(all_candidate_scores) / len(all_candidate_scores)
            if all_candidate_scores else 0.0
        )
        composite_baseline = (
            sum(all_baseline_scores) / len(all_baseline_scores)
            if all_baseline_scores else 0.0
        )
        composite_delta = composite_candidate - composite_baseline
        regression_detected = any(md.regression for md in metric_deltas) or (composite_delta < -threshold)
        passed = (composite_candidate >= 0.7) and not regression_detected

        return BaselineComparison(
            comparison_id=f"comp_{uuid.uuid4().hex[:12]}",
            candidate_id=candidate_id,
            baseline_id=baseline_id,
            evaluator_version=self.evaluator_version,
            composite_candidate_score=round(composite_candidate, 4),
            composite_baseline_score=round(composite_baseline, 4),
            composite_delta=round(composite_delta, 4),
            regression_detected=regression_detected,
            passed=passed,
            metric_deltas=metric_deltas,
            confidence_intervals=confidence_intervals,
            created_at=datetime.now(timezone.utc),
        )
