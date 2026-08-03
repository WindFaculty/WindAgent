"""
Candidate selection (plan 05 Phase 20 §25.5,
gate VP20_GENERATION_REVIEW_VERIFIED).

Ranking + selection rules:

- rank ONLY among candidates that are NOT blocked and NOT error
  (a candidate with a blocking defect or a review error is never ranked);
- the ranking is DETERMINISTIC and ORDER-INDEPENDENT: input candidate order
  never changes the selected result (plan §26 "candidate ordering không ảnh
  hưởng selected result") — ties break on candidate id;
- the selection record carries the algorithm + policy versions and the
  reason (gate condition 4: selection/rejection truy được về policy, model
  và evidence);
- human selection/override is audited (actor, decision, reason, timestamp);
- a REJECTED candidate keeps its evidence; a retry proposal records which
  defect to fix and which request field changes (plan §25.5).
"""

from __future__ import annotations

from typing import List, Optional

from windagent_intelligence.video.reviewers.models import (
    CandidateReview,
    CandidateVerdict,
    HumanSelectionOverride,
    RetryProposal,
    SelectionRecord,
)

SELECTION_ALGORITHM_VERSION = "1.0.0"

# Defect -> request field change suggestion (§25.5 retry proposal).
_DEFECT_FIELD_CHANGES = {
    "MEDIA_DECODE_FAILURE": ("generation.duration", "generation.mode"),
    "MISSING_VIDEO_STREAM": ("generation.mode", "generation.parameters"),
    "INVALID_DURATION": ("generation.duration",),
    "MISSING_MEDIA_METADATA": ("generation.parameters", "generation.mode"),
    "BLACK_ENDING": ("generation.duration", "generation.parameters"),
    "TRUNCATED_ENDING": ("generation.duration", "generation.parameters"),
    "MISSING_PROVENANCE": ("metadata.provenance",),
    "SAFETY_FINDING": ("prompt.negative_constraints",),
    "PROMPT_COMPLIANCE": ("prompt.composition", "prompt.action"),
    "IDENTITY_MISMATCH": ("references.identity", "prompt.identity"),
    "LOCATION_MISMATCH": ("references.location", "prompt.location"),
    "PROP_MISMATCH": ("references.props", "prompt.props"),
    "CAMERA_SIDE_VIOLATION": ("prompt.camera", "continuity.camera_side"),
    "SCREEN_DIRECTION_FLIP": ("prompt.camera", "continuity.screen_direction"),
    "WARDROBE_MISMATCH": ("prompt.appearance", "continuity.wardrobe"),
    "LIGHTING_MISMATCH": ("prompt.lighting", "continuity.lighting"),
    "TAIL_HEAD_FRAME_RELATION": ("references.tail_frame", "references.first_frame"),
    "CONTINUITY_VIOLATION": ("continuity.ledger", "prompt.continuity"),
    "VISUAL_ARTIFACT": ("generation.parameters", "prompt.negative_constraints"),
    "LOW_CONFIDENCE": ("review.retry",),
    "REVIEW_ERROR": ("review.retry",),
}


class CandidateSelector:
    """Deterministic, order-independent candidate selection (§25.5)."""

    def __init__(self, algorithm_version: str = SELECTION_ALGORITHM_VERSION) -> None:
        self.algorithm_version = algorithm_version

    def select(
        self,
        *,
        run_id: str,
        reviews: List[CandidateReview],
        human_override: Optional[HumanSelectionOverride] = None,
        policy_version: str,
        reviewed_at: float = 0.0,
    ) -> SelectionRecord:
        """Select among unblocked candidates; audited human override wins.

        `reviews` is treated as an unordered set: ranking depends only on the
        review contents, never on the input list order (ties -> candidate id).
        """
        by_id = {r.candidate_id: r for r in reviews}
        all_ids = tuple(sorted(by_id))

        eligible = [
            r for r in reviews
            if r.verdict == CandidateVerdict.APPROVE
        ]

        # Deterministic rank: (average score DESC, candidate id ASC).
        ranked = sorted(
            (r.candidate_id for r in eligible),
            key=lambda cid: (-by_id[cid].average_score(), cid),
        )

        selected_id: Optional[str] = None
        reason = "no approvable candidate"
        if human_override is not None:
            # Audited human override: actor, decision, reason, timestamp.
            target = by_id.get(human_override.candidate_id)
            if target is not None and human_override.decision == CandidateVerdict.APPROVE:
                selected_id = human_override.candidate_id
                reason = f"human override by {human_override.actor}: {human_override.reason}"
        elif ranked:
            selected_id = ranked[0]
            reason = f"top-ranked unblocked candidate (avg score {by_id[selected_id].average_score():.3f})"

        retry_proposals = tuple(
            self.retry_proposal(r) for r in reviews if r.verdict == CandidateVerdict.REJECT
        )

        return SelectionRecord(
            selection_id=f"sel_{run_id}",
            run_id=run_id,
            candidates_reviewed=all_ids,
            ranked=tuple(ranked),
            selected_candidate_id=selected_id,
            algorithm_version=self.algorithm_version,
            policy_version=policy_version,
            reason=reason,
            human_override=human_override,
            retry_proposals=retry_proposals,
            reviewed_at=reviewed_at,
        )

    def retry_proposal(self, review: CandidateReview) -> RetryProposal:
        """Propose which defects to fix + which request fields change (§25.5).

        Rejected candidates keep their evidence (the full review is the
        proposal's source); the proposal names the exact fields to change.
        """
        defects = tuple(review.blocking_defects)
        fields: List[str] = []
        for defect in defects:
            for change in _DEFECT_FIELD_CHANGES.get(defect.code.value, ("review.retry",)):
                if change not in fields:
                    fields.append(change)
        return RetryProposal(
            candidate_id=review.candidate_id,
            defects=defects,
            request_field_changes=tuple(fields),
            reason=review.reason,
        )


__all__ = ["SELECTION_ALGORITHM_VERSION", "CandidateSelector"]
