"""Subagent Evolution Orchestration Service (Phase 13 — ban_ke_hoach_v1 §19, §24, §25, §29, §35).

Coordinates the complete subagent evolution lifecycle:
1. Candidate Proposal: Validates spec parameters, infers risk level, bounds memory access.
2. Security & Policy Audit: Scans tools, skills, prompt safety, memory visibility, and budget/depth boundaries.
3. Functional & Benchmark Evaluation: Verifies output contracts, task accuracy, safety score (>= 0.95), and token efficiency.
4. 7-Gate Promotion & Human Governance: Enforces human approval for high-risk subagents; permits bounded automated promotion for low-risk subagents.
5. Atomic Deployment: Commits SubagentSpecVersion, activates in registry, deprecates previous active version.
6. Post-Promotion Rollback: Reverts active subagent spec to parent SubagentSpecVersion upon regressions.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from windagent_core.contracts.repositories.subagent_evolution_repository import (
    SubagentEvolutionRepositoryProtocol,
)
from windagent_core.contracts.subagents import (
    SubagentEvaluatorPort,
    SubagentScannerPort,
    SubagentSpecRegistryPort,
)
from windagent_core.domain.agent_loop import AgentBudgetLimits
from windagent_core.domain.subagent_evolution import (
    MemoryAccessPolicy,
    MemoryScope,
    ModelRoutingPolicy,
    SubagentCandidate,
    SubagentCandidateStatus,
    SubagentEvaluationResult,
    SubagentOutputContract,
    SubagentPromotionDecision,
    SubagentPromotionStatus,
    SubagentRiskLevel,
    SubagentSecurityAuditResult,
    SubagentSpecStatus,
    SubagentSpecVersion,
    utc_now,
)
from windagent_core.errors.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
logger = logging.getLogger("windagent.orchestration.subagent_evolution")


class SubagentEvolutionService:
    """Orchestrator for subagent candidate proposal, security audit, evaluation, promotion, and rollback."""

    def __init__(
        self,
        repository: SubagentEvolutionRepositoryProtocol,
        scanner: SubagentScannerPort,
        evaluator: SubagentEvaluatorPort,
        spec_registry: Optional[SubagentSpecRegistryPort] = None,
        registered_tools: Optional[List[str]] = None,
        registered_skills: Optional[List[str]] = None,
    ) -> None:
        self.repository = repository
        self.scanner = scanner
        self.evaluator = evaluator
        self.spec_registry = spec_registry
        self.registered_tools = registered_tools
        self.registered_skills = registered_skills

    async def propose_candidate(
        self,
        role: str,
        proposed_spec: Dict[str, Any],
        reasoning_summary: str = "",
        supporting_experiences: Optional[List[str]] = None,
        risk_level: SubagentRiskLevel = SubagentRiskLevel.LOW,
        is_high_risk: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SubagentCandidate:
        """Proposes a new subagent candidate or evolution."""
        if not role or not role.strip():
            raise ValidationError("role cannot be empty.")

        spec_data = dict(proposed_spec)
        spec_data["role"] = role

        # Check memory access and budget to determine if high risk
        mem_access = spec_data.get("memory_access", {})
        write_scopes = mem_access.get("allowed_write_scopes", []) if isinstance(mem_access, dict) else []
        has_global_write = "GLOBAL" in write_scopes or MemoryScope.GLOBAL in write_scopes or "PROJECT" in write_scopes

        max_depth = int(spec_data.get("max_depth", 2))
        max_budget = spec_data.get("max_budget", {})
        max_cost = float(max_budget.get("max_cost_usd", 0.0)) if isinstance(max_budget, dict) else 0.0

        final_high_risk = (
            is_high_risk
            or has_global_write
            or (max_depth > 3)
            or (max_cost > 20.0)
            or (risk_level in (SubagentRiskLevel.HIGH, SubagentRiskLevel.CRITICAL))
        )
        final_risk_level = SubagentRiskLevel.HIGH if final_high_risk and risk_level == SubagentRiskLevel.LOW else risk_level

        candidate_id = f"subcand_{uuid.uuid4().hex[:12]}"
        candidate = SubagentCandidate(
            candidate_id=candidate_id,
            role=role,
            proposed_spec=spec_data,
            reasoning_summary=reasoning_summary or f"Proposed evolution for subagent role [{role}].",
            supporting_experiences=supporting_experiences or [],
            status=SubagentCandidateStatus.PROPOSED,
            risk_level=final_risk_level,
            is_high_risk=final_high_risk,
            metadata=metadata or {},
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        await self.repository.save_candidate(candidate)
        logger.info(f"Proposed subagent candidate [{candidate_id}] for role [{role}] (high_risk={final_high_risk})")
        return candidate

    async def audit_candidate(self, candidate_id: str) -> SubagentCandidate:
        """Audits a proposed subagent candidate against security, tools, memory, and prompt policies."""
        candidate = await self.repository.get_candidate(candidate_id)
        if not candidate:
            raise NotFoundError(f"Subagent candidate [{candidate_id}] not found.")

        audit_result: SubagentSecurityAuditResult = self.scanner.audit(
            candidate,
            registered_tools=self.registered_tools,
            registered_skills=self.registered_skills,
        )

        updated_candidate = candidate.with_audit(audit_result)
        await self.repository.save_candidate(updated_candidate)
        logger.info(
            f"Audited subagent candidate [{candidate_id}]: passed={audit_result.passed}, "
            f"violations={len(audit_result.violations)}"
        )
        return updated_candidate

    async def evaluate_candidate(
        self,
        candidate_id: str,
        test_cases: Optional[List[Any]] = None,
        baseline_token_usage: int = 3000,
        baseline_latency_ms: float = 250.0,
    ) -> SubagentCandidate:
        """Evaluates a subagent candidate against task benchmarks, contract schema, and safety scores."""
        candidate = await self.repository.get_candidate(candidate_id)
        if not candidate:
            raise NotFoundError(f"Subagent candidate [{candidate_id}] not found.")

        # Ensure candidate has been audited first
        if candidate.status not in (SubagentCandidateStatus.AUDITED, SubagentCandidateStatus.EVALUATED):
            audit_result = self.scanner.audit(
                candidate,
                registered_tools=self.registered_tools,
                registered_skills=self.registered_skills,
            )
            candidate = candidate.with_audit(audit_result)
            if not audit_result.is_safe:
                await self.repository.save_candidate(candidate)
                return candidate

        eval_result: SubagentEvaluationResult = self.evaluator.evaluate(
            candidate,
            test_cases=test_cases,
            baseline_token_usage=baseline_token_usage,
            baseline_latency_ms=baseline_latency_ms,
        )

        updated_candidate = candidate.with_evaluation(eval_result)
        await self.repository.save_candidate(updated_candidate)
        logger.info(
            f"Evaluated subagent candidate [{candidate_id}]: benchmark_passed={eval_result.benchmark_passed}, "
            f"accuracy={eval_result.accuracy_score:.2f}, safety={eval_result.safety_score:.2f}, "
            f"contract={eval_result.contract_compliance_score:.2f}"
        )
        return updated_candidate

    async def promote_candidate(
        self,
        candidate_id: str,
        target_version: str,
        approved_by: Optional[str] = None,
        decision_rationale: str = "",
    ) -> tuple[SubagentPromotionDecision, SubagentSpecVersion]:
        """Promotes an evaluated subagent candidate to an active, deployed SubagentSpecVersion (§19, §35)."""
        candidate = await self.repository.get_candidate(candidate_id)
        if not candidate:
            raise NotFoundError(f"Subagent candidate [{candidate_id}] not found.")

        # Gate 1: Candidate state verification
        if candidate.status not in (SubagentCandidateStatus.EVALUATED, SubagentCandidateStatus.AUDITED):
            raise ValidationError(
                f"Candidate [{candidate_id}] is in state '{candidate.status.value}'. "
                "Must be EVALUATED and pass benchmark/security audits before promotion."
            )

        # Gate 2: Security Audit verification
        if not candidate.security_audit or not candidate.security_audit.is_safe:
            violations_summary = (
                ", ".join(candidate.security_audit.violations)
                if candidate.security_audit
                else "No security audit report available"
            )
            raise ValidationError(
                f"Promotion rejected: Candidate [{candidate_id}] failed security audit. Violations: {violations_summary}"
            )

        # Gate 3: Benchmark & Contract Evaluation verification
        if not candidate.evaluation or not candidate.evaluation.benchmark_passed:
            eval_details = (
                f"accuracy={candidate.evaluation.accuracy_score}, safety={candidate.evaluation.safety_score}, "
                f"contract={candidate.evaluation.contract_compliance_score}"
                if candidate.evaluation
                else "No evaluation report available"
            )
            raise ValidationError(
                f"Promotion rejected: Candidate [{candidate_id}] failed evaluation benchmark ({eval_details})."
            )

        # Gate 4: Human Governance for High-Risk Subagents (§19, §35)
        requires_human = candidate.is_high_risk or candidate.risk_level in (
            SubagentRiskLevel.HIGH,
            SubagentRiskLevel.CRITICAL,
        )
        if requires_human and not approved_by:
            raise PermissionDeniedError(
                f"Promotion of high-risk subagent candidate [{candidate_id}] for role [{candidate.role}] "
                "strictly requires explicit human approval (approved_by)."
            )

        # Gate 5: Semver collision check
        existing_version = await self.repository.get_spec_by_semver(candidate.role, target_version)
        if existing_version and existing_version.status == SubagentSpecStatus.ACTIVE:
            raise ConflictError(
                f"SubagentSpecVersion [{candidate.role}:{target_version}] is already active."
            )

        # Gate 6: Atomic version deployment & active deprecation
        active_version = await self.repository.get_active_spec(candidate.role)
        parent_version_str = active_version.version if active_version else None

        spec_dict = candidate.proposed_spec
        routing_raw = spec_dict.get("model_routing_policy", {})
        routing_policy = ModelRoutingPolicy(**routing_raw) if isinstance(routing_raw, dict) else ModelRoutingPolicy()

        mem_raw = spec_dict.get("memory_access", {})
        memory_access = MemoryAccessPolicy(**mem_raw) if isinstance(mem_raw, dict) else MemoryAccessPolicy()

        budget_raw = spec_dict.get("max_budget", {})
        max_budget = AgentBudgetLimits(**budget_raw) if isinstance(budget_raw, dict) else AgentBudgetLimits()

        contract_raw = spec_dict.get("output_contract", {})
        output_contract = SubagentOutputContract(**contract_raw) if isinstance(contract_raw, dict) else SubagentOutputContract()

        version_id = f"subspec_{uuid.uuid4().hex[:12]}"
        new_version = SubagentSpecVersion(
            id=version_id,
            role=candidate.role,
            version=target_version,
            parent_version=parent_version_str,
            objective=spec_dict.get("objective", f"Specialized {candidate.role}"),
            system_supplement=spec_dict.get("system_supplement", ""),
            allowed_tools=spec_dict.get("allowed_tools", []),
            allowed_skills=spec_dict.get("allowed_skills", []),
            model_routing_policy=routing_policy,
            memory_access=memory_access,
            max_budget=max_budget,
            max_depth=int(spec_dict.get("max_depth", 2)),
            output_contract=output_contract,
            status=SubagentSpecStatus.ACTIVE,
            risk_level=candidate.risk_level,
            promoted_from_candidate_id=candidate.candidate_id,
            security_audit_id=candidate.candidate_id,
            evaluation_id=candidate.evaluation.evaluation_id if candidate.evaluation else None,
            metadata=candidate.metadata,
            created_at=utc_now(),
            activated_at=utc_now(),
        )

        # Deprecate previously active version
        if active_version:
            deprecated_active = active_version.model_copy(
                update={
                    "status": SubagentSpecStatus.DEPRECATED,
                    "deprecated_at": utc_now(),
                }
            )
            await self.repository.save_spec(deprecated_active)

        await self.repository.save_spec(new_version)

        # Update candidate status to PROMOTED
        promoted_cand = candidate.model_copy(
            update={
                "status": SubagentCandidateStatus.PROMOTED,
                "updated_at": utc_now(),
            }
        )
        await self.repository.save_candidate(promoted_cand)

        # Register in runtime spec registry if present
        if self.spec_registry:
            self.spec_registry.register_spec(new_version)

        # Gate 7: Durable Promotion Decision Audit Record
        decision_id = f"subprom_{uuid.uuid4().hex[:12]}"
        decision = SubagentPromotionDecision(
            id=decision_id,
            candidate_id=candidate.candidate_id,
            role=candidate.role,
            source_version=parent_version_str,
            target_version=target_version,
            status=SubagentPromotionStatus.PROMOTED,
            security_audit_passed=True,
            evaluation_passed=True,
            requires_human_approval=requires_human,
            approved_by=approved_by,
            approved_at=utc_now() if approved_by else None,
            decision_rationale=decision_rationale or f"Successfully promoted candidate [{candidate_id}] to spec [{version_id}] ({candidate.role}:{target_version})",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.repository.save_promotion(decision)

        logger.info(
            f"Promoted subagent candidate [{candidate_id}] to SubagentSpecVersion [{version_id}] "
            f"({candidate.role}:{target_version})"
        )
        return decision, new_version

    async def rollback_spec(
        self,
        role: str,
        target_version_id: Optional[str] = None,
        target_version: Optional[str] = None,
        reason: str = "Rollback triggered due to performance or safety regression",
        initiated_by: Optional[str] = None,
    ) -> tuple[SubagentPromotionDecision, SubagentSpecVersion]:
        """Rolls back an active subagent spec to a previous/parent SubagentSpecVersion (§19, §35)."""
        active_version = await self.repository.get_active_spec(role)
        if not active_version:
            raise NotFoundError(f"No active SubagentSpecVersion found for role [{role}] to roll back.")

        target_spec: Optional[SubagentSpecVersion] = None
        if target_version_id:
            target_spec = await self.repository.get_spec(target_version_id)
        elif target_version:
            target_spec = await self.repository.get_spec_by_semver(role, target_version)
        elif active_version.parent_version:
            target_spec = await self.repository.get_spec_by_semver(role, active_version.parent_version)

        if not target_spec:
            raise NotFoundError(
                f"Target rollback SubagentSpecVersion not found for role [{role}]."
            )

        # Deprecate current active version as rolled back
        rolled_back_active = active_version.model_copy(
            update={
                "status": SubagentSpecStatus.ROLLED_BACK,
                "deprecated_at": utc_now(),
            }
        )
        await self.repository.save_spec(rolled_back_active)

        # Reactivate target spec
        reactivated_target = target_spec.model_copy(
            update={
                "status": SubagentSpecStatus.ACTIVE,
                "activated_at": utc_now(),
            }
        )
        await self.repository.save_spec(reactivated_target)

        # Update runtime registry if present
        if self.spec_registry:
            self.spec_registry.register_spec(reactivated_target)

        # Record rollback decision
        decision_id = f"subprom_{uuid.uuid4().hex[:12]}"
        decision = SubagentPromotionDecision(
            id=decision_id,
            candidate_id=active_version.promoted_from_candidate_id or "rollback_trigger",
            role=role,
            source_version=active_version.version,
            target_version=reactivated_target.version,
            status=SubagentPromotionStatus.ROLLED_BACK,
            security_audit_passed=True,
            evaluation_passed=True,
            requires_human_approval=True,
            approved_by=initiated_by,
            approved_at=utc_now(),
            rejection_reason=reason,
            decision_rationale=f"Rolled back role [{role}] from version [{active_version.version}] to [{reactivated_target.version}]. Reason: {reason}",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.repository.save_promotion(decision)

        logger.info(
            f"Successfully rolled back subagent [{role}] from [{active_version.version}] to [{reactivated_target.version}]."
        )
        return decision, reactivated_target

    async def get_active_spec(self, role: str) -> Optional[SubagentSpecVersion]:
        """Retrieves currently active spec for a specialized subagent role."""
        return await self.repository.get_active_spec(role)

    async def resolve_delegation_context_from_spec(
        self,
        role: str,
        base_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Enriches delegation context with active versioned spec parameters."""
        active_spec = await self.get_active_spec(role)
        if not active_spec:
            return base_context

        enriched = dict(base_context)
        enriched["system_supplement"] = active_spec.system_supplement
        enriched["allowed_tools"] = active_spec.allowed_tools
        enriched["allowed_skills"] = active_spec.allowed_skills
        enriched["model_routing_policy"] = active_spec.model_routing_policy.model_dump()
        enriched["memory_access"] = active_spec.memory_access.model_dump()
        enriched["max_budget"] = active_spec.max_budget.model_dump()
        enriched["max_depth"] = active_spec.max_depth
        enriched["output_contract"] = active_spec.output_contract.model_dump()
        enriched["spec_version"] = active_spec.version
        return enriched
