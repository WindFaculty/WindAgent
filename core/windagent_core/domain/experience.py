"""Experience Store Domain Models (Phase 8 — ban_ke_hoach_v1 §13 & §24).

Defines the core Experience entity, lifecycle states, transition helpers, and invariants.
Experience bridges observational execution telemetry and Phase 7 evaluation results
into empirical learning data without conflating experiences with promoted rules or policies.

Invariants:
- All domain records are immutable (frozen).
- Experience != MemoryFact != LearnedRule != Skill != Policy.
- Lifecycle: RAW -> EVALUATED -> DIAGNOSED -> ARCHIVED.
- Validated diagnosis requires confidence in [0.0, 1.0] and non-empty evaluation evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExperienceState(str, Enum):
    """Lifecycle states for empirical execution experiences."""
    RAW = "raw"
    EVALUATED = "evaluated"
    DIAGNOSED = "diagnosed"
    ARCHIVED = "archived"


class Experience(BaseModel):
    """Immutable domain entity representing an empirical agent run experience.

    Captures the full execution loop:
    context -> decision -> action -> result -> artifacts -> metrics -> evaluations -> diagnosis.
    """
    experience_id: str = Field(description="Unique experience identifier (UUID/prefixed 'exp_').")
    execution_id: str = Field(description="Associated agent execution identifier (agent_run_id).")
    trajectory_id: Optional[str] = Field(default=None, description="Linked execution trajectory identifier.")
    parent_task_id: Optional[str] = Field(default=None, description="Parent task identifier if decomposed.")
    session_id: Optional[str] = Field(default=None, description="Chat session or thread identifier.")
    project_id: Optional[str] = Field(default=None, description="Project/Workspace identifier.")
    state: ExperienceState = Field(default=ExperienceState.RAW, description="Current lifecycle state.")

    # Execution telemetry decomposition
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution context (problem statement, prompt inputs, system state).")
    decision: Dict[str, Any] = Field(default_factory=dict, description="Decision trace (plan, chosen tools, routing rationale).")
    action: Dict[str, Any] = Field(default_factory=dict, description="Actions executed (tool calls, arguments, subagent delegations).")
    result: Dict[str, Any] = Field(default_factory=dict, description="Execution outcome (terminal status, final response, errors).")
    artifacts: List[Dict[str, Any]] = Field(default_factory=list, description="Artifact references and metadata produced.")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics (tokens, cost_usd, latency_ms, retries).")

    # Evaluator & diagnostic enrichment
    evaluator_results: List[Dict[str, Any]] = Field(default_factory=list, description="Attached EvaluationRecord outputs across dimensions.")
    hypothesis: Optional[str] = Field(default=None, description="Diagnosed learning hypothesis (e.g. pattern attribution).")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Statistical confidence in experience/attribution.")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Execution provenance (harness_version, model, worker_id).")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last transition timestamp in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def with_evaluations(
        self,
        eval_records: Sequence[Union[Dict[str, Any], Any]],
    ) -> Experience:
        """Transitions experience to EVALUATED state with evaluation records."""
        serialized_evals: List[Dict[str, Any]] = []
        for rec in eval_records:
            if hasattr(rec, "model_dump"):
                serialized_evals.append(rec.model_dump(mode="json"))
            elif isinstance(rec, dict):
                serialized_evals.append(rec)
            else:
                serialized_evals.append(dict(rec))

        return self.model_copy(
            update={
                "evaluator_results": serialized_evals,
                "state": ExperienceState.EVALUATED,
                "updated_at": utc_now(),
            }
        )

    def with_diagnosis(
        self,
        hypothesis: str,
        confidence: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> Experience:
        """Transitions experience to DIAGNOSED state with hypothesis and confidence."""
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {confidence}")
        if not hypothesis or not hypothesis.strip():
            raise ValueError("Diagnosis hypothesis cannot be empty.")

        updated_metrics = dict(self.metrics)
        if details:
            updated_metrics["diagnosis_details"] = details

        return self.model_copy(
            update={
                "hypothesis": hypothesis.strip(),
                "confidence": confidence,
                "metrics": updated_metrics,
                "state": ExperienceState.DIAGNOSED,
                "updated_at": utc_now(),
            }
        )

    def archive(self) -> Experience:
        """Transitions experience to ARCHIVED state."""
        return self.model_copy(
            update={
                "state": ExperienceState.ARCHIVED,
                "updated_at": utc_now(),
            }
        )

    def is_learning_candidate_ready(self, min_confidence: float = 0.6) -> bool:
        """Validates if experience is qualified for LearningCandidate generation in Phase 9."""
        return (
            self.state == ExperienceState.DIAGNOSED
            and self.confidence >= min_confidence
            and bool(self.hypothesis)
            and len(self.evaluator_results) > 0
        )

    def assert_empirical_experience(self) -> bool:
        """Asserts domain invariant: Experience is empirical observation, not a promoted rule."""
        return True

