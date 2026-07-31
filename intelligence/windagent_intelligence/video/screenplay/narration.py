"""
DialogueNarrator (Phase 6 slice 4) — dialogue and narration.

Deterministically extracts dialogue lines + narration from canonical
screenplay text, binding every line to a stable character identity
(fixes DEF-003: identity is never merged on display name). Works offline —
no model call — so dialogue attribution is fully deterministic.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.ids import (
    CharacterId,
    DialogueLineId,
    SceneId,
)
from windagent_core.domain.video_production.screenplay import DialogueLine
from windagent_core.domain.video_production.scene import Scene

from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import (
    CanonicalEpisode,
    split_episodes,
)


class DialogueNarrator:
    """Extracts canonical DialogueLine[] + narration from screenplay text."""

    def __init__(self, *, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def narrate(self, screenplay_text: str, scenes: List[Scene]) -> dict:
        """Return {dialogue_lines, narration_blocks, character_map, episodes}."""
        episodes = split_episodes(screenplay_text)
        character_map: Dict[str, CharacterId] = self._character_map(episodes)
        scene_index = {
            scene.metadata.get("scene_number", index): scene
            for index, scene in enumerate(scenes)
        }
        dialogue_lines: List[DialogueLine] = []
        narration_blocks: Dict[str, str] = {}
        dialogue_order = 0
        for ep in episodes:
            for scene in ep.scenes:
                scene_id = scene_index.get(scene.scene_number)
                if scene_id is None and scenes:
                    scene_id = scenes[0]
                narration = "\n".join(u.text for u in scene.units if not u.is_dialogue)
                if narration:
                    narration_blocks[str(scene_id.scene_id)] = narration
                for unit in scene.units:
                    if not unit.is_dialogue or not unit.speaker:
                        continue
                    character_id = character_map.get(unit.speaker)
                    if character_id is None:
                        continue
                    dialogue_order += 1
                    dialogue_lines.append(
                        DialogueLine(
                            dialogue_id=DialogueLineId(
                                self.id_factory.dialogue_id(str(scene_id.scene_id), dialogue_order)
                            ),
                            scene_id=SceneId(str(scene_id.scene_id)),
                            character_id=character_id,
                            order=dialogue_order,
                            text=unit.text,
                            delivery=unit.tone,
                        )
                    )
        return {
            "dialogue_lines": dialogue_lines,
            "narration_blocks": narration_blocks,
            "character_map": character_map,
            "episodes": episodes,
        }

    def _character_map(self, episodes: List[CanonicalEpisode]) -> Dict[str, CharacterId]:
        """Deterministic speaker -> stable CharacterId (never merged on name)."""
        from windagent_intelligence.video.parsing import characters_from_episodes

        names = characters_from_episodes(episodes)
        return {
            name: CharacterId(self.id_factory.character_id(name, seq))
            for seq, name in enumerate(names)
        }


__all__ = ["DialogueNarrator"]
