"""Plan B B6 runtime task handler: ``studio.story.screenplay.generate``.

Thin application service over the pure screenplay pipeline, exactly as
``story_task_io.json`` declares (EpisodeOutline -> ScreenplayDraft; canonical
text is a derived view). Never touches persistence, task execution
infrastructure, or provider internals directly; the only external dependency
is the provider-neutral model port, crossed exclusively through
``StoryModelBoundary``. Approval/lock of the draft are A checkpoint commands,
not this handler.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.bibles import CharacterCanon, WorldBible
from windagent_core.domain.story.outline import BeatSheet, EpisodeOutline
from windagent_intelligence.story.prompts import StoryModelBoundary
from windagent_intelligence.story.screenplay.service import (
    ScreenplayGenerationResult,
    ScreenplayGenerationService,
)
from windagent_intelligence.video.ports import PreproductionModelPort

__all__ = [
    "ScreenplayGenerateHandler",
    "SCREENPLAY_HANDLER_REGISTRY",
]


class ScreenplayGenerateHandler:
    """Handler for ``studio.story.screenplay.generate`` (EpisodeOutline -> ScreenplayDraft)."""

    task_type = StudioTaskType.SCREENPLAY_GENERATE

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = ScreenplayGenerationService(boundary)

    async def handle(
        self,
        episode_outline: EpisodeOutline,
        *,
        beat_sheet: Optional[BeatSheet] = None,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        target_duration_seconds: Optional[int] = None,
        language: str = "vi",
        audience_band: str = "5-8",
        route_lock_id: Optional[str] = None,
    ) -> ScreenplayGenerationResult:
        return await self.service.generate(
            episode_outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
            target_duration_seconds=target_duration_seconds,
            language=language,
            audience_band=audience_band,
            route_lock_id=route_lock_id,
        )


#: B6 handler surface: task type -> handler class (B9 instantiates per task).
SCREENPLAY_HANDLER_REGISTRY: Dict[StudioTaskType, Any] = {
    StudioTaskType.SCREENPLAY_GENERATE: ScreenplayGenerateHandler,
}
