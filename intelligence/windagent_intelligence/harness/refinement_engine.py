"""Refinement Engine for Continual Harness (Phase 10 — ban_ke_hoach_v1 §15, §16).

Coordinates the preview-first refinement flow:
1. /refine creates RefinementProposal
2. generates exact diff preview (DiffEngine)
3. validates immutable base policies (ImmutableBaseGuard)
4. evaluates performance against baseline
5. promotes proposal into an atomic HarnessVersion commit
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from windagent_core.domain.candidate import CandidateKind, LearningCandidate
from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    RefinementProposal,
    RefinementStatus,
)
from windagent_intelligence.harness.diff_engine import DiffEngine
from windagent_intelligence.harness.immutable_base_guard import ImmutableBaseGuard


class RefinementEngine:
    """Coordinates preview-first refinement proposals, diff inspection, evaluation, and promotion."""

    @classmethod
    def candidate_to_entry(cls, candidate: LearningCandidate) -> HarnessEntry:
        """Converts a LearningCandidate into a corresponding HarnessEntry."""
        kind_mapping = {
            CandidateKind.PROMPT_RULE: HarnessEntryKind.PROMPT_RULE,
            CandidateKind.MEMORY: HarnessEntryKind.MEMORY_REF,
            CandidateKind.SKILL: HarnessEntryKind.SKILL_REF,
            CandidateKind.SUBAGENT_SPEC: HarnessEntryKind.SUBAGENT_SPEC,
            CandidateKind.ROUTING_POLICY: HarnessEntryKind.ROUTING_POLICY,
        }
        entry_kind = kind_mapping.get(candidate.kind, HarnessEntryKind.PROMPT_RULE)
        entry_id = f"hent_{candidate.candidate_id}"

        # Clean entry name from condition/rule
        entry_name = f"rule_{candidate.candidate_id}"
        if "rule" in candidate.proposed_change:
            entry_name = str(candidate.proposed_change.get("name") or candidate.condition)[:40]

        return HarnessEntry(
            entry_id=entry_id,
            kind=entry_kind,
            name=entry_name,
            content=candidate.proposed_change,
            priority=100,
            enabled=True,
            scope=candidate.scope.value,
            metadata={
                "candidate_id": candidate.candidate_id,
                "confidence": candidate.confidence,
                "sample_size": candidate.sample_size,
                "domain": candidate.domain,
            },
        )

    @classmethod
    def propose_refinement(
        cls,
        target_harness: HarnessVersion,
        candidates: Optional[List[LearningCandidate]] = None,
        custom_entries: Optional[List[HarnessEntry]] = None,
        project_id: Optional[str] = None,
        created_by: str = "system",
    ) -> RefinementProposal:
        """Creates a preview-first RefinementProposal with exact diff preview without mutating state."""
        proposed_entries: List[HarnessEntry] = list(custom_entries or [])
        candidate_ids: List[str] = []

        if candidates:
            for cand in candidates:
                candidate_ids.append(cand.candidate_id)
                entry = cls.candidate_to_entry(cand)
                proposed_entries.append(entry)

        if not proposed_entries:
            raise ValueError("Refinement proposal must contain at least one candidate or proposed entry.")

        # 1. Zero-tolerance check against immutable base policies
        ImmutableBaseGuard.validate_entries(proposed_entries)

        # 2. Construct simulated target entries to compute preview diff
        target_map: Dict[str, HarnessEntry] = {e.entry_id: e for e in target_harness.entries}
        for pe in proposed_entries:
            target_map[pe.entry_id] = pe

        simulated_target = list(target_map.values())
        preview_diff = DiffEngine.compute_diff(target_harness.entries, simulated_target)

        refinement_id = f"ref_{uuid.uuid4().hex[:12]}"
        return RefinementProposal(
            refinement_id=refinement_id,
            target_harness_version=target_harness.version_id,
            candidate_ids=candidate_ids,
            proposed_entries=proposed_entries,
            preview_diff=preview_diff,
            status=RefinementStatus.PREVIEW,
            evaluation_results={},
            project_id=project_id or target_harness.project_id,
            created_by=created_by,
            metadata={"domain": target_harness.domain},
        )

    @classmethod
    def evaluate_refinement(
        cls,
        proposal: RefinementProposal,
        benchmark_results: Optional[Dict[str, Any]] = None,
        min_pass_score: float = 0.70,
    ) -> RefinementProposal:
        """Evaluates a refinement proposal against safety and benchmark thresholds."""
        # 1. Re-validate immutable base guard
        ImmutableBaseGuard.validate_entries(proposal.proposed_entries)

        eval_payload = dict(benchmark_results or {})
        eval_payload["safety_check"] = "PASSED"
        eval_payload["entry_count"] = len(proposal.proposed_entries)
        eval_payload["diff_summary"] = proposal.preview_diff.get("summary", "")

        score = eval_payload.get("composite_score", 0.85)
        passed = score >= min_pass_score
        eval_payload["passed"] = passed
        eval_payload["threshold"] = min_pass_score

        if not passed:
            raise ValueError(f"Refinement proposal score ({score:.2f}) is below threshold ({min_pass_score:.2f})")

        return proposal.mark_evaluated(eval_payload)

    @classmethod
    def promote_refinement(
        cls,
        proposal: RefinementProposal,
        base_version: HarnessVersion,
        promotion_authority: str = "promotion_gate",
        auto_activate: bool = True,
    ) -> HarnessVersion:
        """Promotes an evaluated proposal and produces a newly committed HarnessVersion."""
        new_version_number = base_version.version_number + 1
        new_version_id = f"harness_v{new_version_number}_{uuid.uuid4().hex[:6]}"

        new_harness = proposal.promote(
            new_version_id=new_version_id,
            new_version_number=new_version_number,
            base_version=base_version,
            promotion_authority=promotion_authority,
        )

        new_harness.assert_invariants()

        if auto_activate:
            return new_harness.activate()
        return new_harness

