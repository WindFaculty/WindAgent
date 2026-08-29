"""Organizational Learning & Multi-Agent Knowledge Sharing Service (Phase 14 — ban_ke_hoach_v1 §20, §21, §22, §23, §24, §25, §32, §35).

Coordinates:
1. Knowledge Visibility Enforcement: Evaluates scoped access (PRIVATE_AGENT, TASK, SESSION, ROLE, PROJECT, GLOBAL).
2. Raw Experience Containment: Ensures raw experiences are NEVER auto-globalized; only PROMOTED rules cross boundaries.
3. Multi-Agent Rule Query & Conflict Resolution: Resolves competing rules using RuleConflictResolver.
4. Rule Lifecycle Management: Propose, promote, deprecate, and rollback learned rules.
5. YouTube / Studio Multi-Agent Metric Attribution: Stage-separated metric attribution to specialized agent roles.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from windagent_core.contracts.repositories.organizational_learning_repository import (
    OrganizationalLearningRepositoryProtocol,
)
from windagent_core.domain.organizational_learning import (
    AgentExecutionContext,
    KnowledgeVisibilityScope,
    LearnedRule,
    LearnedRuleState,
    MultiAgentAttributionRecord,
    utc_now,
)
from windagent_core.errors.exceptions import (
    NotFoundError,
    ValidationError as CoreValidationError,
)
from windagent_orchestration.learning.conflict_resolver import RuleConflictResolver

# YouTube / Studio Metric Attribution Mapping (§22)
YOUTUBE_SIGNAL_ROLE_MAP: Dict[str, Dict[str, Any]] = {
    "impressions": {
        "role": "TopicAgent",
        "dimension": "Topic / Market Selection",
        "description": "Packaging & topic cluster market reach",
    },
    "ctr": {
        "role": "ThumbnailAgent",
        "dimension": "Thumbnail / Title Packaging",
        "description": "Visual contrast & title click-through appeal",
    },
    "retention_30s": {
        "role": "ScriptAgent",
        "dimension": "Hook / Intro Pacing",
        "description": "Opening hook engagement and 0-30s drop-off reduction",
    },
    "retention_dips": {
        "role": "SceneAgent",
        "dimension": "Scene Pacing / Visuals",
        "description": "Mid-video scene density and visual transitions",
    },
    "avg_view_duration": {
        "role": "PacingAgent",
        "dimension": "Structure / Pacing",
        "description": "Content pacing and section length balance",
    },
    "completion_rate": {
        "role": "StoryAgent",
        "dimension": "Narrative Arc",
        "description": "Climax payoff and story architecture satisfaction",
    },
    "comments": {
        "role": "AudienceAgent",
        "dimension": "Audience Model",
        "description": "Discussion prompt and community value proposition",
    },
    "production_retries": {
        "role": "ProductionAgent",
        "dimension": "Production Workflow",
        "description": "Render pipeline stability and asset generation efficiency",
    },
    "cost_usd": {
        "role": "ProductionAgent",
        "dimension": "Cost Efficiency",
        "description": "Execution budget adherence and model routing efficiency",
    },
}


class OrganizationalLearningService:
    """Service governing multi-agent knowledge sharing, visibility gates, and conflict resolution."""

    def __init__(
        self,
        repository: OrganizationalLearningRepositoryProtocol,
        conflict_resolver: Optional[RuleConflictResolver] = None,
    ) -> None:
        self.repository = repository
        self.conflict_resolver = conflict_resolver or RuleConflictResolver()

    # -------------------------------------------------------------------------
    # Visibility Boundary & Scoping Gate (§20)
    # -------------------------------------------------------------------------

    def is_rule_visible_to_agent(
        self,
        rule: LearnedRule,
        agent_context: AgentExecutionContext,
    ) -> bool:
        """Enforces multi-agent memory and knowledge visibility boundaries.

        Rules:
        - Only PROMOTED rules can be shared globally or across project.
        - PRIVATE_AGENT: Only visible to creating agent_id.
        - TASK: Only visible within same task_id.
        - SESSION: Only visible within same session_id.
        - ROLE: Visible only to agents with matching role.
        - PROJECT: Visible to all agents within same project_id.
        - GLOBAL: Visible to all agents in organization (must be PROMOTED).
        """
        # Invariant: Non-promoted candidate rules cannot cross private/task boundary
        if not rule.is_active and rule.scope in {KnowledgeVisibilityScope.GLOBAL, KnowledgeVisibilityScope.PROJECT}:
            # Candidate rules remain local to proposing context
            creator_agent = rule.metadata.get("agent_id")
            if creator_agent and creator_agent != agent_context.agent_id:
                return False

        if rule.scope == KnowledgeVisibilityScope.GLOBAL:
            return True

        if rule.scope == KnowledgeVisibilityScope.PROJECT:
            if not agent_context.project_id or not rule.project_id:
                return False
            return agent_context.project_id == rule.project_id

        if rule.scope == KnowledgeVisibilityScope.ROLE:
            if not rule.target_role:
                return True
            return agent_context.role == rule.target_role

        if rule.scope == KnowledgeVisibilityScope.SESSION:
            target_session = rule.metadata.get("session_id")
            return bool(agent_context.session_id and target_session and agent_context.session_id == target_session)

        if rule.scope == KnowledgeVisibilityScope.TASK:
            target_task = rule.metadata.get("task_id")
            return bool(agent_context.task_id and target_task and agent_context.task_id == target_task)

        if rule.scope == KnowledgeVisibilityScope.PRIVATE_AGENT:
            target_agent = rule.metadata.get("agent_id")
            return bool(agent_context.agent_id and target_agent and agent_context.agent_id == target_agent)

        return False

    # -------------------------------------------------------------------------
    # Rule Query & Conflict Resolution Workflow (§20)
    # -------------------------------------------------------------------------

    async def query_applicable_rules(
        self,
        agent_context: AgentExecutionContext,
        active_harness_version: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[LearnedRule]:
        """Queries, filters, and conflict-resolves all active rules applicable to the agent context."""
        # 1. Fetch active rules for the given domain
        all_active_rules = await self.repository.query_active_rules(
            domain=agent_context.domain,
            target_role=agent_context.role,
            project_id=agent_context.project_id,
        )

        # 2. Filter by visibility policy
        visible_rules = [
            rule for rule in all_active_rules
            if self.is_rule_visible_to_agent(rule, agent_context)
        ]

        if not visible_rules:
            return []

        # 3. Filter by condition match against agent context tags
        matching_rules: List[LearnedRule] = []
        for rule in visible_rules:
            if self._matches_condition(rule.condition, agent_context.context_tags):
                matching_rules.append(rule)

        if not matching_rules:
            return []

        # 4. Group rules that may conflict (e.g. by conflict group or same target aspect)
        grouped_rules = self._group_conflicting_rules(matching_rules)

        # 5. Resolve conflicts within each group
        resolved_rules: List[LearnedRule] = []
        for group in grouped_rules:
            if len(group) == 1:
                resolved_rules.append(group[0])
            else:
                winner, resolution_rec = self.conflict_resolver.resolve_conflict(
                    competing_rules=group,
                    context_query=agent_context.context_tags,
                    domain=agent_context.domain,
                    active_harness_version=active_harness_version,
                    reference_time=reference_time,
                )
                await self.repository.save_conflict_resolution(resolution_rec)
                resolved_rules.append(winner)

        return resolved_rules

    def _matches_condition(self, condition: Dict[str, Any], context_tags: Dict[str, Any]) -> bool:
        """Determines if rule condition matches context tags."""
        if not condition:
            return True
        for k, v in condition.items():
            if k not in context_tags or context_tags[k] != v:
                return False
        return True

    def _group_conflicting_rules(self, rules: List[LearnedRule]) -> List[List[LearnedRule]]:
        """Groups rules that target overlapping aspect / conflict keys."""
        # Simple grouping by conflict_group metadata key if present, otherwise by condition fingerprint
        groups: Dict[str, List[LearnedRule]] = {}
        for rule in rules:
            group_key = rule.metadata.get("conflict_group")
            if not group_key:
                # Group by condition keys or target role
                cond_keys = "_".join(sorted(rule.condition.keys()))
                group_key = f"{rule.target_role or 'all'}_{cond_keys or 'general'}"
            groups.setdefault(group_key, []).append(rule)
        return list(groups.values())

    # -------------------------------------------------------------------------
    # Rule Lifecycle Operations (§23)
    # -------------------------------------------------------------------------

    async def propose_rule(
        self,
        condition: Dict[str, Any],
        recommendation: str,
        domain: str = "youtube_studio",
        scope: KnowledgeVisibilityScope = KnowledgeVisibilityScope.ROLE,
        target_role: Optional[str] = None,
        project_id: Optional[str] = None,
        evidence_refs: Optional[List[str]] = None,
        metrics: Optional[Dict[str, float]] = None,
        confidence: float = 0.5,
        sample_size: int = 1,
        supersedes_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LearnedRule:
        """Proposes a new candidate learned rule."""
        if not recommendation.strip():
            raise CoreValidationError("Learned rule recommendation cannot be empty.")

        rule_id = f"rule_{uuid.uuid4().hex[:12]}"
        now = utc_now()

        version = 1
        if supersedes_id:
            parent_rule = await self.repository.get_rule(supersedes_id)
            if parent_rule:
                version = parent_rule.version + 1

        rule = LearnedRule(
            rule_id=rule_id,
            condition=condition,
            recommendation=recommendation.strip(),
            domain=domain,
            scope=scope,
            target_role=target_role,
            project_id=project_id,
            evidence_refs=evidence_refs or [],
            metrics=metrics or {},
            confidence=confidence,
            sample_size=sample_size,
            version=version,
            state=LearnedRuleState.CANDIDATE,
            supersedes_id=supersedes_id,
            created_at=now,
            metadata=metadata or {},
        )

        await self.repository.save_rule(rule)
        return rule

    async def promote_rule(
        self,
        rule_id: str,
        approved_by: Optional[str] = None,
        harness_version: Optional[str] = None,
    ) -> LearnedRule:
        """Promotes a candidate rule to active PROMOTED status (§20, §23, §35)."""
        rule = await self.repository.get_rule(rule_id)
        if not rule:
            raise NotFoundError(f"LearnedRule '{rule_id}' not found.")

        if rule.state == LearnedRuleState.PROMOTED:
            return rule

        now = utc_now()

        # Update superseded rule if applicable
        if rule.supersedes_id:
            parent_rule = await self.repository.get_rule(rule.supersedes_id)
            if parent_rule and parent_rule.state == LearnedRuleState.PROMOTED:
                deprecated_parent = LearnedRule(
                    **{
                        **parent_rule.to_dict(),
                        "state": LearnedRuleState.DEPRECATED,
                        "superseded_by": rule.rule_id,
                        "deprecated_at": now,
                    }
                )
                await self.repository.save_rule(deprecated_parent)

        updated_metadata = dict(rule.metadata)
        if approved_by:
            updated_metadata["approved_by"] = approved_by
            updated_metadata["approved_at"] = now.isoformat()

        promoted_rule = LearnedRule(
            **{
                **rule.to_dict(),
                "state": LearnedRuleState.PROMOTED,
                "harness_version": harness_version or rule.harness_version,
                "activated_at": now,
                "last_validated_at": now,
                "metadata": updated_metadata,
            }
        )

        await self.repository.save_rule(promoted_rule)
        return promoted_rule

    async def deprecate_rule(
        self,
        rule_id: str,
        reason: str = "Superseded or outdated",
    ) -> LearnedRule:
        """Deprecates an existing rule."""
        rule = await self.repository.get_rule(rule_id)
        if not rule:
            raise NotFoundError(f"LearnedRule '{rule_id}' not found.")

        now = utc_now()
        updated_metadata = dict(rule.metadata)
        updated_metadata["deprecation_reason"] = reason

        deprecated_rule = LearnedRule(
            **{
                **rule.to_dict(),
                "state": LearnedRuleState.DEPRECATED,
                "deprecated_at": now,
                "metadata": updated_metadata,
            }
        )

        await self.repository.save_rule(deprecated_rule)
        return deprecated_rule

    async def rollback_rule(
        self,
        rule_id: str,
        reason: str = "Rollback triggered due to performance regression",
        rollback_target_id: Optional[str] = None,
    ) -> Tuple[LearnedRule, Optional[LearnedRule]]:
        """Rolls back an active rule and optionally re-activates a previous rule (§20, §35)."""
        rule = await self.repository.get_rule(rule_id)
        if not rule:
            raise NotFoundError(f"LearnedRule '{rule_id}' not found.")

        now = utc_now()
        updated_metadata = dict(rule.metadata)
        updated_metadata["rollback_reason"] = reason
        updated_metadata["rolled_back_at"] = now.isoformat()

        rolled_back_rule = LearnedRule(
            **{
                **rule.to_dict(),
                "state": LearnedRuleState.ROLLED_BACK,
                "deprecated_at": now,
                "metadata": updated_metadata,
            }
        )
        await self.repository.save_rule(rolled_back_rule)

        # Re-activate target previous version
        reactivated_rule: Optional[LearnedRule] = None
        target_id = rollback_target_id or rule.supersedes_id
        if target_id:
            target = await self.repository.get_rule(target_id)
            if target:
                reactivated_rule = LearnedRule(
                    **{
                        **target.to_dict(),
                        "state": LearnedRuleState.PROMOTED,
                        "activated_at": now,
                        "deprecated_at": None,
                        "superseded_by": None,
                    }
                )
                await self.repository.save_rule(reactivated_rule)

        return rolled_back_rule, reactivated_rule

    # -------------------------------------------------------------------------
    # YouTube / Studio Metric Attribution (§21, §22)
    # -------------------------------------------------------------------------

    async def attribute_youtube_metrics(
        self,
        episode_id: str,
        metric_signals: Dict[str, float],
        baseline_signals: Optional[Dict[str, float]] = None,
        domain: str = "youtube_studio",
    ) -> MultiAgentAttributionRecord:
        """Performs stage-separated performance attribution across multi-agent roles (§21, §22)."""
        baselines = baseline_signals or {}
        role_attributions: Dict[str, Dict[str, Any]] = {}

        for signal_name, signal_val in metric_signals.items():
            mapping = YOUTUBE_SIGNAL_ROLE_MAP.get(signal_name)
            if not mapping:
                continue

            role = mapping["role"]
            base_val = baselines.get(signal_name, signal_val)
            delta = signal_val - base_val

            # Determine performance verdict
            if delta > 0.05:
                status = "outperforming"
            elif delta < -0.05:
                status = "underperforming"
            else:
                status = "neutral"

            role_attributions[role] = {
                "signal": signal_name,
                "dimension": mapping["dimension"],
                "value": float(signal_val),
                "baseline": float(base_val),
                "delta": round(float(delta), 4),
                "status": status,
                "description": mapping["description"],
            }

        attribution_rec = MultiAgentAttributionRecord(
            attribution_id=f"attr_{uuid.uuid4().hex[:12]}",
            episode_id=episode_id,
            domain=domain,
            metric_signals=metric_signals,
            role_attributions=role_attributions,
            created_at=utc_now(),
        )

        await self.repository.save_attribution(attribution_rec)
        return attribution_rec

