"""Organizational Learning & Multi-Agent Knowledge Sharing Domain Models (Phase 14 — ban_ke_hoach_v1 §20, §21, §22, §23, §24, §25, §32, §35).

Defines:
- KnowledgeVisibilityScope: Scoped memory and knowledge visibility boundaries (PRIVATE_AGENT, TASK, SESSION, ROLE, PROJECT, GLOBAL).
- LearnedRuleState: State machine for learned rules (CANDIDATE, EXPERIMENTING, PROMOTED, DEPRECATED, ROLLED_BACK).
- LearnedRule: Immutable, evidence-backed domain entity capturing actionable recommendations, metrics, and confidence.
- AgentExecutionContext: Context identity representing an agent querying organizational knowledge.
- ConflictResolutionRecord: Audit trail documenting deterministic multi-factor conflict resolution between competing rules.
- MultiAgentAttributionRecord: Stage-separated performance attribution mapping metrics to responsible agent roles (YouTube/Studio).

Invariants (§20, §23, §35):
- All domain entities are immutable (frozen=True).
- Raw experiences are strictly scoped and NEVER auto-globalized.
- Only verified, PROMOTED learned rules can be shared across agents (PROJECT / GLOBAL).
- Competing rules matching the same domain and context undergo deterministic conflict resolution.
- Deprecated or rolled-back rules cannot be actively applied to live executions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeVisibilityScope(str, Enum):
    """Memory and knowledge visibility boundaries (§20)."""
    PRIVATE_AGENT = "private_agent"
    TASK = "task"
    SESSION = "session"
    ROLE = "role"
    PROJECT = "project"
    GLOBAL = "global"


class LearnedRuleState(str, Enum):
    """Lifecycle states of a learned rule (§23)."""
    CANDIDATE = "candidate"
    EXPERIMENTING = "experimenting"
    PROMOTED = "promoted"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class AgentExecutionContext(BaseModel):
    """Execution context and identity of an agent querying organizational knowledge (§20)."""
    agent_id: str = Field(description="Unique instance ID of the calling agent.")
    role: str = Field(description="Specialized role of the calling agent (e.g. 'ScriptAgent', 'ThumbnailAgent').")
    session_id: Optional[str] = Field(default=None, description="Active session ID if available.")
    task_id: Optional[str] = Field(default=None, description="Active task node run ID if available.")
    project_id: Optional[str] = Field(default=None, description="Active project ID if available.")
    domain: str = Field(default="youtube_studio", description="Domain of execution.")
    context_tags: Dict[str, Any] = Field(default_factory=dict, description="Contextual tags and features.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class LearnedRule(BaseModel):
    """Evidence-backed, versioned learned rule entity (§20, §23)."""
    rule_id: str = Field(description="Unique deterministic or generated identifier for the rule.")
    condition: Dict[str, Any] = Field(description="Activation trigger or context matching criteria.")
    recommendation: str = Field(description="Actionable behavioral instruction or prompt guideline.")
    domain: str = Field(default="youtube_studio", description="Application domain (e.g. 'youtube_studio', 'coding', 'research').")
    scope: KnowledgeVisibilityScope = Field(default=KnowledgeVisibilityScope.ROLE, description="Visibility scope for knowledge sharing.")
    target_role: Optional[str] = Field(default=None, description="Target agent role if scope is ROLE (e.g. 'ScriptAgent').")
    project_id: Optional[str] = Field(default=None, description="Target project ID if scope is PROJECT.")
    evidence_refs: List[str] = Field(default_factory=list, description="Provenances to supporting experiences, runs, or evaluations.")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Observed quantitative impact metrics (e.g. {'retention_30s_delta': 0.12}).")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Evaluator confidence score in [0.0, 1.0].")
    sample_size: int = Field(default=0, ge=0, description="Number of supporting observational samples.")
    harness_version: Optional[str] = Field(default=None, description="Associated harness version string if promoted into harness.")
    version: int = Field(default=1, ge=1, description="Monotonically increasing version number for this rule lineage.")
    state: LearnedRuleState = Field(default=LearnedRuleState.CANDIDATE, description="Current lifecycle state of the rule.")
    supersedes_id: Optional[str] = Field(default=None, description="Rule ID of a previous rule version superseded by this rule.")
    superseded_by: Optional[str] = Field(default=None, description="Rule ID of a newer rule that supersedes this rule.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when rule was initially generated.")
    last_validated_at: Optional[datetime] = Field(default=None, description="Timestamp of the most recent validation or experiment pass.")
    activated_at: Optional[datetime] = Field(default=None, description="Timestamp when rule was promoted to active/promoted status.")
    deprecated_at: Optional[datetime] = Field(default=None, description="Timestamp when rule was deprecated or rolled back.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible metadata payload.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    @property
    def is_active(self) -> bool:
        """Rule is actively applicable to live agent execution."""
        return self.state == LearnedRuleState.PROMOTED

    @property
    def is_promotable(self) -> bool:
        """Rule meets structural minimums to enter promotion consideration."""
        return self.state in {LearnedRuleState.CANDIDATE, LearnedRuleState.EXPERIMENTING} and self.sample_size > 0 and self.confidence >= 0.5

    def calculate_fingerprint(self) -> str:
        """Compute deterministic sha256 hash representing the rule content and condition."""
        content = {
            "domain": self.domain,
            "condition": self.condition,
            "recommendation": self.recommendation,
            "target_role": self.target_role,
            "scope": self.scope.value,
        }
        raw = json.dumps(content, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "condition": dict(self.condition),
            "recommendation": self.recommendation,
            "domain": self.domain,
            "scope": self.scope.value,
            "target_role": self.target_role,
            "project_id": self.project_id,
            "evidence_refs": list(self.evidence_refs),
            "metrics": {k: float(v) for k, v in self.metrics.items()},
            "confidence": float(self.confidence),
            "sample_size": int(self.sample_size),
            "harness_version": self.harness_version,
            "version": int(self.version),
            "state": self.state.value,
            "supersedes_id": self.supersedes_id,
            "superseded_by": self.superseded_by,
            "created_at": self.created_at.isoformat(),
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "deprecated_at": self.deprecated_at.isoformat() if self.deprecated_at else None,
            "metadata": dict(self.metadata),
        }


class ConflictResolutionRecord(BaseModel):
    """Audit record capturing the deterministic resolution between competing rules (§20)."""
    resolution_id: str = Field(description="Unique identifier for the resolution event.")
    domain: str = Field(description="Application domain of the conflict.")
    context_query: Dict[str, Any] = Field(description="Query condition or context that triggered the conflict.")
    winning_rule_id: str = Field(description="Rule ID selected as the winner.")
    competing_rule_ids: List[str] = Field(description="Rule IDs that competed in the resolution.")
    resolution_rationale: str = Field(description="Transparent, human-readable justification of the resolution outcome.")
    score_breakdown: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Detailed breakdown of multi-factor scores for each competing rule."
    )
    resolved_at: datetime = Field(default_factory=utc_now, description="Timestamp of the resolution event.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolution_id": self.resolution_id,
            "domain": self.domain,
            "context_query": dict(self.context_query),
            "winning_rule_id": self.winning_rule_id,
            "competing_rule_ids": list(self.competing_rule_ids),
            "resolution_rationale": self.resolution_rationale,
            "score_breakdown": {
                r_id: {factor: float(sc) for factor, sc in factors.items()}
                for r_id, factors in self.score_breakdown.items()
            },
            "resolved_at": self.resolved_at.isoformat(),
        }


class MultiAgentAttributionRecord(BaseModel):
    """Performance attribution mapping video/episode metrics to specialized agent roles (§21, §22)."""
    attribution_id: str = Field(description="Unique identifier for the attribution record.")
    episode_id: str = Field(description="Episode or run ID evaluated.")
    domain: str = Field(default="youtube_studio", description="Domain of evaluation.")
    metric_signals: Dict[str, float] = Field(
        description="Raw or normalized performance signals (e.g. impressions, ctr, retention_30s, retries)."
    )
    role_attributions: Dict[str, Dict[str, Any]] = Field(
        description="Mapping from agent role (e.g. 'TopicAgent', 'ThumbnailAgent', 'ScriptAgent') to diagnosis and delta."
    )
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp of attribution creation.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribution_id": self.attribution_id,
            "episode_id": self.episode_id,
            "domain": self.domain,
            "metric_signals": {k: float(v) for k, v in self.metric_signals.items()},
            "role_attributions": dict(self.role_attributions),
            "created_at": self.created_at.isoformat(),
        }

