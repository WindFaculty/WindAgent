"""Candidate Learning & Rule Domain Models (Phase 9 — ban_ke_hoach_v1 §14, §23, §24).

Defines the core LearningCandidate and LearnedRule entities, lifecycle states,
invariants, and transition helpers.

Invariants:
- All domain records are immutable (frozen).
- Experience != MemoryFact != LearningCandidate != LearnedRule != Skill != Policy.
- Lifecycle: PROPOSED -> ELIGIBLE -> EXPERIMENTING -> PROMOTED (or REJECTED / EXPIRED).
- Hard rule: 1 failure -> reflection -> candidate (PROPOSED with sample_size=1).
- LLMs/Generators CANNOT self-promote candidates directly to harness or prompt modifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CandidateKind(str, Enum):
    """Types of learning mutations that can be proposed."""
    PROMPT_RULE = "prompt_rule"
    MEMORY = "memory"
    SKILL = "skill"
    SUBAGENT_SPEC = "subagent_spec"
    ROUTING_POLICY = "routing_policy"


class CandidateStatus(str, Enum):
    """Lifecycle states of a learning candidate."""
    PROPOSED = "proposed"
    ELIGIBLE = "eligible"
    EXPERIMENTING = "experimenting"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CandidateRiskLevel(str, Enum):
    """Risk assessment classification for candidate mutations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CandidateScope(str, Enum):
    """Scope of candidate impact across the agent platform."""
    LOCAL = "local"
    PROJECT = "project"
    GLOBAL = "global"


class LearnedRuleState(str, Enum):
    """Lifecycle states of a structured learned rule."""
    CANDIDATE = "candidate"
    EXPERIMENTING = "experimenting"
    PROMOTED = "promoted"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class LearningCandidate(BaseModel):
    """Immutable domain entity representing a proposed learning mutation.

    Generated from empirical experiences or reflection, candidate learning
    must pass sample size and confidence eligibility checks before entering
    experimentation and eventual promotion.
    """
    candidate_id: str = Field(description="Unique candidate identifier (e.g. 'cand_...').")
    kind: CandidateKind = Field(description="Kind of proposed learning mutation.")
    condition: str = Field(description="Context trigger condition or domain match criteria.")
    proposed_change: Dict[str, Any] = Field(description="Structured change payload (rule text, params, diffs).")
    reasoning_summary: str = Field(description="Diagnostic rationale and hypothesis explaining the proposed change.")

    supporting_experiences: List[str] = Field(
        default_factory=list,
        description="IDs of experiences providing positive evidence for this candidate.",
    )
    counter_evidence: List[str] = Field(
        default_factory=list,
        description="IDs of experiences providing conflicting or negative evidence.",
    )
    sample_size: int = Field(
        default=1,
        ge=1,
        description="Total empirical sample size observed for this pattern.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Statistical confidence score in [0.0, 1.0].",
    )
    scope: CandidateScope = Field(
        default=CandidateScope.PROJECT,
        description="Scope of application (local, project, global).",
    )
    risk_level: CandidateRiskLevel = Field(
        default=CandidateRiskLevel.MEDIUM,
        description="Assessed risk level of the proposed modification.",
    )
    status: CandidateStatus = Field(
        default=CandidateStatus.PROPOSED,
        description="Current lifecycle status.",
    )

    project_id: Optional[str] = Field(default=None, description="Associated project ID if scoped to project.")
    domain: Optional[str] = Field(default=None, description="Domain classification (e.g. 'youtube', 'coding').")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata.")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last updated timestamp in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def mark_eligible(
        self,
        min_sample_size: int = 3,
        min_confidence: float = 0.65,
        max_counter_ratio: float = 0.35,
    ) -> LearningCandidate:
        """Transitions candidate to ELIGIBLE state after validating eligibility criteria."""
        if self.status not in (CandidateStatus.PROPOSED, CandidateStatus.ELIGIBLE):
            raise ValueError(f"Cannot mark candidate {self.candidate_id} as ELIGIBLE from status {self.status.value}")

        if self.sample_size < min_sample_size:
            raise ValueError(
                f"Candidate {self.candidate_id} sample size ({self.sample_size}) "
                f"is below required threshold ({min_sample_size})"
            )

        if self.confidence < min_confidence:
            raise ValueError(
                f"Candidate {self.candidate_id} confidence ({self.confidence:.2f}) "
                f"is below required threshold ({min_confidence:.2f})"
            )

        total_evidence = len(self.supporting_experiences) + len(self.counter_evidence)
        if total_evidence > 0:
            counter_ratio = len(self.counter_evidence) / total_evidence
            if counter_ratio > max_counter_ratio:
                raise ValueError(
                    f"Candidate {self.candidate_id} counter-evidence ratio ({counter_ratio:.2f}) "
                    f"exceeds tolerance ({max_counter_ratio:.2f})"
                )

        return self.model_copy(
            update={
                "status": CandidateStatus.ELIGIBLE,
                "updated_at": utc_now(),
            }
        )

    def start_experiment(self) -> LearningCandidate:
        """Transitions candidate from ELIGIBLE to EXPERIMENTING state."""
        if self.status != CandidateStatus.ELIGIBLE:
            raise ValueError(
                f"Candidate {self.candidate_id} must be in ELIGIBLE state to enter EXPERIMENTING, "
                f"currently {self.status.value}"
            )

        return self.model_copy(
            update={
                "status": CandidateStatus.EXPERIMENTING,
                "updated_at": utc_now(),
            }
        )

    def reject(self, reason: str) -> LearningCandidate:
        """Transitions candidate to REJECTED state with rejection reason recorded in metadata."""
        if not reason or not reason.strip():
            raise ValueError("Rejection reason cannot be empty.")

        updated_meta = dict(self.metadata)
        updated_meta["rejection_reason"] = reason.strip()
        updated_meta["rejected_at"] = utc_now().isoformat()

        return self.model_copy(
            update={
                "status": CandidateStatus.REJECTED,
                "metadata": updated_meta,
                "updated_at": utc_now(),
            }
        )

    def expire(self) -> LearningCandidate:
        """Transitions candidate to EXPIRED state."""
        return self.model_copy(
            update={
                "status": CandidateStatus.EXPIRED,
                "updated_at": utc_now(),
            }
        )

    def with_evidence(
        self,
        supporting_exp_id: str,
        new_confidence: Optional[float] = None,
    ) -> LearningCandidate:
        """Adds positive supporting experience, increments sample size, and updates confidence."""
        if not supporting_exp_id or not supporting_exp_id.strip():
            raise ValueError("Supporting experience ID cannot be empty.")

        new_supporting = list(self.supporting_experiences)
        if supporting_exp_id not in new_supporting:
            new_supporting.append(supporting_exp_id)

        new_sample_size = max(self.sample_size + 1, len(new_supporting))
        calculated_conf = new_confidence if new_confidence is not None else min(1.0, self.confidence + 0.05)

        return self.model_copy(
            update={
                "supporting_experiences": new_supporting,
                "sample_size": new_sample_size,
                "confidence": round(calculated_conf, 4),
                "updated_at": utc_now(),
            }
        )

    def with_counter_evidence(
        self,
        counter_exp_id: str,
        penalty: float = 0.15,
    ) -> LearningCandidate:
        """Adds conflicting counter-evidence and applies a downward confidence penalty."""
        if not counter_exp_id or not counter_exp_id.strip():
            raise ValueError("Counter evidence experience ID cannot be empty.")

        new_counter = list(self.counter_evidence)
        if counter_exp_id not in new_counter:
            new_counter.append(counter_exp_id)

        new_conf = max(0.0, self.confidence - penalty)
        new_sample_size = self.sample_size + 1

        return self.model_copy(
            update={
                "counter_evidence": new_counter,
                "sample_size": new_sample_size,
                "confidence": round(new_conf, 4),
                "updated_at": utc_now(),
            }
        )

    def assert_candidate_invariants(self) -> bool:
        """Asserts domain invariants for learning candidates."""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Candidate confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.sample_size < 1:
            raise ValueError(f"Candidate sample size must be >= 1, got {self.sample_size}")
        if not self.condition or not self.condition.strip():
            raise ValueError("Candidate condition cannot be empty.")
        if not self.reasoning_summary or not self.reasoning_summary.strip():
            raise ValueError("Candidate reasoning summary cannot be empty.")
        return True


