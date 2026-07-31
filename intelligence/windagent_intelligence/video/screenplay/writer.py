"""
ScreenplayWriter (Phase 6 slice 3) — multi-scene screenplay from a concept.

Provider-neutral: builds a versioned, hashed PromptSpec, calls the model port,
parses the returned canonical screenplay TEXT deterministically (Unicode /
Vietnamese / CJK tolerant — fixes DEF-002/DEF-005), then maps parsed episodes
+ scenes into a canonical `Screenplay` with ordered scenes.

Scenes reference locations and characters by stable ID; dialogue line IDs are
assigned deterministically (fixes DEF-003 identity binding).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.enums import ScreenplayStatus
from windagent_core.domain.video_production.ids import (
    CharacterId,
    DialogueLineId,
    LocationId,
    ScreenplayId,
    SceneId,
)
from windagent_core.domain.video_production.screenplay import (
    DialogueLine,
    Screenplay,
    StoryConcept,
)
from windagent_core.domain.video_production.scene import Scene

from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import (
    CanonicalEpisode,
    characters_from_episodes,
    split_episodes,
)
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec

SCREENPLAY_PROMPT_V1 = PromptSpec(
    capability="screenplay_generation",
    version="1.0.0",
    description="Generate a canonical multi-scene screenplay text from a story concept.",
    template=(
        "You are a screenwriter.\n"
        "Write a multi-scene screenplay for the story concept below using "
        "this canonical format:\n"
        '  ## Episode <N>\n'
        '  ## Scene <N> | <TIME: DAY|NIGHT|DAWN|DUSK> | <SPACE: INTERIOR|EXTERIOR> | <Location name>\n'
        '  Characters: Name1, Name2\n'
        '  Name1: dialogue line\n'
        '  <action>narrative action</action>\n'
        "Preserve scene order. Every scene must have a header line.\n\n"
        "CONCEPT:\n{concept_json}"
    ),
)


class ScreenplayWriter:
    """Generates a canonical Screenplay from a StoryConcept."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        id_factory: Optional[StableIdFactory] = None,
        canonical_model: str = "canonical-default",
        prompt_spec: PromptSpec = SCREENPLAY_PROMPT_V1,
    ) -> None:
        self.model_port = model_port
        self.id_factory = id_factory or StableIdFactory()
        self.canonical_model = canonical_model
        self.prompt_spec = prompt_spec

    async def write(self, concept: StoryConcept) -> dict:
        """Return {screenplay, dialogue_lines, episodes, prompt_version, prompt_hash}."""
        from pydantic import TypeAdapter

        concept_json = TypeAdapter(StoryConcept).dump_json(concept).decode("utf-8")
        rendered = self.prompt_spec.render(concept_json=concept_json)
        result = await self.model_port.complete(
            ModelCompletionRequest(
                capability="screenplay_generation",
                system="You are the WindAgent screenwriter.",
                user=rendered,
                canonical_model=self.canonical_model,
                temperature=0.7,
                max_tokens=4000,
                prompt_spec=self.prompt_spec,
            )
        )
        if not result.content or not result.content.strip():
            from windagent_intelligence.video.errors import EmptyResponseError

            raise EmptyResponseError("Screenplay writer received an empty response.")

        episodes = split_episodes(result.content)
        if not episodes:
            from windagent_intelligence.video.errors import ResponseParseError

            raise ResponseParseError(
                "Screenplay text did not contain any parseable episode.",
                details={"raw": result.content[:200]},
            )

        return self._assemble(
            concept=concept,
            episodes=episodes,
            prompt_version=self.prompt_spec.version,
            prompt_hash=self.prompt_spec.content_hash,
        )

    # ------------------------------------------------------------------
    # Deterministic assembly of the canonical Screenplay from parsed text
    # ------------------------------------------------------------------
    def _assemble(
        self,
        *,
        concept: StoryConcept,
        episodes: List[CanonicalEpisode],
        prompt_version: str,
        prompt_hash: str,
    ) -> dict:
        screenplay_id = self.id_factory.screenplay_id(concept.title)
        # Deterministic character registry (fully sorted, NONDET-005)
        char_names = characters_from_episodes(episodes)
        char_ids: Dict[str, CharacterId] = {
            name: CharacterId(self.id_factory.character_id(name, seq))
            for seq, name in enumerate(char_names)
        }
        # Deterministic location registry
        loc_names: List[str] = sorted(
            {
                scene.header.location
                for ep in episodes
                for scene in ep.scenes
                if scene.header.location
            }
        )
        loc_ids: Dict[str, LocationId] = {
            name: LocationId(self.id_factory.location_id(name, seq))
            for seq, name in enumerate(loc_names)
        }

        scenes: List[Scene] = []
        dialogue_lines: List[DialogueLine] = []
        scene_order = 0
        dialogue_order = 0
        for ep in episodes:
            for scene in ep.scenes:
                scene_order += 1
                scene_id = SceneId(
                    self.id_factory.scene_id(str(screenplay_id), scene_order)
                )
                scene_loc = loc_ids.get(scene.header.location)
                scene_char_ids = sorted(
                    {
                        char_ids[u.speaker]
                        for u in scene.units
                        if u.is_dialogue and u.speaker in char_ids
                    },
                    key=str,
                )
                dlg_ids: List[DialogueLineId] = []
                for unit in scene.units:
                    if unit.is_dialogue and unit.speaker:
                        dialogue_order += 1
                        dlg_id = DialogueLineId(
                            self.id_factory.dialogue_id(str(scene_id), dialogue_order)
                        )
                        dlg = DialogueLine(
                            dialogue_id=dlg_id,
                            scene_id=scene_id,
                            character_id=char_ids[unit.speaker],
                            order=dialogue_order,
                            text=unit.text,
                            delivery=unit.tone,
                        )
                        dialogue_lines.append(dlg)
                        dlg_ids.append(dlg_id)
                scenes.append(
                    Scene(
                        scene_id=scene_id,
                        order=scene_order,
                        title=scene.header.location or f"Scene {scene_order}",
                        location_id=scene_loc or _default_location_id(self.id_factory),
                        character_ids=scene_char_ids,
                        dialogue_line_ids=dlg_ids,
                        action_description="\n".join(
                            u.text for u in scene.units if not u.is_dialogue
                        ),
                        metadata={
                            "episode_number": ep.episode_number,
                            "scene_number": scene.scene_number,
                            "scene_time": scene.header.time_of_day,
                            "scene_space": scene.header.space,
                            "scene_location": scene.header.location,
                            "scene_context": scene.header.raw,
                        },
                    )
                )

        screenplay = Screenplay(
            screenplay_id=ScreenplayId(screenplay_id),
            title=concept.title,
            logline=concept.synopsis,
            status=ScreenplayStatus.DRAFT,
            scenes=scenes,
            metadata={
                "prompt_version": prompt_version,
                "prompt_hash": prompt_hash,
                "episode_count": len(episodes),
                "characters": sorted(char_ids.keys()),
                "locations": loc_names,
            },
        )
        return {
            "screenplay": screenplay,
            "dialogue_lines": dialogue_lines,
            "episodes": episodes,
            "character_map": char_ids,
            "location_map": loc_ids,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
        }


def _default_location_id(id_factory: StableIdFactory) -> LocationId:
    """Deterministic LocationId for scenes whose header carries no location."""
    from windagent_core.domain.video_production.ids import LocationId

    return LocationId(id_factory.location_id("unspecified", 0))


__all__ = ["ScreenplayWriter", "SCREENPLAY_PROMPT_V1"]
