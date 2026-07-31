"""
QualityReviewPort — canonical contract for reviewing generation candidates.

Reviewers evaluate multiple dimensions (technical validity, prompt
compliance, identity consistency, continuity, motion quality, safety) and
never collapse to a single score (road_map.md Phase 20).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from windagent_core.domain.video_production.approval import ReviewResult
from windagent_core.domain.video_production.generation_job import GenerationCandidate
from windagent_core.domain.video_production.ids import ReviewResultId


@runtime_checkable
class QualityReviewPort(Protocol):
    """Port for reviewing generation candidates."""

    async def review_candidate(self, candidate: GenerationCandidate) -> ReviewResult:
        """Review a candidate and produce a multi-dimensional verdict."""
        ...

    async def get_review(self, review_id: ReviewResultId) -> ReviewResult:
        """Fetch a previously recorded review."""
        ...


__all__ = ["QualityReviewPort"]
