"""Experience Store Service (Phase 8 — ban_ke_hoach_v1 §13 & §24).

Provides authoritative ingestion, lifecycle progression, state query,
and learning candidate qualification for empirical agent experiences.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Union

from windagent_core.domain.evaluation import EvaluationRecord
from windagent_core.domain.experience import Experience, ExperienceState
from windagent_core.domain.trajectory import ExecutionTrajectory
from windagent_intelligence.experience.diagnostics import ExperienceDiagnostics

logger = logging.getLogger("windagent.intelligence.experience.store")


def _gen_experience_id() -> str:
    return f"exp_{uuid.uuid4().hex[:12]}"


class ExperienceStore:
    """In-memory & domain service for managing agent experiences."""

    def __init__(self) -> None:
        self._experiences: Dict[str, Experience] = {}

    def save(self, experience: Experience) -> Experience:
        """Persists or updates an Experience instance in the store."""
        if not isinstance(experience, Experience):
            experience = Experience.model_validate(experience)
        self._experiences[experience.experience_id] = experience
        return experience

    def get(self, experience_id: str) -> Optional[Experience]:
        """Retrieves an experience by its unique identifier."""
        return self._experiences.get(experience_id)

    def create_from_trajectory(
        self,
        trajectory: ExecutionTrajectory,
        evaluations: Optional[Sequence[Union[EvaluationRecord, Dict[str, Any]]]] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        custom_experience_id: Optional[str] = None,
    ) -> Experience:
        """Projects an ExecutionTrajectory into an empirical Experience record."""
        exp_id = custom_experience_id or _gen_experience_id()

        # Extract context
        context_data = {
            "execution_id": trajectory.execution_id,
            "harness_version": trajectory.harness_version,
            "agent_type": trajectory.agent_type,
            "session_id": session_id or trajectory.agent_session_id or trajectory.conversation_id,
        }

        # Extract decisions & actions from steps
        step_decisions = []
        step_actions = []
        for step in trajectory.steps:
            step_decisions.append({
                "sequence": step.sequence,
                "kind": step.kind,
                "identifier": step.identifier,
                "selected_tool": step.details.get("tool_name", step.identifier),
            })
            step_actions.append({
                "sequence": step.sequence,
                "kind": step.kind,
                "status": step.status,
                "details": step.details,
                "provenance": step.provenance,
            })

        # Extract result
        result_data = {
            "terminal_state": trajectory.outcome.terminal_state,
            "succeeded": trajectory.outcome.succeeded,
            "error_class": trajectory.outcome.error_class,
            "error_message": trajectory.outcome.error_message,
            "has_terminal_evidence": trajectory.outcome.has_terminal_evidence,
            "total_steps": len(trajectory.steps),
        }

        # Extract artifacts
        artifacts_list = [
            {
                "artifact_id": art.artifact_id,
                "kind": art.kind,
                "sequence": art.sequence,
                "preview": art.content_redacted_preview,
                "provenance": art.provenance,
            }
            for art in trajectory.artifacts
        ]

        # Extract metrics
        metrics_dict: Dict[str, Any] = {}
        if trajectory.metrics:
            metrics_dict = {
                "total_tokens": trajectory.metrics.total_tokens,
                "prompt_tokens": trajectory.metrics.prompt_tokens,
                "completion_tokens": trajectory.metrics.completion_tokens,
                "cost_usd": trajectory.metrics.cost_usd,
                "latency_ms": trajectory.metrics.latency_ms,
                "attempt_count": trajectory.metrics.attempt_count,
                "retry_count": trajectory.metrics.retry_count,
            }

        prov_dict = provenance or {
            "harness_version": trajectory.harness_version,
            "evaluator_version": "2.0.0",
            "source": "ExecutionTrajectory",
        }

        traj_id = trajectory.source_identifiers.get("trajectory_id") if trajectory.source_identifiers else None

        exp = Experience(
            experience_id=exp_id,
            execution_id=trajectory.execution_id,
            trajectory_id=traj_id,
            parent_task_id=parent_task_id or trajectory.parent_task_id,
            session_id=session_id or trajectory.agent_session_id or trajectory.conversation_id,
            project_id=project_id,
            state=ExperienceState.RAW,
            context=context_data,
            decision={"steps": step_decisions},
            action={"steps": step_actions},
            result=result_data,
            artifacts=artifacts_list,
            metrics=metrics_dict,
            evaluator_results=[],
            hypothesis=None,
            confidence=0.0,
            provenance=prov_dict,
        )

        if evaluations:
            exp = exp.with_evaluations(evaluations)

        return self.save(exp)

    def attach_evaluations(
        self,
        experience_id: str,
        evaluations: Sequence[Union[EvaluationRecord, Dict[str, Any]]],
    ) -> Experience:
        """Attaches evaluation records to an experience and transitions to EVALUATED."""
        exp = self.get(experience_id)
        if not exp:
            raise KeyError(f"Experience {experience_id} not found.")

        updated = exp.with_evaluations(evaluations)
        return self.save(updated)

    def diagnose(
        self,
        experience_id: str,
        custom_hypothesis: Optional[str] = None,
        baseline_metrics: Optional[Dict[str, float]] = None,
    ) -> Experience:
        """Applies diagnostics and attribution to generate a diagnosed experience."""
        exp = self.get(experience_id)
        if not exp:
            raise KeyError(f"Experience {experience_id} not found.")

        diagnosed = ExperienceDiagnostics.attribute_experience(
            experience=exp,
            custom_hypothesis=custom_hypothesis,
            baseline_metrics=baseline_metrics,
        )
        return self.save(diagnosed)

    def archive(self, experience_id: str) -> Experience:
        """Transitions an experience into ARCHIVED state."""
        exp = self.get(experience_id)
        if not exp:
            raise KeyError(f"Experience {experience_id} not found.")

        archived = exp.archive()
        return self.save(archived)

    def list(
        self,
        project_id: Optional[str] = None,
        state: Optional[ExperienceState] = None,
        execution_id: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[Experience]:
        """Lists experiences matching search and filter criteria."""
        results = []
        for exp in self._experiences.values():
            if project_id and exp.project_id != project_id:
                continue
            if state and exp.state != state:
                continue
            if execution_id and exp.execution_id != execution_id:
                continue
            if exp.confidence < min_confidence:
                continue
            results.append(exp)
            if len(results) >= limit:
                break
        return results

    def list_learning_ready(
        self,
        project_id: Optional[str] = None,
        min_confidence: float = 0.6,
    ) -> List[Experience]:
        """Lists all diagnosed experiences qualified for Phase 9 Learning Candidate generation."""
        return [
            exp for exp in self._experiences.values()
            if (project_id is None or exp.project_id == project_id)
            and exp.is_learning_candidate_ready(min_confidence=min_confidence)
        ]

    def delete(self, experience_id: str) -> bool:
        """Removes an experience from store."""
        if experience_id in self._experiences:
            del self._experiences[experience_id]
            return True
        return False
