"""Continual Harness Service (Phase 10 — ban_ke_hoach_v1 §15, §16).

High-level asynchronous service coordinating harness version resolution, preview-first
refinements, evaluations, promotions, rollbacks, and executable context assembly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from windagent_core.domain.candidate import LearningCandidate
from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessVersion,
    HarnessVersionStatus,
    RefinementProposal,
    RefinementStatus,
)
from windagent_core.contracts.repositories.harness_repository import (
    HarnessRepositoryProtocol,
)
from windagent_intelligence.harness.harness_assembler import AssembledHarnessContext, HarnessAssembler
from windagent_intelligence.harness.refinement_engine import RefinementEngine

logger = logging.getLogger("windagent.intelligence.harness.service")


class HarnessService:
    """Coordinates continual harness lifecycle, refinement proposals, and prompt assembly."""

    def __init__(self, repository: Optional[HarnessRepositoryProtocol] = None) -> None:
        self._repo = repository
        self._memory_versions: Dict[str, HarnessVersion] = {}
        self._memory_refinements: Dict[str, RefinementProposal] = {}

    def _create_baseline_v1(
        self,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> HarnessVersion:
        """Constructs an initial baseline HarnessVersion v1."""
        return HarnessVersion(
            version_id=f"harness_v1_{project_id or 'global'}",
            version_number=1,
            parent_version=None,
            status=HarnessVersionStatus.ACTIVE,
            entries=[],
            diff={"summary": "Initial baseline continual harness v1"},
            evidence=[],
            promotion_decision={"reason": "Baseline bootstrap"},
            evaluation_set={"composite_score": 1.0},
            created_by="system",
            project_id=project_id,
            domain=domain,
            is_active=True,
        )

    async def get_active_version(
        self,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> HarnessVersion:
        """Retrieves currently active HarnessVersion, initializing baseline v1 if none exists."""
        if self._repo:
            active = await self._repo.get_active_version(project_id=project_id, domain=domain)
            if active:
                return active

            baseline = self._create_baseline_v1(project_id=project_id, domain=domain)
            await self._repo.save_version(baseline)
            return baseline

        # In-memory fallback
        for v in self._memory_versions.values():
            if v.is_active and (not project_id or v.project_id == project_id):
                return v

        baseline = self._create_baseline_v1(project_id=project_id, domain=domain)
        self._memory_versions[baseline.version_id] = baseline
        return baseline

    async def get_version_by_id(self, version_id: str) -> Optional[HarnessVersion]:
        """Retrieves a HarnessVersion by ID."""
        if self._repo:
            return await self._repo.get_version_by_id(version_id)
        return self._memory_versions.get(version_id)

    async def propose_refinement(
        self,
        target_version_id: Optional[str] = None,
        candidates: Optional[List[LearningCandidate]] = None,
        custom_entries: Optional[List[HarnessEntry]] = None,
        project_id: Optional[str] = None,
        created_by: str = "system",
    ) -> RefinementProposal:
        """Creates a preview-first RefinementProposal with exact diff preview."""
        if target_version_id:
            target_version = await self.get_version_by_id(target_version_id)
            if not target_version:
                raise ValueError(f"Target harness version {target_version_id} not found.")
        else:
            target_version = await self.get_active_version(project_id=project_id)

        proposal = RefinementEngine.propose_refinement(
            target_harness=target_version,
            candidates=candidates,
            custom_entries=custom_entries,
            project_id=project_id,
            created_by=created_by,
        )

        if self._repo:
            await self._repo.save_refinement(proposal)
        else:
            self._memory_refinements[proposal.refinement_id] = proposal

        return proposal

    async def evaluate_refinement(
        self,
        refinement_id: str,
        benchmark_results: Optional[Dict[str, Any]] = None,
        min_pass_score: float = 0.70,
    ) -> RefinementProposal:
        """Evaluates a refinement proposal against safety and benchmark scores."""
        if self._repo:
            proposal = await self._repo.get_refinement_by_id(refinement_id)
        else:
            proposal = self._memory_refinements.get(refinement_id)

        if not proposal:
            raise ValueError(f"Refinement proposal {refinement_id} not found.")

        evaluated = RefinementEngine.evaluate_refinement(
            proposal=proposal,
            benchmark_results=benchmark_results,
            min_pass_score=min_pass_score,
        )

        if self._repo:
            await self._repo.update_refinement_status(
                refinement_id=refinement_id,
                new_status=RefinementStatus.EVALUATED,
                eval_results=evaluated.evaluation_results,
            )
        else:
            self._memory_refinements[refinement_id] = evaluated

        return evaluated

    async def promote_refinement(
        self,
        refinement_id: str,
        promotion_authority: str = "promotion_gate",
        auto_activate: bool = True,
    ) -> HarnessVersion:
        """Promotes an evaluated proposal and produces a newly active HarnessVersion commit."""
        if self._repo:
            proposal = await self._repo.get_refinement_by_id(refinement_id)
        else:
            proposal = self._memory_refinements.get(refinement_id)

        if not proposal:
            raise ValueError(f"Refinement proposal {refinement_id} not found.")

        base_version = await self.get_version_by_id(proposal.target_harness_version)
        if not base_version:
            raise ValueError(f"Base harness version {proposal.target_harness_version} not found.")

        new_version = RefinementEngine.promote_refinement(
            proposal=proposal,
            base_version=base_version,
            promotion_authority=promotion_authority,
            auto_activate=auto_activate,
        )

        if self._repo:
            await self._repo.save_version(new_version)
            if auto_activate:
                await self._repo.set_active_version(new_version.version_id, project_id=new_version.project_id)
            await self._repo.update_refinement_status(
                refinement_id=refinement_id,
                new_status=RefinementStatus.PROMOTED,
            )
        else:
            if auto_activate:
                for v in self._memory_versions.values():
                    if v.is_active and v.project_id == new_version.project_id:
                        self._memory_versions[v.version_id] = v.archive()
            self._memory_versions[new_version.version_id] = new_version
            self._memory_refinements[refinement_id] = proposal.model_copy(
                update={"status": RefinementStatus.PROMOTED}
            )

        return new_version

    async def rollback_version(
        self,
        version_id: str,
        reason: str,
    ) -> HarnessVersion:
        """Rolls back a harness version due to detected regression and reinstates parent version."""
        if self._repo:
            return await self._repo.rollback_version(version_id=version_id, reason=reason, fallback_to_parent=True)

        target = self._memory_versions.get(version_id)
        if not target:
            raise ValueError(f"Harness version {version_id} not found.")

        rolled_back = target.rollback(reason=reason)
        self._memory_versions[version_id] = rolled_back

        if target.parent_version and target.parent_version in self._memory_versions:
            parent = self._memory_versions[target.parent_version].activate()
            self._memory_versions[target.parent_version] = parent

        return rolled_back

    async def assemble_context(
        self,
        version_id: Optional[str] = None,
        base_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> AssembledHarnessContext:
        """Assembles base prompt with target (or active) harness version into runtime context."""
        if version_id:
            harness = await self.get_version_by_id(version_id)
            if not harness:
                raise ValueError(f"Harness version {version_id} not found.")
        else:
            harness = await self.get_active_version(project_id=project_id, domain=domain)

        return HarnessAssembler.assemble(
            base_prompt=base_prompt,
            harness_version=harness,
            project_id=project_id,
            domain=domain,
        )

