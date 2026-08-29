"""Learning Workflow Orchestrator Service (Phase 11 — ban_ke_hoach_v1 §17, §24, §25, §35).

Coordinates the end-to-end continuous learning and promotion lifecycle:
Candidate -> Experiment -> Promotion Gate -> Harness Version Commit -> Post-Promotion Monitoring -> Rollback.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from windagent_core.contracts.repositories.experiment_repository import (
    ExperimentRepositoryProtocol,
)
from windagent_core.contracts.repositories.harness_repository import (
    HarnessRepositoryProtocol,
)
from windagent_core.contracts.repositories.promotion_repository import (
    PromotionRepositoryProtocol,
)
from windagent_core.domain.candidate import (
    CandidateKind,
    LearningCandidate,
)
from windagent_core.domain.experiment import (
    Experiment,
    ExperimentType,
)
from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    HarnessVersionStatus,
)
from windagent_core.domain.promotion import (
    PostPromotionHealth,
    PromotionDecision,
)
from windagent_orchestration.learning.experiment_runner import ExperimentRunner
from windagent_orchestration.learning.promotion_gate import PromotionGate
from windagent_orchestration.learning.rollback_coordinator import RollbackCoordinator

logger = logging.getLogger("windagent.orchestration.learning.workflow")


class LearningWorkflowService:
    """High-level orchestration service for experiments, promotions, and rollbacks."""

    def __init__(
        self,
        experiment_repo: Optional[ExperimentRepositoryProtocol] = None,
        promotion_repo: Optional[PromotionRepositoryProtocol] = None,
        harness_repo: Optional[HarnessRepositoryProtocol] = None,
        promotion_gate: Optional[PromotionGate] = None,
        experiment_runner: Optional[ExperimentRunner] = None,
        rollback_coordinator: Optional[RollbackCoordinator] = None,
    ) -> None:
        self.experiment_repo = experiment_repo
        self.promotion_repo = promotion_repo
        self.harness_repo = harness_repo
        self.promotion_gate = promotion_gate or PromotionGate()
        self.experiment_runner = experiment_runner or ExperimentRunner(repository=experiment_repo)
        self.rollback_coordinator = rollback_coordinator or RollbackCoordinator(
            harness_repo=harness_repo,
            promotion_repo=promotion_repo,
        )

        # In-memory storage fallback for testing / decoupled execution
        self._memory_candidates: Dict[str, LearningCandidate] = {}
        self._memory_experiments: Dict[str, Experiment] = {}
        self._memory_decisions: Dict[str, PromotionDecision] = {}
        self._memory_harness_versions: Dict[str, HarnessVersion] = {}

    def register_candidate(self, candidate: LearningCandidate) -> None:
        """Registers a candidate in memory for evaluation."""
        self._memory_candidates[candidate.candidate_id] = candidate

    async def run_experiment_for_candidate(
        self,
        candidate: LearningCandidate,
        baseline_harness_version: str,
        baseline_episodes: List[Dict[str, Any]],
        candidate_episodes: List[Dict[str, Any]],
        experiment_type: ExperimentType = ExperimentType.REPLAY,
        dataset_id: Optional[str] = None,
    ) -> Experiment:
        """Executes a comparative experiment for a candidate."""
        self.register_candidate(candidate)
        exp = await self.experiment_runner.run_experiment(
            candidate=candidate,
            baseline_harness_version=baseline_harness_version,
            baseline_episodes=baseline_episodes,
            candidate_episodes=candidate_episodes,
            experiment_type=experiment_type,
            dataset_id=dataset_id,
        )
        self._memory_experiments[exp.experiment_id] = exp
        return exp

    async def evaluate_promotion_gate(
        self,
        candidate: LearningCandidate,
        experiment: Experiment,
        source_harness_version: str,
    ) -> PromotionDecision:
        """Evaluates 7 promotion gates for a completed experiment and persists the decision."""
        decision = self.promotion_gate.evaluate_candidate(
            candidate=candidate,
            experiment=experiment,
            source_harness_version=source_harness_version,
        )

        self._memory_decisions[decision.decision_id] = decision
        if self.promotion_repo:
            await self.promotion_repo.save_decision(decision)

        return decision

    async def execute_promotion(
        self,
        decision: PromotionDecision,
        candidate: LearningCandidate,
        base_harness_version: HarnessVersion,
        approver: str,
        new_version_id: Optional[str] = None,
        rationale: str = "Promotion gate validated and committed.",
    ) -> tuple[PromotionDecision, HarnessVersion]:
        """Atomically promotes an evaluated candidate and commits a new active HarnessVersion."""
        target_vid = new_version_id or f"harness_v{base_harness_version.version_number + 1}"
        new_vnum = base_harness_version.version_number + 1

        # 1. Validate and update PromotionDecision
        promoted_decision = decision.approve_and_promote(
            target_harness_version=target_vid,
            approver=approver,
            rationale=rationale,
        )

        # 2. Build supplemental entries for new HarnessVersion
        entry_kind = (
            HarnessEntryKind.PROMPT_RULE
            if candidate.kind == CandidateKind.PROMPT_RULE
            else HarnessEntryKind.MEMORY_REF
            if candidate.kind == CandidateKind.MEMORY
            else HarnessEntryKind.SKILL_REF
            if candidate.kind == CandidateKind.SKILL
            else HarnessEntryKind.SUBAGENT_SPEC
            if candidate.kind == CandidateKind.SUBAGENT_SPEC
            else HarnessEntryKind.ROUTING_POLICY
        )

        new_entry = HarnessEntry(
            entry_id=f"hent_{uuid.uuid4().hex[:10]}",
            kind=entry_kind,
            name=candidate.proposed_change.get("name", f"rule_{candidate.candidate_id}"),
            content=candidate.proposed_change,
            priority=50,
            enabled=True,
            scope=candidate.scope.value,
            metadata={"candidate_id": candidate.candidate_id},
        )

        existing_entries = [e for e in base_harness_version.entries if e.name != new_entry.name]
        existing_entries.append(new_entry)
        existing_entries.sort(key=lambda e: e.priority)

        # 3. Create new HarnessVersion
        new_harness = HarnessVersion(
            version_id=target_vid,
            version_number=new_vnum,
            parent_version=base_harness_version.version_id,
            status=HarnessVersionStatus.ACTIVE,
            entries=existing_entries,
            diff={"added_entries": [new_entry.name], "candidate_id": candidate.candidate_id},
            evidence=[candidate.candidate_id] + candidate.supporting_experiences,
            promotion_decision=promoted_decision.model_dump(),
            evaluation_set=decision.gate_checks.details,
            created_by=approver,
            project_id=candidate.project_id,
            domain=candidate.domain,
            is_active=True,
        )

        # 4. Persist HarnessVersion and Decision
        self._memory_harness_versions[new_harness.version_id] = new_harness
        self._memory_decisions[promoted_decision.decision_id] = promoted_decision

        if self.harness_repo:
            await self.harness_repo.save_version(new_harness)
            await self.harness_repo.set_active_version(new_harness.version_id)

        if self.promotion_repo:
            await self.promotion_repo.save_decision(promoted_decision)

        logger.info(
            "Successfully promoted candidate %s into active harness version %s",
            candidate.candidate_id,
            new_harness.version_id,
        )

        return promoted_decision, new_harness

    async def monitor_and_rollback_if_regressed(
        self,
        current_version: HarnessVersion,
        decision: PromotionDecision,
        telemetry_runs: List[Dict[str, Any]],
    ) -> tuple[PostPromotionHealth, Optional[HarnessVersion]]:
        """Monitors post-promotion execution telemetry and automatically triggers rollback if regression detected."""
        health = self.rollback_coordinator.evaluate_post_promotion_health(
            version_id=current_version.version_id,
            execution_runs=telemetry_runs,
        )

        restored_parent = None
        if health.is_regression_detected:
            reason = health.regression_reason or "Detected post-promotion performance regression"
            _, restored_parent, updated_dec = await self.rollback_coordinator.execute_rollback(
                current_version=current_version,
                promotion_decision=decision,
                rollback_reason=reason,
            )
            self._memory_decisions[updated_dec.decision_id] = updated_dec

        return health, restored_parent

