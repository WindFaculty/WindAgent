"""
StoryOutliner (Phase 6 slice 2) — story outline from a creative brief.

Produces a canonical `StoryConcept` (premise, synopsis, themes) with fully
sorted themes for determinism (fixes NONDET-005 ordering). Provider responses
are parsed with typed failures (fixes DEF-001).
"""

from __future__ import annotations

from typing import Optional

from windagent_core.domain.video_production.ids import StoryConceptId
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    StoryConcept,
)

from windagent_intelligence.video.errors import (
    EmptyResponseError,
    ResponseParseError,
)
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import parse_json_contract
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec

OUTLINE_PROMPT_V1 = PromptSpec(
    capability="story_outline",
    version="1.0.0",
    description="Turn a creative brief into a story outline JSON.",
    template=(
        "You are a story developer.\n"
        'Respond ONLY with a JSON object with keys: "title", "premise", '
        '"synopsis", "themes" (array of strings), "beats" (array of strings).\n\n'
        "BRIEF:\n{brief_json}"
    ),
)


class StoryOutliner:
    """Builds a StoryConcept outline from a CreativeBrief."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        id_factory: Optional[StableIdFactory] = None,
        canonical_model: str = "canonical-default",
        prompt_spec: PromptSpec = OUTLINE_PROMPT_V1,
    ) -> None:
        self.model_port = model_port
        self.id_factory = id_factory or StableIdFactory()
        self.canonical_model = canonical_model
        self.prompt_spec = prompt_spec

    async def outline(self, brief: CreativeBrief) -> dict:
        """Return {concept, beats, prompt_version, prompt_hash, capability}."""
        from pydantic import TypeAdapter

        brief_json = TypeAdapter(CreativeBrief).dump_json(brief).decode("utf-8")
        rendered = self.prompt_spec.render(brief_json=brief_json)
        result = await self.model_port.complete(
            ModelCompletionRequest(
                capability="story_outline",
                system="You are the WindAgent story outliner.",
                user=rendered,
                canonical_model=self.canonical_model,
                temperature=0.7,
                max_tokens=1500,
                prompt_spec=self.prompt_spec,
            )
        )
        if not result.content or not result.content.strip():
            raise EmptyResponseError("Story outliner received an empty response.")
        data = parse_json_contract(result.content)
        title = str(data.get("title") or brief.title).strip()
        if not title:
            raise ResponseParseError("Story outline missing 'title'.", details={"raw": data})
        themes = [str(t).strip() for t in (data.get("themes") or []) if str(t).strip()]
        themes = sorted(set(themes))  # deterministic full ordering (NONDET-005)
        concept = StoryConcept(
            concept_id=StoryConceptId(self.id_factory.concept_id(title)),
            title=title,
            premise=str(data.get("premise") or ""),
            synopsis=str(data.get("synopsis") or ""),
            themes=themes,
            metadata={"beats": [str(b).strip() for b in (data.get("beats") or []) if str(b).strip()]},
        )
        return {
            "concept": concept,
            "beats": concept.metadata.get("beats", []),
            "prompt_version": self.prompt_spec.version,
            "prompt_hash": self.prompt_spec.content_hash,
            "capability": self.prompt_spec.capability,
        }


__all__ = ["StoryOutliner", "OUTLINE_PROMPT_V1"]
