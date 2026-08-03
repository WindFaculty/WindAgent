"""
Phase 14 — Candidate review & approval (plan 04 §18.4).

Approval fails CLOSED:

- deterministic file validity is checked BEFORE any VLM scoring;
- a character master (CREATE_CHARACTER_REFERENCE) is ALWAYS human-approved
  in Release 0.1 — never auto-approved;
- a rejected candidate keeps its reason and evidence and is never
  auto-bound to the package;
- re-generation creates a new attempt/job while keeping the causal link
  (handled by `FlowJobRegistry.next_attempt`).

`VlmReviewPort` is a port: tests inject a deterministic fake; a real VLM
adapter lives outside the tools boundary and is wired later.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, runtime_checkable

from windagent_tools.google_flow.candidate_downloader import CandidateAcquisition
from windagent_tools.google_flow.image_operations import (
    FlowImageOperation,
    FlowImageRequest,
)


class ReviewDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"


@dataclass(frozen=True)
class VlmScores:
    """Multi-dimensional VLM scores (never a single number)."""

    prompt_compliance: float = 0.0
    identity: float = 0.0


@runtime_checkable
class VlmReviewPort(Protocol):
    """Scores prompt compliance + identity for a candidate."""

    async def score(
        self,
        *,
        candidate: CandidateAcquisition,
        request: FlowImageRequest,
    ) -> VlmScores:
        ...


@dataclass(frozen=True)
class CandidateReview:
    """Fail-closed review verdict with reason + evidence."""

    candidate_id: str
    decision: ReviewDecision
    reason: str
    deterministic_valid: bool
    character_master: bool
    vlm_scores: VlmScores
    reviewed_at: float


class ReviewGate:
    """Approval gate: deterministic validity first, VLM second, human last."""

    def __init__(
        self,
        *,
        clock: Optional[callable] = None,
        compliance_threshold: float = 0.6,
        identity_threshold: float = 0.6,
    ) -> None:
        self._clock = clock or time.time
        self.compliance_threshold = compliance_threshold
        self.identity_threshold = identity_threshold

    # ------------------------------------------------------------------
    async def review(
        self,
        *,
        candidate: CandidateAcquisition,
        request: FlowImageRequest,
        vlm: Optional[VlmReviewPort],
        deterministic_valid: bool,
    ) -> CandidateReview:
        """Produce a fail-closed review for one candidate (§18.4)."""
        character_master = (
            request.operation == FlowImageOperation.CREATE_CHARACTER_REFERENCE
        )

        # 1. Deterministic file validity BEFORE any VLM scoring.
        if not deterministic_valid or not candidate.published:
            return CandidateReview(
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.REJECTED,
                reason="deterministic file validation failed or not published",
                deterministic_valid=deterministic_valid and candidate.published,
                character_master=character_master,
                vlm_scores=VlmScores(),
                reviewed_at=self._clock(),
            )

        # 2. Character master always needs human approval in Release 0.1 —
        #    checked BEFORE VLM scoring (no wasted scoring, §18.4).
        if character_master:
            return CandidateReview(
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.REQUIRES_HUMAN,
                reason="character master requires human approval (Release 0.1)",
                deterministic_valid=True,
                character_master=True,
                vlm_scores=VlmScores(),
                reviewed_at=self._clock(),
            )

        # 3. VLM scoring (after validity + character-master gates).
        scores = VlmScores()
        if vlm is not None:
            scores = await vlm.score(candidate=candidate, request=request)

        # 4. VLM low confidence → human review, never auto-approve.
        if scores.prompt_compliance < self.compliance_threshold or (
            scores.identity < self.identity_threshold
        ):
            return CandidateReview(
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.REQUIRES_HUMAN,
                reason="VLM confidence below threshold",
                deterministic_valid=True,
                character_master=False,
                vlm_scores=scores,
                reviewed_at=self._clock(),
            )

        # 5. High-confidence + not character master → approved for the
        #    revision (binding still happens explicitly, not auto-bound).
        return CandidateReview(
            candidate_id=candidate.candidate_id,
            decision=ReviewDecision.APPROVED,
            reason="deterministic validation + VLM confidence above threshold",
            deterministic_valid=True,
            character_master=False,
            vlm_scores=scores,
            reviewed_at=self._clock(),
        )


__all__ = [
    "CandidateReview",
    "ReviewDecision",
    "ReviewGate",
    "VlmReviewPort",
    "VlmScores",
]
