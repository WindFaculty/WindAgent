"""Plan B B5 runtime task handlers: ``studio.story.beats.generate`` /
``studio.story.outline.generate``.

Thin application services over the pure outline pipeline, exactly as
``story_task_io.json`` declares (canon set -> BeatSheet; BeatSheet ->
EpisodeOutline). Never touches persistence, workflows, or provider
infrastructure directly; the only external dependency is the provider-neutral
model port, crossed exclusively through ``StoryModelBoundary``. Approval of
the outline is an A checkpoint command, not these handlers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.bibles import CharacterCanon, StoryBible, WorldBible
from windagent_core.domain.story.outline import BeatSheet
from windagent_intelligence.story.outline.service import (
    BeatGenerationResult,
    BeatGenerationService,
    OutlineGenerationResult,
    OutlineGenerationService,
)
from windagent_intelligence.story.prompts import StoryModelBoundary
from windagent_intelligence.video.ports import PreproductionModelPort

__all__ = [
    "BeatGenerateHandler",
    "OutlineGenerateHandler",
    "OUTLINE_HANDLER_REGISTRY",
]


class BeatGenerateHandler:
    """Handler for ``studio.story.beats.generate`` (canon set -> BeatSheet)."""

    task_type = StudioTaskType.BEATS_GENERATE

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = BeatGenerationService(boundary)

    async def handle(
        self,
        story_bible: StoryBible,
        world_bible: WorldBible,
        character_canon: CharacterCanon,
        *,
        target_duration_seconds: int = 240,
        language: str = "vi",
        route_lock_id: Optional[str] = None,
    ) -> BeatGenerationResult:
        return await self.service.generate(
            story_bible,
            world_bible,
            character_canon,
            target_duration_seconds=target_duration_seconds,
            language=language,
            route_lock_id=route_lock_id,
        )


class OutlineGenerateHandler:
    """Handler for ``studio.story.outline.generate`` (BeatSheet -> EpisodeOutline)."""

    task_type = StudioTaskType.OUTLINE_GENERATE

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = OutlineGenerationService(boundary)

    async def handle(
        self,
        beat_sheet: BeatSheet,
        *,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        target_duration_seconds: Optional[int] = None,
        language: str = "vi",
        audience_band: str = "5-8",
        route_lock_id: Optional[str] = None,
    ) -> OutlineGenerationResult:
        return await self.service.generate(
            beat_sheet,
            canon=canon,
            world=world,
            target_duration_seconds=target_duration_seconds,
            language=language,
            audience_band=audience_band,
            route_lock_id=route_lock_id,
        )


#: B5 handler surface: task type -> handler class (B9 instantiates per task).
OUTLINE_HANDLER_REGISTRY: Dict[StudioTaskType, Any] = {
    StudioTaskType.BEATS_GENERATE: BeatGenerateHandler,
    StudioTaskType.OUTLINE_GENERATE: OutlineGenerateHandler,
}
