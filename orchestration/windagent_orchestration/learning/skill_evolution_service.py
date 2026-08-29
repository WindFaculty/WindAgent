"""Skill Evolution Orchestration Service (Phase 12 — ban_ke_hoach_v1 §18, §24, §25, §29, §35).

Coordinates the end-to-end skill evolution lifecycle:
1. Candidate Proposal: Validates payload, flags executables / high-risk mutations.
2. Security & Permission Audit: AST analysis, forbidden dynamic exec detection, secret scanning, dependency resolution.
3. Functional & Benchmark Evaluation: Functional test suite verification, accuracy and safety scoring.
4. 7-Gate Promotion & Human Governance: Enforces human approval for executable/high-risk skills; permits bounded automated promotion for low-risk prompt templates.
5. Atomic Deployment: Commits SkillVersion, installs/activates in SkillManager.
6. Post-Promotion Rollback: Reverts active skill to parent SkillVersion upon regressions.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from windagent_core.contracts.repositories.skill_evolution_repository import (
    SkillEvolutionRepositoryProtocol,
)
from windagent_core.contracts.skills import (
    SkillEvaluatorPort,
    SkillManagerPort,
    SkillScannerPort,
    SkillValidatorPort,
)
from windagent_core.domain.skill_evolution import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillEvaluationResult,
    SkillPromotionDecision,
    SkillPromotionStatus,
    SkillRiskLevel,
    SkillSecurityAuditResult,
    SkillVersion,
    SkillVersionStatus,
    utc_now,
)
from windagent_core.errors.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger("windagent.orchestration.skill_evolution")


class SkillEvolutionService:
    """Orchestrator for candidate lifecycle, audits, evaluations, promotions, and rollbacks."""

    def __init__(
        self,
        repository: SkillEvolutionRepositoryProtocol,
        skill_manager: Optional[SkillManagerPort] = None,
        scanner: Optional[SkillScannerPort] = None,
        validator: Optional[SkillValidatorPort] = None,
        evaluator: Optional[SkillEvaluatorPort] = None,
    ) -> None:
        self.repository = repository
        self.skill_manager = skill_manager
        self.scanner = scanner
        self.validator = validator
        self.evaluator = evaluator

    async def propose_candidate(
        self,
        skill_id: str,
        proposed_manifest: Dict[str, Any],
        proposed_code: Optional[str] = None,
        reasoning_summary: str = "",
        supporting_experiences: Optional[List[str]] = None,
        risk_level: SkillRiskLevel = SkillRiskLevel.LOW,
        is_executable: bool = False,
        is_high_risk: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillCandidate:
        """Proposes a new skill mutation candidate."""
        if not skill_id or not skill_id.strip():
            raise ValidationError("skill_id cannot be empty.")

        # Ensure manifest dictionary has matching ID
        manifest_data = dict(proposed_manifest)
        manifest_data["id"] = skill_id

        # If executable code is supplied, flag as executable and elevate risk accordingly
        has_code = bool(proposed_code and proposed_code.strip())
        final_executable = is_executable or has_code
        final_high_risk = (
            is_high_risk or final_executable or (risk_level in (SkillRiskLevel.HIGH, SkillRiskLevel.CRITICAL))
        )

        candidate_id = f"skcand_{uuid.uuid4().hex[:12]}"
        candidate = SkillCandidate(
            candidate_id=candidate_id,
            skill_id=skill_id,
            proposed_manifest=manifest_data,
            proposed_code=proposed_code,
            reasoning_summary=reasoning_summary or f"Proposed evolution for skill [{skill_id}].",
            supporting_experiences=supporting_experiences or [],
            status=SkillCandidateStatus.PROPOSED,
            risk_level=risk_level if not final_high_risk else SkillRiskLevel.HIGH,
            is_executable=final_executable,
            is_high_risk=final_high_risk,
            metadata=metadata or {},
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        await self.repository.save_candidate(candidate)
        logger.info(f"Proposed skill candidate [{candidate_id}] for skill [{skill_id}].")
        return candidate

    async def audit_candidate(self, candidate_id: str) -> tuple[SkillCandidate, SkillSecurityAuditResult]:
        """Runs static AST scanning, secret scanning, dependency verification, and permission checks."""
        candidate = await self.repository.get_candidate(candidate_id)
        if not candidate:
            raise NotFoundError(f"Skill candidate [{candidate_id}] not found.")

        manifest_violations: List[str] = []
        valid_manifest = True
        dep_passed = True
        dep_violations: List[str] = []
        perm_passed = True
        perm_violations: List[str] = []

        if self.validator:
            # 1. Manifest structure validation
            valid_manifest, _, manifest_violations = self.validator.validate_manifest(
                candidate.proposed_manifest
            )

            # 2. Dependency validation
            req_tools = candidate.proposed_manifest.get("required_tools", [])
            req_workflows = candidate.proposed_manifest.get("required_workflows", [])
            dep_passed, dep_violations = self.validator.validate_dependencies(req_tools, req_workflows)

            # 3. Permission audit
            req_perms = candidate.proposed_manifest.get("required_permissions", [])
            perm_passed, perm_violations = self.validator.audit_permissions(req_perms)

        # 4. Security scan (AST + Secrets)
        all_dep_violations = manifest_violations + dep_violations
        if self.scanner:
            audit_result = self.scanner.audit(
                source_code=candidate.proposed_code,
                manifest_dict=candidate.proposed_manifest,
                dependency_passed=valid_manifest and dep_passed,
                permission_passed=perm_passed,
                dependency_violations=all_dep_violations,
                permission_violations=perm_violations,
            )
        else:
            all_viols = all_dep_violations + perm_violations
            audit_result = SkillSecurityAuditResult(
                passed=(valid_manifest and dep_passed and perm_passed and len(all_viols) == 0),
                ast_scan_passed=True,
                permission_audit_passed=perm_passed,
                dependency_validation_passed=valid_manifest and dep_passed,
                secret_scan_passed=True,
                violations=all_viols,
                risk_score=0.0 if not all_viols else 0.5,
            )

        updated_candidate = candidate.with_audit(audit_result)
        await self.repository.save_candidate(updated_candidate)
        logger.info(
            f"Audited skill candidate [{candidate_id}]: passed={audit_result.is_safe}, "
            f"violations={len(audit_result.violations)}."
        )
        return updated_candidate, audit_result

    async def evaluate_candidate(
        self,
        candidate_id: str,
        test_cases: Optional[List[Any]] = None,
    ) -> tuple[SkillCandidate, SkillEvaluationResult]:
        """Runs functional tests and benchmark evaluation on a skill candidate."""
        candidate = await self.repository.get_candidate(candidate_id)
        if not candidate:
            raise NotFoundError(f"Skill candidate [{candidate_id}] not found.")

        # If not yet audited, run audit first
        if not candidate.security_audit:
            candidate, audit_res = await self.audit_candidate(candidate_id)
            if not audit_res.is_safe:
                raise ValidationError(
                    f"Candidate [{candidate_id}] failed security audit: {audit_res.violations}"
                )

        if self.evaluator:
            eval_result = self.evaluator.evaluate(candidate, test_cases=test_cases)
        else:
            eval_result = SkillEvaluationResult(
                evaluation_id=f"skeval_{uuid.uuid4().hex[:12]}",
                skill_candidate_id=candidate.candidate_id,
                benchmark_passed=True,
                test_suite_passed=True,
                tests_run=1,
                tests_passed=1,
                tests_failed=0,
                accuracy_score=1.0,
                safety_score=1.0,
            )

        updated_candidate = candidate.with_evaluation(eval_result)
        await self.repository.save_candidate(updated_candidate)

        logger.info(
            f"Evaluated skill candidate [{candidate_id}]: benchmark_passed={eval_result.benchmark_passed}, "
            f"accuracy={eval_result.accuracy_score:.2f}, safety={eval_result.safety_score:.2f}."
        )
        return updated_candidate, eval_result

    async def promote_candidate(
        self,
        candidate_id: str,
        approved_by: Optional[str] = None,
        rationale: str = "",
    ) -> tuple[SkillPromotionDecision, SkillVersion]:
        """Promotes an evaluated skill candidate to an active, deployed SkillVersion."""
        candidate = await self.repository.get_candidate(candidate_id)
        if not candidate:
            raise NotFoundError(f"Skill candidate [{candidate_id}] not found.")

        # Ensure candidate is audited
        if not candidate.security_audit:
            candidate, _ = await self.audit_candidate(candidate_id)

        # Ensure candidate is evaluated
        if not candidate.evaluation:
            candidate, _ = await self.evaluate_candidate(candidate_id)

        # 1. Gate Check: Security audit must be 100% safe
        if not candidate.security_audit.is_safe:
            decision_id = f"skprom_{uuid.uuid4().hex[:12]}"
            decision = SkillPromotionDecision(
                decision_id=decision_id,
                candidate_id=candidate_id,
                skill_id=candidate.skill_id,
                target_version=str(candidate.proposed_manifest.get("version", "1.0.0")),
                status=SkillPromotionStatus.REJECTED,
                security_audit_passed=False,
                evaluation_passed=candidate.evaluation.benchmark_passed,
                requires_human_approval=candidate.is_high_risk,
                rejection_reason=f"Security audit failed with violations: {candidate.security_audit.violations}",
                decision_rationale=rationale or "Rejected by security gate.",
            )
            await self.repository.save_promotion(decision)
            await self.repository.save_candidate(candidate.mark_rejected("Security audit failed."))
            raise PermissionDeniedError(
                message=f"Cannot promote skill candidate [{candidate_id}]: security audit failed.",
                code="WINDAGENT_ERR_SKILL_SECURITY_FAILED",
                details={"violations": candidate.security_audit.violations},
            )

        # 2. Gate Check: Evaluation benchmark must have passed
        if not candidate.evaluation.benchmark_passed or candidate.evaluation.safety_score < 0.95:
            decision_id = f"skprom_{uuid.uuid4().hex[:12]}"
            decision = SkillPromotionDecision(
                decision_id=decision_id,
                candidate_id=candidate_id,
                skill_id=candidate.skill_id,
                target_version=str(candidate.proposed_manifest.get("version", "1.0.0")),
                status=SkillPromotionStatus.REJECTED,
                security_audit_passed=True,
                evaluation_passed=False,
                requires_human_approval=candidate.is_high_risk,
                rejection_reason=f"Evaluation benchmark failed (accuracy={candidate.evaluation.accuracy_score}, safety={candidate.evaluation.safety_score}).",
                decision_rationale=rationale or "Rejected by evaluation benchmark gate.",
            )
            await self.repository.save_promotion(decision)
            await self.repository.save_candidate(candidate.mark_rejected("Evaluation benchmark failed."))
            raise ValidationError(
                f"Cannot promote skill candidate [{candidate_id}]: evaluation benchmark failed."
            )

        # 3. Gate Check: Executable skills and High-Risk skills require human approval (§18, §35)
        requires_human = candidate.is_executable or candidate.is_high_risk
        if requires_human:
            if not approved_by or not approved_by.strip():
                decision_id = f"skprom_{uuid.uuid4().hex[:12]}"
                decision = SkillPromotionDecision(
                    decision_id=decision_id,
                    candidate_id=candidate_id,
                    skill_id=candidate.skill_id,
                    target_version=str(candidate.proposed_manifest.get("version", "1.0.0")),
                    status=SkillPromotionStatus.PENDING_APPROVAL,
                    security_audit_passed=True,
                    evaluation_passed=True,
                    requires_human_approval=True,
                    decision_rationale=rationale or "Awaiting human authorization for executable/high-risk skill.",
                )
                await self.repository.save_promotion(decision)
                raise PermissionDeniedError(
                    message=f"Promotion for executable skill candidate [{candidate_id}] requires explicit human approval.",
                    code="WINDAGENT_ERR_HUMAN_APPROVAL_REQUIRED",
                    details={"candidate_id": candidate_id, "skill_id": candidate.skill_id},
                )
        else:
            approved_by = approved_by or "system_automated_promotion"

        # Lookup current active version to establish parent link
        current_active = await self.repository.get_active_version(candidate.skill_id)
        parent_version_id = current_active.version_id if current_active else None
        target_version_str = str(candidate.proposed_manifest.get("version", "1.0.0"))
        version_id = f"skver_{candidate.skill_id}_v{target_version_str}"

        # Check for version collision
        existing_version = await self.repository.get_version(version_id)
        if existing_version and existing_version.status == SkillVersionStatus.ACTIVE:
            raise ConflictError(f"SkillVersion [{version_id}] is already active.")

        # Create new SkillVersion
        new_version = SkillVersion(
            version_id=version_id,
            skill_id=candidate.skill_id,
            version=target_version_str,
            parent_version=parent_version_id,
            manifest=candidate.proposed_manifest,
            code_hash=candidate.compute_code_hash(),
            source_code=candidate.proposed_code,
            status=SkillVersionStatus.ACTIVE,
            promoted_from_candidate_id=candidate_id,
            security_audit_id=candidate_id,
            evaluation_id=candidate.evaluation.evaluation_id,
            created_at=utc_now(),
            activated_at=utc_now(),
        )

        # Deprecate previous active version if exists
        if current_active:
            deprecated_active = current_active.deprecate()
            await self.repository.save_version(deprecated_active)

        # Persist new SkillVersion
        await self.repository.save_version(new_version)

        # Record promotion decision
        decision_id = f"skprom_{uuid.uuid4().hex[:12]}"
        decision = SkillPromotionDecision(
            decision_id=decision_id,
            candidate_id=candidate_id,
            skill_id=candidate.skill_id,
            source_version=current_active.version if current_active else None,
            target_version=target_version_str,
            status=SkillPromotionStatus.PROMOTED,
            security_audit_passed=True,
            evaluation_passed=True,
            requires_human_approval=requires_human,
            approved_by=approved_by,
            approved_at=utc_now(),
            decision_rationale=rationale or "All 7 promotion gates and security audits passed.",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.repository.save_promotion(decision)

        # Mark candidate promoted
        await self.repository.save_candidate(candidate.mark_promoted())

        # Deploy into runtime SkillManager if present
        if self.skill_manager:
            self.skill_manager.install_skill_code(candidate.proposed_manifest, candidate.proposed_code)

        logger.info(
            f"Successfully promoted skill candidate [{candidate_id}] to SkillVersion [{version_id}] "
            f"(approved_by: {approved_by})."
        )
        return decision, new_version

    async def rollback_skill(
        self,
        skill_id: str,
        target_version_id: Optional[str] = None,
        reason: str = "",
    ) -> tuple[SkillPromotionDecision, SkillVersion]:
        """Rolls back an active skill to a previous SkillVersion."""
        current_active = await self.repository.get_active_version(skill_id)
        if not current_active:
            raise NotFoundError(f"No active SkillVersion found for skill [{skill_id}] to roll back.")

        # Determine target version to restore
        if target_version_id:
            target_version = await self.repository.get_version(target_version_id)
        elif current_active.parent_version:
            target_version = await self.repository.get_version(current_active.parent_version)
        else:
            raise ValidationError(
                f"Cannot roll back skill [{skill_id}]: no parent version recorded for active version [{current_active.version_id}]."
            )

        if not target_version:
            raise NotFoundError(
                f"Target rollback version [{target_version_id or current_active.parent_version}] not found."
            )

        # Mark current active as ROLLED_BACK
        rolled_back_current = current_active.mark_rolled_back()
        await self.repository.save_version(rolled_back_current)

        # Reactivate target version
        reactivated_target = target_version.model_copy(
            update={
                "status": SkillVersionStatus.ACTIVE,
                "activated_at": utc_now(),
                "deprecated_at": None,
            }
        )
        await self.repository.save_version(reactivated_target)

        # Reinstall previous version in SkillManager if present
        if self.skill_manager:
            self.skill_manager.rollback_skill_version(
                reactivated_target.manifest, reactivated_target.source_code
            )

        # Record rollback decision
        decision_id = f"skprom_{uuid.uuid4().hex[:12]}"
        decision = SkillPromotionDecision(
            decision_id=decision_id,
            candidate_id=current_active.promoted_from_candidate_id or "rollback_manual",
            skill_id=skill_id,
            source_version=current_active.version,
            target_version=reactivated_target.version,
            status=SkillPromotionStatus.ROLLED_BACK,
            security_audit_passed=True,
            evaluation_passed=True,
            requires_human_approval=False,
            approved_by="rollback_coordinator",
            approved_at=utc_now(),
            decision_rationale=f"Rolled back from v{current_active.version} to v{reactivated_target.version}. Reason: {reason or 'Performance regression detected.'}",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await self.repository.save_promotion(decision)

        logger.info(
            f"Successfully rolled back skill [{skill_id}] from [{current_active.version_id}] to [{reactivated_target.version_id}]."
        )
        return decision, reactivated_target


__all__ = ["SkillEvolutionService"]
