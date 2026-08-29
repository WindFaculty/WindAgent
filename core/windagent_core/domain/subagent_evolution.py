"""Subagent Evolution Domain Models (Phase 13 — ban_ke_hoach_v1 §19, §20, §24, §25, §29, §35).

Defines the SubagentSpecVersion, SubagentCandidate, SubagentSecurityAuditResult,
SubagentEvaluationResult, SubagentPromotionDecision entities, routing and memory policies,
output contracts, security gates, and lifecycle transitions.

Invariants:
- All domain records are immutable (frozen).
- Subagents are declarative versioned configurations (SubagentSpecVersion), not hard-coded into runtime.
- Security Boundary (§19, §29):
  - Allowed tools must exist and cannot include unauthorized host execution or privilege escalation tools.
  - Allowed skills must be registered in SkillManager.
  - Memory access scopes must be bounded (GLOBAL write strictly requires human approval).
  - Recursion depth is capped (max_depth <= 5).
  - System supplements undergo prompt injection and jailbreak scanning.
- High-Risk Governance (§19, §35):
  - High-risk subagents (privileged tools, global memory write, high budget/depth) strictly require human approval (approved_by).
  - Safe, low-risk analytical/critic subagents may undergo bounded automated promotion.
- Rollback Invariant (§19, §35):
  - Post-promotion regressions trigger atomic rollback to parent/previous SubagentSpecVersion.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.agent_loop import AgentBudgetLimits


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryScope(str, Enum):
    """Memory access visibility scopes (Phase 13/14 — §20)."""
    PRIVATE_AGENT = "PRIVATE_AGENT"
    TASK = "TASK"
    SESSION = "SESSION"
    ROLE = "ROLE"
    PROJECT = "PROJECT"
    GLOBAL = "GLOBAL"


class SubagentCandidateStatus(str, Enum):
    """Lifecycle states of a proposed subagent candidate."""
    PROPOSED = "proposed"
    ELIGIBLE = "eligible"
    AUDITED = "audited"
    EVALUATED = "evaluated"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SubagentSpecStatus(str, Enum):
    """Lifecycle states of a versioned subagent specification."""
    DRAFT = "draft"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class SubagentPromotionStatus(str, Enum):
    """Lifecycle states of a subagent promotion decision."""
    PENDING_APPROVAL = "pending_approval"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class SubagentRiskLevel(str, Enum):
    """Risk assessment classification for subagent specifications."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ModelRoutingPolicy(BaseModel):
    """Model routing and generation parameters for specialized subagents (§19)."""
    model_tier: str = Field(default="flash", description="Model tier: flash, flash_lite, pro, inherit.")
    provider: Optional[str] = Field(default=None, description="Preferred provider vendor or endpoint.")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature.")
    fallback_models: List[str] = Field(default_factory=list, description="Fallback model names if primary fails.")
    max_context_tokens: Optional[int] = Field(default=None, ge=1, description="Context window cap.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class MemoryAccessPolicy(BaseModel):
    """Declarative memory visibility and access boundaries for subagents (§19, §20)."""
    allowed_read_scopes: List[MemoryScope] = Field(
        default_factory=lambda: [MemoryScope.PRIVATE_AGENT, MemoryScope.TASK, MemoryScope.SESSION],
        description="Memory scopes this subagent may read.",
    )
    allowed_write_scopes: List[MemoryScope] = Field(
        default_factory=lambda: [MemoryScope.PRIVATE_AGENT, MemoryScope.TASK],
        description="Memory scopes this subagent may write.",
    )
    max_memory_items: int = Field(default=20, ge=1, le=100, description="Bounded memory item retrieval limit.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    @property
    def has_global_write(self) -> bool:
        return MemoryScope.GLOBAL in self.allowed_write_scopes or MemoryScope.PROJECT in self.allowed_write_scopes


class SubagentOutputContract(BaseModel):
    """Structured output expectations and validation schemas for specialized subagents (§19)."""
    schema_type: str = Field(default="json", description="Expected output format type (json, markdown, artifact).")
    required_fields: List[str] = Field(default_factory=list, description="Required keys in output payload.")
    json_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema for structural validation.")
    required_artifact_types: List[str] = Field(default_factory=list, description="Artifact types required on completion.")
    strict_validation: bool = Field(default=True, description="Whether schema validation must fail on unknown fields.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class SubagentSecurityAuditResult(BaseModel):
    """Structured security audit report for a proposed subagent candidate (§19, §29)."""
    passed: bool = Field(default=False, description="Overall security audit verdict.")
    tool_permission_passed: bool = Field(default=False, description="Tools exist and within authorized boundaries.")
    skill_permission_passed: bool = Field(default=False, description="Skills exist and within authorized boundaries.")
    memory_scope_passed: bool = Field(default=False, description="Memory scopes comply with security policy.")
    prompt_safety_passed: bool = Field(default=False, description="Prompt supplement free of prompt injection.")
    budget_ceiling_passed: bool = Field(default=False, description="Budget limits within organizational thresholds.")
    depth_ceiling_passed: bool = Field(default=False, description="Recursion depth <= 5.")
    violations: List[str] = Field(default_factory=list, description="List of detected policy violations.")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Computed risk score in [0.0, 1.0].")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic payload.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    @property
    def is_safe(self) -> bool:
        return (
            self.passed
            and self.tool_permission_passed
            and self.skill_permission_passed
            and self.memory_scope_passed
            and self.prompt_safety_passed
            and self.budget_ceiling_passed
            and self.depth_ceiling_passed
            and len(self.violations) == 0
        )


class SubagentEvaluationResult(BaseModel):
    """Structured benchmark and contract validation evaluation metrics (§19, §27)."""
    evaluation_id: str = Field(description="Unique evaluation identifier.")
    subagent_candidate_id: str = Field(description="Associated subagent candidate identifier.")
    benchmark_passed: bool = Field(default=False, description="Whether task benchmark succeeded.")
    task_suite_passed: bool = Field(default=False, description="Whether test task suite passed 100%.")
    tasks_run: int = Field(default=0, ge=0, description="Total benchmark tasks executed.")
    tasks_passed: int = Field(default=0, ge=0, description="Tasks passed.")
    tasks_failed: int = Field(default=0, ge=0, description="Tasks failed.")
    accuracy_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Task success score.")
    safety_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Safety compliance score (must be >= 0.95).")
    contract_compliance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Output contract schema conformance score (must be >= 0.90)."
    )
    token_efficiency_score: float = Field(default=1.0, ge=0.0, description="Token consumption ratio vs baseline.")
    cost_delta_usd: float = Field(default=0.0, description="Estimated cost delta per task in USD.")
    latency_delta_ms: float = Field(default=0.0, description="Execution latency delta in milliseconds.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed task outputs and errors.")

    model_config = ConfigDict(frozen=True, extra="forbid")


class SubagentCandidate(BaseModel):
    """Immutable domain entity representing a proposed subagent mutation or new subagent (§19)."""
    candidate_id: str = Field(description="Unique subagent candidate ID (e.g. 'subcand_...').")
    role: str = Field(description="Target specialized subagent role name (e.g. 'MarketResearchAgent').")
    proposed_spec: Dict[str, Any] = Field(description="Proposed SubagentSpec dictionary payload.")
    reasoning_summary: str = Field(description="Hypothesis and justification for this specialized subagent.")
    supporting_experiences: List[str] = Field(default_factory=list, description="Associated experience IDs.")
    status: SubagentCandidateStatus = Field(
        default=SubagentCandidateStatus.PROPOSED, description="Current candidate status."
    )
    risk_level: SubagentRiskLevel = Field(default=SubagentRiskLevel.LOW, description="Assessed risk level.")
    is_high_risk: bool = Field(default=False, description="Whether candidate requires human review.")
    security_audit: Optional[SubagentSecurityAuditResult] = Field(default=None, description="Security audit findings.")
    evaluation: Optional[SubagentEvaluationResult] = Field(default=None, description="Benchmark evaluation findings.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extension metadata.")
    created_at: datetime = Field(default_factory=utc_now, description="Proposal timestamp.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def compute_spec_hash(self) -> str:
        """Computes SHA-256 hash of proposed spec payload."""
        hasher = hashlib.sha256()
        payload = {"role": self.role, "spec": self.proposed_spec}
        spec_str = json.dumps(payload, sort_keys=True, default=str)
        hasher.update(spec_str.encode("utf-8"))
        return hasher.hexdigest()

    def with_audit(self, audit: SubagentSecurityAuditResult) -> SubagentCandidate:
        """Transitions candidate to AUDITED state or REJECTED if audit failed."""
        new_status = SubagentCandidateStatus.AUDITED if audit.is_safe else SubagentCandidateStatus.REJECTED
        return self.model_copy(
            update={
                "security_audit": audit,
                "status": new_status,
                "updated_at": utc_now(),
            }
        )

    def with_evaluation(self, evaluation: SubagentEvaluationResult) -> SubagentCandidate:
        """Transitions candidate to EVALUATED state or REJECTED if benchmark failed."""
        passed = (
            evaluation.benchmark_passed
            and evaluation.task_suite_passed
            and evaluation.safety_score >= 0.95
            and evaluation.contract_compliance_score >= 0.90
        )
        new_status = SubagentCandidateStatus.EVALUATED if passed else SubagentCandidateStatus.REJECTED
        return self.model_copy(
            update={
                "evaluation": evaluation,
                "status": new_status,
                "updated_at": utc_now(),
            }
        )


class SubagentSpecVersion(BaseModel):
    """Immutable versioned subagent configuration deployed to runtime registry (§19, §24)."""
    id: str = Field(description="Unique spec version ID (e.g. 'subspec_...').")
    role: str = Field(description="Specialized subagent role name (e.g. 'ScriptAgent').")
    version: str = Field(description="Semver version string (e.g. '1.0.0').")
    parent_version: Optional[str] = Field(default=None, description="Previous version string if an evolution.")
    objective: str = Field(description="Primary objective and responsibility statement.")
    system_supplement: str = Field(default="", description="Specialized system prompt instructions.")
    allowed_tools: List[str] = Field(default_factory=list, description="Whitelist of allowed tool names.")
    allowed_skills: List[str] = Field(default_factory=list, description="Whitelist of allowed skill IDs.")
    model_routing_policy: ModelRoutingPolicy = Field(
        default_factory=ModelRoutingPolicy, description="Model routing policy."
    )
    memory_access: MemoryAccessPolicy = Field(
        default_factory=MemoryAccessPolicy, description="Memory visibility and access boundaries."
    )
    max_budget: AgentBudgetLimits = Field(
        default_factory=AgentBudgetLimits, description="Durable budget bounds."
    )
    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum recursive delegation depth (1 to 5).")
    output_contract: SubagentOutputContract = Field(
        default_factory=SubagentOutputContract, description="Structured output schema."
    )
    status: SubagentSpecStatus = Field(default=SubagentSpecStatus.ACTIVE, description="Current spec status.")
    risk_level: SubagentRiskLevel = Field(default=SubagentRiskLevel.LOW, description="Risk level.")
    spec_hash: Optional[str] = Field(default=None, description="SHA-256 checksum of spec content.")
    promoted_from_candidate_id: Optional[str] = Field(default=None, description="Candidate ID that originated this.")
    security_audit_id: Optional[str] = Field(default=None, description="Audit report reference.")
    evaluation_id: Optional[str] = Field(default=None, description="Evaluation report reference.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata tags.")
    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp.")
    activated_at: Optional[datetime] = Field(default=None, description="Activation timestamp.")
    deprecated_at: Optional[datetime] = Field(default=None, description="Deprecation timestamp.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def compute_spec_hash(self) -> str:
        """Computes SHA-256 hash of this versioned specification."""
        hasher = hashlib.sha256()
        payload = {
            "role": self.role,
            "version": self.version,
            "objective": self.objective,
            "system_supplement": self.system_supplement,
            "allowed_tools": sorted(self.allowed_tools),
            "allowed_skills": sorted(self.allowed_skills),
            "model_routing_policy": self.model_routing_policy.model_dump(),
            "memory_access": self.memory_access.model_dump(),
            "max_budget": self.max_budget.model_dump(),
            "max_depth": self.max_depth,
            "output_contract": self.output_contract.model_dump(),
        }
        spec_str = json.dumps(payload, sort_keys=True, default=str)
        hasher.update(spec_str.encode("utf-8"))
        return hasher.hexdigest()


class SubagentPromotionDecision(BaseModel):
    """Immutable audit record documenting promotion, approval, or rollback of a subagent spec (§19, §35)."""
    id: str = Field(description="Unique promotion decision ID (e.g. 'subprom_...').")
    candidate_id: str = Field(description="Associated candidate ID.")
    role: str = Field(description="Subagent role name.")
    source_version: Optional[str] = Field(default=None, description="Previous version replaced by this.")
    target_version: str = Field(description="Target version deployed.")
    status: SubagentPromotionStatus = Field(
        default=SubagentPromotionStatus.PENDING_APPROVAL, description="Promotion status."
    )
    security_audit_passed: bool = Field(default=False, description="Whether security gate passed.")
    evaluation_passed: bool = Field(default=False, description="Whether benchmark gate passed.")
    requires_human_approval: bool = Field(default=False, description="Whether human review was mandatory.")
    approved_by: Optional[str] = Field(default=None, description="User/authority ID who approved promotion.")
    approved_at: Optional[datetime] = Field(default=None, description="Approval timestamp.")
    rejection_reason: Optional[str] = Field(default=None, description="Rejection reason if rejected.")
    decision_rationale: str = Field(default="", description="Summary explanation for decision.")
    created_at: datetime = Field(default_factory=utc_now, description="Record creation timestamp.")
    updated_at: datetime = Field(default_factory=utc_now, description="Record last update timestamp.")

    model_config = ConfigDict(frozen=True, extra="forbid")

