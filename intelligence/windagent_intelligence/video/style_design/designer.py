"""
StyleDesigner (Phase 6 slice 6) — style bible.

Builds a canonical `StyleBible` from a creative brief + screenplay using a
provider-neutral model port with versioned/hashed prompts. Deterministic
field ordering; required style constraints from the brief are preserved
(equivalence policy: style constraints are blocking).
"""

from __future__ import annotations

from typing import Optional

from windagent_core.domain.video_production.ids import StyleBibleId
from windagent_core.domain.video_production.location import StyleBible
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    Screenplay,
)

from windagent_intelligence.video.errors import EmptyResponseError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import parse_json_contract
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec

STYLE_DESIGN_PROMPT_V1 = PromptSpec(
    capability="style_design",
    version="1.0.0",
    description="Design a visual style bible from brief + screenplay.",
    template=(
        "You are a visual development lead.\n"
        "Design a style bible for this production.\n"
        'Respond ONLY with a JSON object with keys: "name" (string), '
        '"visual_style" (string), "color_palette" (array), '
        '"lighting_rules" (array).\n\n'
        "BRIEF:\n{brief_json}\n\nSCREENPLAY TITLE: {screenplay_title}"
    ),
)


class StyleDesigner:
    """Designs a canonical StyleBible from a brief + screenplay."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        id_factory: Optional[StableIdFactory] = None,
        canonical_model: str = "canonical-default",
        prompt_spec: PromptSpec = STYLE_DESIGN_PROMPT_V1,
    ) -> None:
        self.model_port = model_port
        self.id_factory = id_factory or StableIdFactory()
        self.canonical_model = canonical_model
        self.prompt_spec = prompt_spec

    async def design(self, brief: CreativeBrief, screenplay: Screenplay) -> dict:
        """Return {style_bible, prompt_version, prompt_hash, capability}."""
        from pydantic import TypeAdapter

        brief_json = TypeAdapter(CreativeBrief).dump_json(brief).decode("utf-8")
        rendered = self.prompt_spec.render(
            brief_json=brief_json,
            screenplay_title=screenplay.title,
        )
        result = await self.model_port.complete(
            ModelCompletionRequest(
                capability="style_design",
                system="You are the WindAgent style designer.",
                user=rendered,
                canonical_model=self.canonical_model,
                temperature=0.7,
                max_tokens=1200,
                prompt_spec=self.prompt_spec,
            )
        )
        if not result.content or not result.content.strip():
            raise EmptyResponseError("Style designer received an empty response.")
        data = parse_json_contract(result.content)
        name = str(data.get("name") or f"{brief.title} Style").strip()
        style = StyleBible(
            style_id=StyleBibleId(self.id_factory.style_id(name)),
            name=name,
            visual_style=str(data.get("visual_style") or ""),
            color_palette=[str(c).strip() for c in (data.get("color_palette") or []) if str(c).strip()],
            lighting_rules=[str(r).strip() for r in (data.get("lighting_rules") or []) if str(r).strip()],
            metadata={
                "prompt_version": self.prompt_spec.version,
                "prompt_hash": self.prompt_spec.content_hash,
            },
        )
        return {
            "style_bible": style,
            "prompt_version": self.prompt_spec.version,
            "prompt_hash": self.prompt_spec.content_hash,
            "capability": self.prompt_spec.capability,
        }


__all__ = ["StyleDesigner", "STYLE_DESIGN_PROMPT_V1"]
