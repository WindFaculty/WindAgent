"""
Compatibility adapters: legacy V2 screenplay models <-> structured draft
(Plan B B1/B6; B0 reuse decisions REUSE/adapt).

Conversion is explicit and loss-reporting. The V2 text parser/serializer
remains available for legacy import; converting to the structured draft is a
separate, explicit step that returns typed loss/warning information.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.story.ids import (
    BeatId,
    DraftSceneId,
    OutlineSceneId,
    ScreenplayDraftId,
    StoryCharacterId,
    StoryLocationId,
)
from windagent_core.domain.story.screenplay.models import (
    DraftDialogueLine,
    DraftScene,
    ScreenplayDraft,
)
from windagent_core.domain.video_production.screenplay import (
    DialogueLine as VideoDialogueLine,
    Screenplay as VideoScreenplay,
)

__all__ = [
    "from_video_screenplay",
    "dialogue_line_loss",
]


def from_video_screenplay(
    video_screenplay: VideoScreenplay,
    *,
    dialogue_lines: Optional[List[VideoDialogueLine]] = None,
    draft_id: Optional[ScreenplayDraftId] = None,
    character_id_mapping: Optional[Dict[str, str]] = None,
    location_id_mapping: Optional[Dict[str, str]] = None,
    beat_id_mapping: Optional[Dict[str, str]] = None,
    outline_scene_mapping: Optional[Dict[str, str]] = None,
    target_duration_seconds: int = 240,
) -> tuple[ScreenplayDraft, Dict[str, Any]]:
    """Convert a V2 screenplay into a structured draft.

    V2 dialogue lives at package level (``VideoProductionPackage.dialogue``),
    so callers pass the lines explicitly. Returns ``(draft, loss)`` where
    ``loss`` lists every dropped/assumed piece of information.
    """
    character_map = character_id_mapping or {}
    location_map = location_id_mapping or {}
    beat_map = beat_id_mapping or {}
    outline_map = outline_scene_mapping or {}

    warnings: List[str] = []
    if not character_id_mapping:
        warnings.append("no character_id_mapping: character refs kept verbatim (video IDs)")
    if not location_id_mapping:
        warnings.append("no location_id_mapping: location refs kept verbatim (video IDs)")
    if not beat_map:
        warnings.append("no beat_id_mapping: source_beat_ids left empty")
    if not outline_map:
        warnings.append("no outline_scene_mapping: outline_scene_id prefixed 'legacy:'")
    if dialogue_lines is None:
        warnings.append("no dialogue_lines supplied: draft scenes carry no dialogue")

    lines_by_scene: Dict[str, List[VideoDialogueLine]] = {}
    for line in dialogue_lines or []:
        lines_by_scene.setdefault(str(line.scene_id), []).append(line)

    loss: Dict[str, Any] = {
        "warnings": warnings,
        "dropped": [
            "video Screenplay.status",
            "video Screenplay.metadata",
            "video Scene.time_of_day",
            "video Scene.metadata",
        ],
        "assumed": {
            "estimated_seconds": "0 until the B6 timing pass",
            "transition": "CUT TO:",
            "language": "vi",
            "audience_band": "5-8",
        },
        "mappings": {
            "character_id_mapping": character_map,
            "location_id_mapping": location_map,
            "beat_id_mapping": beat_map,
        },
    }

    scenes: List[DraftScene] = []
    for index, scene in enumerate(video_screenplay.scenes):
        story_scene_id = DraftSceneId.generate("dscn")
        lines: List[DraftDialogueLine] = []
        for order, line in enumerate(
            sorted(lines_by_scene.get(str(scene.scene_id), []), key=lambda line_item: line_item.order),
            start=1,
        ):
            lines.append(DraftDialogueLine(
                dialogue_id=line.dialogue_id,
                scene_id=story_scene_id,
                character_id=StoryCharacterId(
                    character_map.get(str(line.character_id), str(line.character_id))
                ),
                order=order,
                text=line.text,
                delivery=line.delivery,
            ))
        scenes.append(DraftScene(
            scene_id=story_scene_id,
            order=index + 1,
            outline_scene_id=OutlineSceneId(
                outline_map.get(str(scene.scene_id), f"legacy:{scene.scene_id}")
            ),
            location_id=StoryLocationId(
                location_map.get(str(scene.location_id), str(scene.location_id))
            ),
            character_ids=[
                StoryCharacterId(character_map.get(str(c), str(c)))
                for c in scene.character_ids
            ],
            action_description=scene.action_description,
            dialogue=lines,
            transition="CUT TO:",
            source_beat_ids=[BeatId(beat_map.get(b, b)) for b in []],
        ))

    draft = ScreenplayDraft(
        draft_id=draft_id or ScreenplayDraftId.generate("draft"),
        title=video_screenplay.title,
        logline=video_screenplay.logline,
        target_duration_seconds=target_duration_seconds,
        scenes=scenes,
    )
    return draft, loss


def dialogue_line_loss(line: VideoDialogueLine) -> Dict[str, Any]:
    """Documented loss when mapping one V2 dialogue line into a draft."""
    return {
        "dialogue_id": str(line.dialogue_id),
        "dropped": [] if line.delivery else ["delivery (empty in V2)"],
        "assumed": {
            "estimated_seconds": "0 until B6 timing pass",
        },
    }