class LearnedRule(BaseModel):
    """Immutable domain entity representing a structured rule derived from candidate learning.

    Tracks condition, recommendation, domain attribution, versioning, and validation status.
    """
    rule_id: str = Field(description="Unique rule identifier (e.g. 'rule_...').")
    condition: str = Field(description="Activation condition / context when rule applies.")
    recommendation: str = Field(description="Recommended action, prompt supplement, or behavior.")
    domain: str = Field(default="general", description="Domain classification (e.g. 'youtube', 'coding').")
    scope: CandidateScope = Field(default=CandidateScope.PROJECT, description="Scope of application.")

    evidence_refs: List[str] = Field(default_factory=list, description="IDs of experiences and candidates supporting rule.")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Performance metrics and attribution data.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Statistical confidence score.")
    sample_size: int = Field(default=1, ge=1, description="Number of supporting evidence instances.")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    last_validated_at: Optional[datetime] = Field(default=None, description="Timestamp of latest validation run.")
    harness_version: Optional[str] = Field(default=None, description="Harness version where rule was introduced.")
    version: int = Field(default=1, ge=1, description="Rule revision version.")
    state: LearnedRuleState = Field(default=LearnedRuleState.CANDIDATE, description="Lifecycle state of the rule.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def deprecate(self, reason: Optional[str] = None) -> LearnedRule:
        """Transitions rule to DEPRECATED state."""
        updated_metrics = dict(self.metrics)
        if reason:
            updated_metrics["deprecation_reason"] = reason

        return self.model_copy(
            update={
                "state": LearnedRuleState.DEPRECATED,
                "metrics": updated_metrics,
            }
        )

    def rollback(self, reason: str) -> LearnedRule:
        """Transitions rule to ROLLED_BACK state due to detected regression."""
        updated_metrics = dict(self.metrics)
        updated_metrics["rollback_reason"] = reason
        updated_metrics["rolled_back_at"] = utc_now().isoformat()

        return self.model_copy(
            update={
                "state": LearnedRuleState.ROLLED_BACK,
                "metrics": updated_metrics,
            }
        )

