"""Plan B B4 runtime task handler: ``studio.story.bible.generate``.

Thin application service over the pure canon pipeline: maps the frozen
``StudioTaskType.BIBLE_GENERATE`` to its typed input/output pair, exactly as
``story_task_io.json`` declares (SelectedIdea -> StoryBible + WorldBible +
CharacterCanon). Never touches persistence, workflows, or provider
infrastructure directly; the only external dependency is the provider-neutral
model port, crossed exclusively through ``StoryModelBoundary``. Approval of
the generated set is an A checkpoint command, not this handler.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.ideation import CreativeBrief, SelectedIdea
from windagent_intelligence.story.bibles.service import (
    BibleGenerationResult,
    BibleGenerationService,
)
from windagent_intelligence.story.prompts import StoryModelBoundary
from windagent_intelligence.video.ports import PreproductionModelPort

__all__ = [
    "BibleGenerateHandler",
    "BIBLE_HANDLER_REGISTRY",
]


class BibleGenerateHandler:
    """Handler for ``studio.story.bible.generate`` (SelectedIdea -> canon set)."""

    task_type = StudioTaskType.BIBLE_GENERATE

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = BibleGenerationService(boundary)

    async def handle(
        self,
        selected_idea: SelectedIdea,
        *,
        brief: Optional[CreativeBrief] = None,
        language: Optional[str] = None,
        audience_min_age: Optional[int] = None,
        audience_max_age: Optional[int] = None,
        route_lock_id: Optional[str] = None,
    ) -> BibleGenerationResult:
        """Generate the canon set; the brief (when present) supplies
        language/audience context the frozen SelectedIdea does not carry."""
        if language is None:
            language = brief.language if brief is not None else "vi"
        if audience_min_age is None:
            audience_min_age = brief.audience_min_age if brief is not None else 5
        if audience_max_age is None:
            audience_max_age = brief.audience_max_age if brief is not None else 8
        return await self.service.generate(
            selected_idea,
            language=language,
            audience_min_age=audience_min_age,
            audience_max_age=audience_max_age,
            route_lock_id=route_lock_id,
        )


#: B4 handler surface: task type -> handler class (B9 instantiates per task).
BIBLE_HANDLER_REGISTRY: Dict[StudioTaskType, Any] = {
    StudioTaskType.BIBLE_GENERATE: BibleGenerateHandler,
}
