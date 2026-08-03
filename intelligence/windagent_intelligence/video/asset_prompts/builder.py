"""
AssetPromptSpecBuilder (Phase 6 slice 8) — asset prompt specification.

Deterministically builds versioned, hashed `PromptSpec`s for reference
assets (character portrait, location/setting, style) so every generated
asset is traceable to its exact prompt (prompt_version + content_hash).

Characterization BM-005/BM-006 showed upstream embeds name/desc/style into
image prompts deterministically. The canonical builder reproduces that
contract without copying upstream template text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.location import (
    LocationBible,
    StyleBible,
)

from windagent_intelligence.video.prompts import PromptSpec

CHARACTER_PORTRAIT_PROMPT_V1 = PromptSpec(
    capability="asset_prompt.character_portrait",
    version="1.0.0",
    description="Reference portrait prompt for a character bible.",
    template=(
        "Character reference portrait.\n"
        "Name: {name}\nDescription: {description}\n"
        "Style: {visual_style}\n"
        "Required views: front, three-quarter, profile.\n"
        "Consistent appearance; no text, labels, or watermarks."
    ),
)

LOCATION_PROMPT_V1 = PromptSpec(
    capability="asset_prompt.location",
    version="1.0.0",
    description="Reference setting prompt for a location bible.",
    template=(
        "Location reference image.\n"
        "Name: {name}\nDescription: {description}\n"
        "Lighting: {lighting}\n"
        "Atmosphere: {atmosphere}\n"
        "No people, animals, or text."
    ),
)

STYLE_PROMPT_V1 = PromptSpec(
    capability="asset_prompt.style",
    version="1.0.0",
    description="Style reference prompt for a style bible.",
    template=(
        "Style reference.\n"
        "Name: {name}\nVisual style: {visual_style}\n"
        "Palette: {palette}\nLighting rules: {lighting_rules}"
    ),
)


@dataclass(frozen=True)
class AssetPromptSpecResult:
    """A versioned prompt spec bound to a target asset."""

    capability: str
    target_id: str
    prompt_spec: PromptSpec
    rendered: str


class AssetPromptSpecBuilder:
    """Deterministic builder of versioned asset prompt specs."""

    def build_character(self, character: CharacterBible) -> AssetPromptSpecResult:
        spec = CHARACTER_PORTRAIT_PROMPT_V1
        rendered = spec.render(
            name=character.name,
            description=_dict_to_text(character.visual_traits),
            visual_style="",
        )
        return AssetPromptSpecResult(
            capability=spec.capability,
            target_id=str(character.character_id),
            prompt_spec=spec,
            rendered=rendered,
        )

    def build_location(self, location: LocationBible) -> AssetPromptSpecResult:
        spec = LOCATION_PROMPT_V1
        rendered = spec.render(
            name=location.name,
            description=location.visual_description,
            lighting=location.lighting_profile,
            atmosphere=", ".join(location.atmosphere_tags),
        )
        return AssetPromptSpecResult(
            capability=spec.capability,
            target_id=str(location.location_id),
            prompt_spec=spec,
            rendered=rendered,
        )

    def build_style(self, style: StyleBible) -> AssetPromptSpecResult:
        spec = STYLE_PROMPT_V1
        rendered = spec.render(
            name=style.name,
            visual_style=style.visual_style,
            palette=", ".join(style.color_palette),
            lighting_rules="; ".join(style.lighting_rules),
        )
        return AssetPromptSpecResult(
            capability=spec.capability,
            target_id=str(style.style_id),
            prompt_spec=spec,
            rendered=rendered,
        )

    def build_all(
        self,
        *,
        characters: List[CharacterBible],
        locations: List[LocationBible],
        style: StyleBible,
    ) -> List[AssetPromptSpecResult]:
        results = [self.build_character(c) for c in characters]
        results += [self.build_location(loc) for loc in locations]
        results.append(self.build_style(style))
        return results


def _dict_to_text(traits) -> str:
    if isinstance(traits, dict):
        return "; ".join(f"{k}: {v}" for k, v in sorted(traits.items()))
    return str(traits or "")


__all__ = ["AssetPromptSpecBuilder", "AssetPromptSpecResult"]
