"""Evaluation Engine V2 Domain Models (Phase 7 — ban_ke_hoach_v1 §12).

Defines core evaluation contracts, records, multidimensional grading definitions,
and baseline comparison types for WindAgent's self-improvement learning substrate.

Invariants:
- All domain records are immutable (frozen).
- Fail-closed: missing execution evidence leads to blocked=True and score=0.0.
- Evidence references are mandatory for validated/promoted evaluation records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationDimension(str, Enum):
    """11 Core Evaluation Dimensions specified in ban_ke_hoach_v1 §12."""
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


class EvaluationRecord(BaseModel):
    """Immutable, typed projection of an evaluation result on an execution run.

    Follows the target data model from ban_ke_hoach_v1 §12 & §24.
    """
    evaluation_id: str = Field(description="Unique evaluation record identifier (UUID/prefixed).")
    execution_id: str = Field(description="Execution identifier (agent_run_id) evaluated.")
    trajectory_id: str = Field(description="Trajectory identifier providing audited evidence.")
    evaluator_version: str = Field(default="2.0.0", description="Version of the evaluation engine.")
    harness_version: Optional[str] = Field(default=None, description="Harness version if applicable.")
    dimension: EvaluationDimension = Field(description="Evaluation dimension under assessment.")
    metric_name: str = Field(description="Specific metric evaluated (e.g. task_completion_rate, secret_leakage).")
    score: float = Field(ge=0.0, le=1.0, description="Normalized score between 0.0 and 1.0.")
    threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum score required to pass.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Statistical confidence (0.0 to 1.0).")
    evidence_refs: List[str] = Field(default_factory=list, description="Ordered references to execution steps/artifacts.")
    passed: bool = Field(description="True if score >= threshold and not blocked.")
    blocked: bool = Field(default=False, description="True if evidence was missing or fail-closed condition met.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed diagnostic notes/metrics.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp of evaluation in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def has_evidence(self) -> bool:
        """Returns True if record has valid non-empty evidence references."""
        return len(self.evidence_refs) > 0 and not self.blocked


class MetricDelta(BaseModel):
    """Delta calculation between candidate and baseline evaluation for a specific metric."""
    metric_name: str
    dimension: EvaluationDimension
    candidate_score: float = Field(ge=0.0, le=1.0)
    baseline_score: float = Field(ge=0.0, le=1.0)
    delta: float = Field(description="candidate_score - baseline_score")
    regression_threshold: float = Field(default=0.05, description="Allowed degradation before flagging regression.")
    regression: bool = Field(description="True if delta < -regression_threshold.")
    confidence_interval: Optional[Tuple[float, float]] = Field(default=None, description="(lower, upper) at 95% CI.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class BaselineComparison(BaseModel):
    """Comprehensive comparison between a candidate run/harness and the production baseline.

    Authority for promotion gates: verifies candidate superiority or non-regression.
    """
    comparison_id: str
    candidate_id: str = Field(description="Identifier of candidate run or harness version.")
    baseline_id: str = Field(description="Identifier of production baseline run or harness version.")
    evaluator_version: str = Field(default="2.0.0")
    composite_candidate_score: float = Field(ge=0.0, le=1.0)
    composite_baseline_score: float = Field(ge=0.0, le=1.0)
    composite_delta: float
    regression_detected: bool
    passed: bool = Field(description="True if candidate met pass threshold and no regressions detected.")
    metric_deltas: List[MetricDelta] = Field(default_factory=list)
    confidence_intervals: Dict[str, Tuple[float, float]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(frozen=True, extra="forbid")


__all__ = [
    "EvaluationDimension",
    "EvaluationRecord",
    "MetricDelta",
    "BaselineComparison",
]

