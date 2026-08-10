"""Plan B B6 canonical screenplay text renderer (S8, derived view).

The structured ``ScreenplayDraft`` JSON is the authority; canonical
screenplay TEXT is rendered deterministically from it — never parsed back
into authority. Rendering is pure and provider-free: same draft, same bytes.
"""

from __future__ import annotations

from typing import Dict, Optional

from windagent_core.domain.story.screenplay.models import ScreenplayDraft

__all__ = ["render_screenplay_text"]


def render_screenplay_text(
    draft: ScreenplayDraft,
    *,
    character_names: Optional[Dict[str, str]] = None,
    location_names: Optional[Dict[str, str]] = None,
    episode_number: int = 1,
) -> str:
    """Render a structured draft into canonical screenplay text.

    ``character_names`` / ``location_names`` map Story IDs to display names
    (from canon); IDs are used verbatim when no mapping is supplied.
    Deterministic: dialogue ordered by ``order``, blocks separated by blank
    lines, trailing newline.
    """
    names = dict(character_names or {})
    loc_names = dict(location_names or {})

    def char_name(character_id: str) -> str:
        return names.get(character_id, character_id)

    parts: list[str] = [f"## Episode {episode_number} | {draft.title}"]
    for scene in draft.scenes:
        location = loc_names.get(scene.location_id.value, scene.location_id.value)
        parts.append(f"## Scene {scene.order} | {location}")
        if scene.character_ids:
            parts.append(
                "Characters: "
                + ", ".join(char_name(c.value) for c in scene.character_ids)
            )
        if scene.action_description.strip():
            parts.append(scene.action_description.strip())
        for line in sorted(scene.dialogue, key=lambda line: line.order):
            parts.append(f"{char_name(line.character_id.value)}: {line.text.strip()}")
        if scene.narration.strip():
            parts.append(f"<{scene.narration.strip()}>")
        parts.append(scene.transition)
    parts.append(
        f"# Duration: {draft.total_estimated_seconds}s / target {draft.target_duration_seconds}s"
    )
    return "\n\n".join(parts) + "\n"
