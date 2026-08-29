"""ExecutionTrajectory domain types (Phase 1 — ban_ke_hoach_v1 §6).

Deterministic, typed projection of one durable execution (``agent_run_id`` as
``execution_id``) from authoritative PostgreSQL/SQL records.

All types are immutable (frozen) and serializable via ``model_dump`` / JSON.
No prompt/completion bodies, credentials, or provider headers are stored.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrajectoryStep(BaseModel):
    """One ordered provenance step within an execution.

    Kinds: ``agent_turn``, ``conversation_event``, ``tool_execution``,
    ``partial_stream``.
    """

    sequence: int = Field(description="Deterministic order index (0-based).")
    kind: str = Field(description="Step kind discriminator.")
    identifier: str = Field(description="Source identifier (turn_id / event_id / tool_execution_id / partial_artifact_id).")
    created_at: str | None = Field(default=None, description="ISO timestamp from durable record, if present.")
    finished_at: str | None = Field(default=None, description="ISO timestamp for completion, if present.")
    status: str | None = Field(default=None)
    details: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict, description="Source table/ids for audit.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class TrajectoryArtifactRef(BaseModel):
    """Durable artifact reference linked to the execution."""

    artifact_id: str
    kind: str = Field(description="Artifact kind: partial_stream | facts | tool_result")
    sequence: int | None = Field(default=None)
    audit_only: bool = Field(default=False)
    created_at: str | None = Field(default=None)
    content_redacted_preview: str | None = Field(default=None)
    failure_reason: str | None = Field(default=None)
    provenance: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid")


class TrajectoryMetric(BaseModel):
    """Token / cost / latency metrics when durably present."""

    prompt_tokens: int | None = Field(default=None)
    completion_tokens: int | None = Field(default=None)
    total_tokens: int | None = Field(default=None)
    latency_ms: int | None = Field(default=None, description="Wall latency from durable timestamps only; None when unavailable.")
    cost_usd: float | None = Field(default=None, description="Present only when a durable cost ledger exists; else None.")
    attempt_count: int | None = Field(default=None)
    retry_count: int | None = Field(default=None)
    model_config = ConfigDict(frozen=True, extra="forbid")


class TrajectoryOutcome(BaseModel):
    """Terminal outcome / evaluation evidence for the execution."""

    terminal_state: str | None = Field(default=None, description="AgentRun / TaskNodeRun terminal state, if any.")
    succeeded: bool | None = Field(default=None)
    error_class: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    evaluation: dict[str, Any] | None = Field(default=None)
    has_terminal_evidence: bool = Field(default=False)

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExecutionTrajectory(BaseModel):
    """Typed, serializable projection of one durable execution."""

    execution_id: str = Field(description="Public execution identity (= agent_run_id).")
    conversation_id: str | None = Field(default=None)
    parent_task_id: str | None = Field(default=None)
    plan_version_id: str | None = Field(default=None)
    node_id: str | None = Field(default=None)
    task_node_run_id: str | None = Field(default=None)
    agent_instance_id: str | None = Field(default=None)
    agent_session_id: str | None = Field(default=None)
    agent_run_id: str | None = Field(default=None)
    agent_type: str | None = Field(default=None)
    harness_version: str | None = Field(default=None)
    steps: tuple[TrajectoryStep, ...] = Field(default_factory=tuple)
    artifacts: tuple[TrajectoryArtifactRef, ...] = Field(default_factory=tuple)
    metrics: TrajectoryMetric | None = Field(default=None)
    outcome: TrajectoryOutcome = Field(default_factory=TrajectoryOutcome)
    completeness: str = Field(description="COMPLETE | INCOMPLETE")
    incomplete_reasons: tuple[str, ...] = Field(default_factory=tuple)
    source_identifiers: dict[str, str | None] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid")

    def is_complete(self) -> bool:
        return self.completeness == "COMPLETE"

    def is_incomplete(self) -> bool:
        return self.completeness == "INCOMPLETE"


__all__ = [
    "TrajectoryStep",
    "TrajectoryArtifactRef",
    "TrajectoryMetric",
    "TrajectoryOutcome",
    "ExecutionTrajectory",
]
