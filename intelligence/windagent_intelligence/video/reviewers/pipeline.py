"""
Review pipeline orchestrator (plan 05 Phase 20 §24, §25,
gate VP20_GENERATION_REVIEW_VERIFIED).

Enforces the reviewer hierarchy IN ORDER:

    deterministic validation (media/file/safety facts)
        ↓
    single-candidate VLM scoring — ONLY when the file decodes and the video
        stream exists (§24 "Không chạy VLM nếu file không decode hoặc thiếu
        video stream")
        ↓
    cross-shot / reference comparison (via the Phase 10 continuity ledger)
        ↓
    verdict policy (blocking defect always wins; low confidence -> human)
        ↓
    candidate selection (rank unblocked only; audited human override)

Fail-closed guarantees:

- gate condition 1: a deterministic failure (decode / missing video stream /
  invalid hash / black / truncated / provenance / safety) is recorded as a
  blocking defect BEFORE any VLM/human score exists — the verdict REJECTs, so
  a VLM/human score can never mask a deterministic failure;
- VLM review_error (timeout / invalid JSON / schema violation) is never a PASS;
- cross-shot review is skipped when no continuity ledger is provided, but is
  REQUIRED when one is (gate condition 5: cross-shot review dùng continuity
  ledger).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from windagent_intelligence.video.reviewers.cross_shot import CrossShotReviewer
from windagent_intelligence.video.reviewers.deterministic import DeterministicReviewer
from windagent_intelligence.video.reviewers.selection import CandidateSelector
from windagent_intelligence.video.reviewers.verdict import VerdictPolicy
from windagent_intelligence.video.reviewers.vlm import (
    VlmReviewRequest,
    VlmReviewer,
)

if TYPE_CHECKING:  # annotation-only imports (never evaluated at runtime)
    from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
    from windagent_intelligence.video.reviewers.cross_shot import CrossShotReviewResult
    from windagent_intelligence.video.reviewers.deterministic import (
        DeterministicReviewResult,
        MediaProbeFacts,
    )
    from windagent_intelligence.video.reviewers.models import (
        BlockingDefect,
        CandidateReview,
        DimensionResult,
        HumanSelectionOverride,
        SelectionRecord,
    )
    from windagent_intelligence.video.reviewers.vlm import (
        ReviewModelPort,
        VlmReviewOutcome,
    )


@dataclass(frozen=True)
class CandidateReviewReceipt:
    """Immutable result of the full review pipeline for ONE candidate."""

    review: CandidateReview
    deterministic: Optional["DeterministicReviewResult"] = None
    vlm: Optional["VlmReviewOutcome"] = None
    cross_shot: Optional["CrossShotReviewResult"] = None
    pipeline_version: str = "1.0.0"

    def to_dict(self) -> Dict:
        data: Dict = {
            "review": self.review.to_dict(),
            "pipeline_version": self.pipeline_version,
        }
        if self.deterministic is not None:
            data["deterministic"] = self.deterministic.to_dict()
        if self.vlm is not None:
            data["vlm"] = self.vlm.to_dict()
        if self.cross_shot is not None:
            data["cross_shot"] = self.cross_shot.to_dict()
        return data


class ReviewPipeline:
    """Orchestrates the multi-tier reviewer hierarchy (plan §24)."""

    def __init__(
        self,
        *,
        deterministic: DeterministicReviewer,
        vlm: VlmReviewer,
        cross_shot: CrossShotReviewer,
        verdict: VerdictPolicy,
        selector: CandidateSelector,
        pipeline_version: str = "1.0.0",
    ) -> None:
        self.deterministic = deterministic
        self.vlm = vlm
        self.cross_shot = cross_shot
        self.verdict = verdict
        self.selector = selector
        self.pipeline_version = pipeline_version

    # -- single candidate ---------------------------------------------------
    def review_candidate(
        self,
        *,
        candidate_id: str,
        request_hash: str,
        shot_id: str,
        media_facts: MediaProbeFacts,
        model_port: ReviewModelPort,
        intent_prompt: str = "",
        reference_hashes: Optional[Tuple[str, ...]] = None,
        media_uri: str = "",
        ledger_receipt: Optional[ContinuityLedgerReceipt] = None,
        reviewed_at: float = 0.0,
    ) -> CandidateReviewReceipt:
        """Run the hierarchy for one candidate (deterministic -> VLM -> cross-shot -> verdict)."""
        dimensions: List[DimensionResult] = []
        defects: List[BlockingDefect] = []

        # Tier 1 — deterministic gate (§25.1).
        det = self.deterministic.review(candidate_id, media_facts)
        dimensions.extend(det.dimension_results)
        defects.extend(det.blocking_defects)

        # Tier 2 — VLM only when the deterministic gate allows (§24).
        vlm_outcome = None
        if det.technical_valid:
            vlm_outcome = self.vlm.review(
                model_port,
                VlmReviewRequest(
                    candidate_id=candidate_id,
                    media_uri=media_uri,
                    intent_prompt=intent_prompt,
                    reference_hashes=tuple(reference_hashes or ()),
                ),
            )
            dimensions.extend(vlm_outcome.dimension_results)
            defects.extend(vlm_outcome.blocking_defects)
        # When the gate blocked, VLM is skipped; the deterministic blocking
        # defect already guarantees the verdict cannot be masked (§24).

        # Tier 3 — cross-shot via the continuity ledger (§25.3, gate cond. 5).
        cross_shot_outcome = None
        if ledger_receipt is not None:
            cross_shot_outcome = self.cross_shot.review(candidate_id, ledger_receipt)
            dimensions.extend(cross_shot_outcome.dimension_results)
            defects.extend(cross_shot_outcome.blocking_defects)

        # Tier 4 — verdict policy (§25.4).
        review = self.verdict.decide(
            candidate_id=candidate_id,
            request_hash=request_hash,
            shot_id=shot_id,
            dimensions=tuple(dimensions),
            blocking_defects=tuple(defects),
            reviewed_at=reviewed_at,
        )

        return CandidateReviewReceipt(
            review=review,
            deterministic=det,
            vlm=vlm_outcome,
            cross_shot=cross_shot_outcome,
            pipeline_version=self.pipeline_version,
        )

    # -- selection ----------------------------------------------------------
    def select(
        self,
        *,
        run_id: str,
        receipts: List[CandidateReviewReceipt],
        human_override: Optional[HumanSelectionOverride] = None,
        reviewed_at: float = 0.0,
    ) -> SelectionRecord:
        """Rank unblocked candidates + produce retry proposals (§25.5)."""
        reviews = [r.review for r in receipts]
        return self.selector.select(
            run_id=run_id,
            reviews=reviews,
            human_override=human_override,
            policy_version=self.verdict.policy_version,
            reviewed_at=reviewed_at,
        )


__all__ = ["CandidateReviewReceipt", "ReviewPipeline"]
