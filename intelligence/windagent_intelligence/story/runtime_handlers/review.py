"""Plan B B7 runtime task handlers: ``studio.story.review`` / ``studio.story.revise``.

Thin application services over the pure review/revision pipeline, exactly as
``story_task_io.json`` declares (ScreenplayDraft -> ReviewReport;
ScreenplayDraft + ReviewReport -> RevisionProposal + ScreenplayDraft). Never
touches persistence, task execution infrastructure, or provider internals
directly; the only external dependency is the provider-neutral model port,
crossed exclusively through ``StoryModelBoundary``. Approval/lock of the
draft are A checkpoint commands, not these handlers; the revision budget
stops the loop deterministically, separate from provider retries.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.bibles import CharacterCanon, WorldBible
from windagent_core.domain.story.outline import BeatSheet, EpisodeOutline
from windagent_core.domain.story.review import ReviewReport
from windagent_core.domain.story.screenplay import ScreenplayDraft
from windagent_intelligence.story.prompts import StoryModelBoundary
from windagent_intelligence.story.review.service import (
    ReviewResult,
    ReviewService,
    RevisionResult,
    ReviseService,
)
from windagent_intelligence.video.ports import PreproductionModelPort

__all__ = [
    "ReviewHandler",
    "ReviseHandler",
    "REVIEW_HANDLER_REGISTRY",
]


class ReviewHandler:
    """Handler for ``studio.story.review`` (ScreenplayDraft -> ReviewReport)."""

    task_type = StudioTaskType.REVIEW

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = ReviewService(boundary)

    async def handle(
        self,
        draft: ScreenplayDraft,
        *,
        outline: Optional[EpisodeOutline] = None,
        beat_sheet: Optional[BeatSheet] = None,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        review_iteration: int = 1,
        maximum_iterations: int = 3,
        route_lock_id: Optional[str] = None,
    ) -> ReviewResult:
        return await self.service.generate(
            draft,
            outline=outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
            review_iteration=review_iteration,
            maximum_iterations=maximum_iterations,
            route_lock_id=route_lock_id,
        )


class ReviseHandler:
    """Handler for ``studio.story.revise`` (Draft + Report -> Proposal + new Draft)."""

    task_type = StudioTaskType.REVISE

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = ReviseService(boundary)

    async def handle(
        self,
        draft: ScreenplayDraft,
        report: ReviewReport,
        *,
        outline: Optional[EpisodeOutline] = None,
        beat_sheet: Optional[BeatSheet] = None,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        language: str = "vi",
        audience_band: str = "5-8",
        route_lock_id: Optional[str] = None,
    ) -> RevisionResult:
        return await self.service.generate(
            draft,
            report,
            outline=outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
            language=language,
            audience_band=audience_band,
            route_lock_id=route_lock_id,
        )


#: B7 handler surface: task type -> handler class (B9 instantiates per task).
REVIEW_HANDLER_REGISTRY: Dict[StudioTaskType, Any] = {
    StudioTaskType.REVIEW: ReviewHandler,
    StudioTaskType.REVISE: ReviseHandler,
}
