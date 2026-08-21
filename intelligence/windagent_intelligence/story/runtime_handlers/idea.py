"""Plan B B3 runtime task handlers: ``studio.story.idea.generate`` / ``.evaluate``.

Handlers are thin application services over the pure pipeline services:
they map one frozen ``StudioTaskType`` to a typed input/output pair, exactly
as ``story_task_io.json`` declares. They never touch storage, queue, or
provider infrastructure directly (B9 wires them into A's worker seam through
ports/UoW); the only external dependency is the provider-neutral model port,
crossed exclusively through ``StoryModelBoundary``.

Selection is NOT a handler: it remains an A command bound to the candidate
set hash/revision (``SelectIdeaCommand``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.ideation import CreativeBrief, IdeaCandidateSet
from windagent_intelligence.story.ideation.service import (
    IdeaEvaluationResult,
    IdeaEvaluationService,
    IdeaGenerationResult,
    IdeaGenerationService,
)
from windagent_intelligence.story.prompts import StoryModelBoundary
from windagent_intelligence.video.ports import PreproductionModelPort

__all__ = [
    "IdeaGenerateHandler",
    "IdeaEvaluateHandler",
    "HANDLER_REGISTRY",
    "registered_story_task_types",
]


class IdeaGenerateHandler:
    """Handler for ``studio.story.idea.generate`` (CreativeBrief -> IdeaCandidateSet)."""

    task_type = StudioTaskType.IDEA_GENERATE

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        boundary = StoryModelBoundary(model_port, registry=registry)
        self.service = IdeaGenerationService(boundary)

    async def handle(
        self,
        brief: CreativeBrief,
        *,
        normalize: bool = True,
        target_count: int = 4,
        route_lock_id: Optional[str] = None,
    ) -> IdeaGenerationResult:
        return await self.service.generate(
            brief,
            normalize=normalize,
            target_count=target_count,
            route_lock_id=route_lock_id,
        )


class IdeaEvaluateHandler:
    """Handler for ``studio.story.idea.evaluate`` (IdeaCandidateSet -> scored set)."""

    task_type = StudioTaskType.IDEA_EVALUATE

    def __init__(
        self,
        *,
        selection_policy: str = "AUTO_WHEN_POLICY_ALLOWS",
    ) -> None:
        self.service = IdeaEvaluationService(selection_policy=selection_policy)

    def handle(
        self,
        brief: CreativeBrief,
        candidate_set: IdeaCandidateSet,
        *,
        model_values: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> IdeaEvaluationResult:
        return self.service.evaluate(brief, candidate_set, model_values=model_values)


#: B3 handler surface: task type -> handler class (B9 instantiates per task).
HANDLER_REGISTRY: Dict[StudioTaskType, Any] = {
    StudioTaskType.IDEA_GENERATE: IdeaGenerateHandler,
    StudioTaskType.IDEA_EVALUATE: IdeaEvaluateHandler,
}


def registered_story_task_types() -> list[str]:
    return sorted(t.value for t in HANDLER_REGISTRY)
