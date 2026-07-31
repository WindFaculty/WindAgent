"""
CreativeBriefExpander (Phase 6 slice 1) — creative brief / idea expansion.

Turns a raw user idea into a canonical `CreativeBrief`. Provider-neutral:
the capability builds a versioned, hashed `PromptSpec`, calls the
`PreproductionModelPort`, parses the JSON response with typed failures
(fixes DEF-001/BM-018), and returns a domain `CreativeBrief` plus the
prompt version/hash used so every artifact is traceable.
"""

from __future__ import annotations

from typing import Optional

from windagent_core.domain.video_production.ids import CreativeBriefId
from windagent_core.domain.video_production.screenplay import CreativeBrief

from windagent_intelligence.video.errors import MissingModelConfigError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import parse_json_contract
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec

BRIEF_EXPANSION_PROMPT_V1 = PromptSpec(
    capability="brief_expansion",
    version="1.0.0",
    description="Expand a raw idea into a structured creative brief JSON.",
    template=(
        "You are a creative development lead.\n"
        "Expand the following idea into a creative brief.\n"
        'Respond ONLY with a JSON object with keys: "title", "logline", '
        '"genre" (string), "tone" (string), "audience" (string), '
        '"target_duration_seconds" (int), "aspect_ratio" (string), '
        '"production_constraints" (object).\n\n'
        "IDEA:\n{idea}"
    ),
)


class CreativeBriefExpander:
    """Expands a raw idea into a canonical CreativeBrief."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        id_factory: Optional[StableIdFactory] = None,
        canonical_model: str = "canonical-default",
        prompt_spec: PromptSpec = BRIEF_EXPANSION_PROMPT_V1,
    ) -> None:
        self.model_port = model_port
        self.id_factory = id_factory or StableIdFactory()
        self.canonical_model = canonical_model
        self.prompt_spec = prompt_spec

    async def expand(self, idea: str) -> dict:
        """Return {brief, prompt_version, prompt_hash, capability}."""
        self.require_model(self.canonical_model)  # BM-010 preflight: fail fast
        rendered = self.prompt_spec.render(idea=idea)
        result = await self.model_port.complete(
            ModelCompletionRequest(
                capability="brief_expansion",
                system="You are the WindAgent creative brief expander.",
                user=rendered,
                canonical_model=self.canonical_model,
                temperature=0.7,
                max_tokens=1200,
                prompt_spec=self.prompt_spec,
            )
        )
        if not result.content or not result.content.strip():
            from windagent_intelligence.video.errors import EmptyResponseError

            raise EmptyResponseError("Brief expander received an empty model response.")
        data = parse_json_contract(result.content)
        title = str(data.get("title") or "Untitled").strip()
        if not title:
            from windagent_intelligence.video.errors import ResponseParseError

            raise ResponseParseError(
                "Brief expansion missing 'title'.", details={"raw": data}
            )
        genre = data.get("genre") or ""
        brief = CreativeBrief(
            brief_id=CreativeBriefId(self.id_factory.brief_id(title)),
            title=title,
            genre=genre if isinstance(genre, str) else ", ".join(genre),
            logline=str(data.get("logline") or ""),
            tone=str(data.get("tone") or ""),
            audience=str(data.get("audience") or ""),
            target_duration_seconds=int(data.get("target_duration_seconds") or 60),
            aspect_ratio=str(data.get("aspect_ratio") or "16:9"),
            production_constraints=dict(data.get("production_constraints") or {}),
        )
        return {
            "brief": brief,
            "prompt_version": self.prompt_spec.version,
            "prompt_hash": self.prompt_spec.content_hash,
            "capability": self.prompt_spec.capability,
        }

    @staticmethod
    def require_model(canonical_model: Optional[str]) -> str:
        """Fail fast when the canonical model is not configured (BM-010)."""
        if not canonical_model:
            raise MissingModelConfigError(
                "Missing required model configuration: llm_model"
            )
        return canonical_model


__all__ = ["CreativeBriefExpander", "BRIEF_EXPANSION_PROMPT_V1"]
