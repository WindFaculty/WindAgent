"""
Deterministic parsing helpers for the video kernel (Phase 6).

Characterization findings that shaped this module:
- DEF-001: broken provider JSON must raise a typed ResponseParseError, never
  silently return None.
- DEF-002: episode detection must not depend on CJK regex alone — it must
  handle Vietnamese/Unicode headers ("Tập 1", "第1集", "Episode 1").
- DEF-005: scene-header parsing must be independent of CJK patterns.

The kernel defines its OWN canonical screenplay text format (never parses the
upstream vendor format at runtime), but the parsing rules are tolerant to
Vietnamese and CJK labels so golden semantics survive translation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_intelligence.video.errors import (
    EmptyResponseError,
    ResponseParseError,
)

# ---------------------------------------------------------------------------
# Typed JSON parsing
# ---------------------------------------------------------------------------


def parse_json_contract(text: Optional[str]) -> Dict[str, Any]:
    """Parse a provider JSON response; raises typed errors on empty/broken.

    Fixes DEF-001 (silent None on broken JSON) and BM-018 (empty response).
    """
    if not text or not str(text).strip():
        raise EmptyResponseError("Provider returned an empty response.")
    try:
        data = json.loads(str(text))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ResponseParseError(
            "Provider response was not valid JSON.",
            details={"raw": str(text)[:200], "error": str(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise ResponseParseError(
            "Provider JSON must be an object.",
            details={"type": type(data).__name__},
        )
    return data


# ---------------------------------------------------------------------------
# Canonical screenplay text parsing (Unicode/Vietnamese/CJK tolerant)
# ---------------------------------------------------------------------------

_EPISODE_HEADER = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:"
    r"第\s*(\d+)\s*集"   # CJK: 第1集 (digits BEFORE label)
    r"|(?:episode|tập|tâp|эпизод)\s*[:#.\-]?\s*(\d+)"
    r")",
    re.IGNORECASE,
)

# Scene markers: CJK 第N场 (optionally prefixed by 第N集-), or label+N forms.
# Anchored to the header region (line start, allowing an optional CJK episode
# prefix "第N集-") so narration/action lines that merely mention "scene 3" or
# "第2场" are never misparsed as scene headers.
_SCENE_MARKER = re.compile(
    r"^\s*(?:第\s*\d+\s*集\s*[-–—]?\s*)?(?:"
    r"第\s*(\d+)\s*场"
    r"|(?:scene|cảnh|canh|сцена)\s*[:#.\-]?\s*(\d+)"
    r")",
    re.IGNORECASE,
)

TIME_OF_DAY = {
    "day": "DAY",
    "ngày": "DAY",
    "ngay": "DAY",
    "日": "DAY",
    "night": "NIGHT",
    "đêm": "NIGHT",
    "dem": "NIGHT",
    "夜": "NIGHT",
    "dawn": "DAWN",
    "bình minh": "DAWN",
    "晨": "DAWN",
    "dusk": "DUSK",
    "hoàng hôn": "DUSK",
    "昏": "DUSK",
}

SPACE = {
    "interior": "INTERIOR",
    "内": "INTERIOR",
    "nội": "INTERIOR",
    "noi": "INTERIOR",
    "exterior": "EXTERIOR",
    "外": "EXTERIOR",
    "ngoại": "EXTERIOR",
    "ngoai": "EXTERIOR",
}


@dataclass(frozen=True)
class SceneHeader:
    """Canonical parsed scene header."""

    scene_number: int
    time_of_day: str  # canonical TimeOfDay-compatible label
    space: str  # INTERIOR | EXTERIOR | ""
    location: str = ""
    raw: str = ""


@dataclass(frozen=True)
class Unit:
    """A dialogue or narration line within a scene."""

    line_number: int
    text: str
    is_dialogue: bool
    speaker: str = ""
    tone: str = ""
    characters: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalScene:
    """Scene parsed from canonical screenplay text."""

    scene_number: int
    header: SceneHeader
    title: str = ""
    units: List[Unit] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalEpisode:
    """Episode parsed from canonical screenplay text."""

    episode_number: int
    title: str = ""
    scenes: List[CanonicalScene] = field(default_factory=list)


def _canonical_case(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _map_time(token: str) -> str:
    key = _canonical_case(token)
    return TIME_OF_DAY.get(key, "")


def _map_space(token: str) -> str:
    key = _canonical_case(token)
    return SPACE.get(key, "")


def parse_scene_header(line: str) -> Optional[SceneHeader]:
    """Parse a scene header line independent of CJK patterns (fixes DEF-005)."""
    stripped = line.strip().lstrip("*#").strip()
    m = _SCENE_MARKER.match(stripped)
    if not m:
        return None
    number = int(next(g for g in m.groups() if g is not None))
    remainder = stripped[m.end():].strip()
    # Canonical/English headers separate fields with pipes
    # ("NIGHT | EXTERIOR | Lake Shore"); CJK headers separate with whitespace
    # ("日 内 森林"). Split on pipes when present, otherwise on whitespace, so
    # multi-word locations like "Lake Shore" are preserved in both conventions.
    if re.search(r"[|｜]", remainder):
        raw_parts = re.split(r"[|｜]", remainder)
    else:
        raw_parts = re.split(r"\s+", remainder)
    time_of_day = ""
    space = ""
    location_parts: List[str] = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        mapped_time = _map_time(part)
        if mapped_time and not time_of_day:
            time_of_day = mapped_time
            continue
        mapped_space = _map_space(part)
        if mapped_space and not space:
            space = mapped_space
            continue
        location_parts.append(part)
    return SceneHeader(
        scene_number=number,
        time_of_day=time_of_day,
        space=space,
        location=" ".join(location_parts),
        raw=stripped,
    )


_DIALOGUE_SPEAKER = re.compile(
    r"^\s*([^\n：:]{1,40})\s*[:：]\s*(.+)$", re.UNICODE
)
_ACTION_TAG = re.compile(r"^\s*<action>\s*(.*?)\s*</action>\s*$", re.IGNORECASE | re.UNICODE)

# End-of-script markers ("完", "THE END", "Hết", "КОНЕЦ") are decorative
# closers, not narration units.
_END_MARKER = re.compile(
    r"^\s*[(（]?\s*(?:完|the\s*end|fin|hết|kết\s*thúc|конец)\s*[)）]?\s*$",
    re.IGNORECASE | re.UNICODE,
)


def parse_unit(line_number: int, line: str, scene_characters: List[str]) -> Unit:
    """Classify a line as dialogue or narration (fixes DEF-003 attribution)."""
    stripped = line.strip()
    if not stripped:
        return Unit(line_number=line_number, text="", is_dialogue=False)
    action_m = _ACTION_TAG.match(stripped)
    if action_m:
        return Unit(
            line_number=line_number,
            text=action_m.group(1),
            is_dialogue=False,
            characters=list(scene_characters),
        )
    dlg_m = _DIALOGUE_SPEAKER.match(stripped)
    if dlg_m:
        speaker = dlg_m.group(1).strip()
        text = dlg_m.group(2).strip()
        tone = _extract_tone(text)
        return Unit(
            line_number=line_number,
            text=text,
            is_dialogue=True,
            speaker=speaker,
            tone=tone,
            characters=[speaker] if speaker else [],
        )
    return Unit(line_number=line_number, text=stripped, is_dialogue=False)


def _extract_tone(text: str) -> str:
    # Canonical convention: "speech (tone)" suffix or "（语气）"
    m = re.search(r"[(（]\s*([^()（）]{1,30}?)\s*[)）]\s*$", text, re.UNICODE)
    return m.group(1).strip() if m else ""


def split_episodes(text: str) -> List[CanonicalEpisode]:
    """Split canonical screenplay text into episodes (Unicode/Vietnamese aware).

    Fixes DEF-002: uses a multi-language header regex, not CJK-only patterns.
    """
    episodes: List[CanonicalEpisode] = []
    current_episode: Optional[CanonicalEpisode] = None
    current_scene: Optional[CanonicalScene] = None
    current_characters: List[str] = []
    line_number = 0

    for raw_line in text.splitlines():
        line_number += 1
        stripped = raw_line.strip()
        if not stripped:
            continue

        # Scene marker is checked BEFORE the episode marker: a CJK scene line
        # such as "**第1集-第1场 日 内 森林" contains an episode prefix AND a
        # scene marker, and must create a scene, not a new episode.
        sc_m = _SCENE_MARKER.match(stripped.lstrip("*#"))
        if sc_m and not _DIALOGUE_SPEAKER.match(stripped):
            if current_episode is None:
                current_episode = CanonicalEpisode(episode_number=1, title="")
                episodes.append(current_episode)
            header = parse_scene_header(stripped) or SceneHeader(
                scene_number=int(next(g for g in sc_m.groups() if g is not None)),
                time_of_day="",
                space="",
            )
            current_scene = CanonicalScene(
                scene_number=header.scene_number,
                header=header,
                title=header.location or stripped,
            )
            current_episode.scenes.append(current_scene)
            current_characters = []
            continue

        ep_m = _EPISODE_HEADER.match(stripped)
        if ep_m:
            episode_number = int(next(g for g in ep_m.groups() if g is not None))
            current_episode = CanonicalEpisode(
                episode_number=episode_number,
                title=stripped,
            )
            episodes.append(current_episode)
            current_scene = None
            continue

        if current_episode is None:
            current_episode = CanonicalEpisode(episode_number=1, title="")
            episodes.append(current_episode)

        # End-of-script marker ("完" / "THE END" / "Hết"): skip, not narration.
        if _END_MARKER.match(stripped):
            continue

        # "Characters: A, B" line
        chars_m = re.match(r"^\s*(?:characters|nhân vật|人物|персонажи)\s*[:：]\s*(.+)$", stripped, re.IGNORECASE | re.UNICODE)
        if chars_m:
            current_characters = [
                c.strip() for c in re.split(r"[,，、]", chars_m.group(1)) if c.strip()
            ]
            continue

        if current_scene is None:
            current_scene = CanonicalScene(scene_number=1, header=SceneHeader(scene_number=1, time_of_day="", space=""))
            current_episode.scenes.append(current_scene)

        unit = parse_unit(line_number, stripped, current_characters)
        if unit.text:
            # mutable dataclass: rebuild scene with appended unit
            current_scene = CanonicalScene(
                scene_number=current_scene.scene_number,
                header=current_scene.header,
                title=current_scene.title,
                units=list(current_scene.units) + [unit],
            )
            current_episode.scenes[-1] = current_scene

    return episodes


def characters_from_episodes(episodes: List[CanonicalEpisode]) -> List[str]:
    """Deterministic, fully-sorted character name list (fixes NONDET-005)."""
    names: set[str] = set()
    for episode in episodes:
        for scene in episode.scenes:
            for unit in scene.units:
                if unit.is_dialogue and unit.speaker:
                    names.add(unit.speaker)
                names.update(unit.characters)
    return sorted(names)


__all__ = [
    "parse_json_contract",
    "SceneHeader",
    "Unit",
    "CanonicalScene",
    "CanonicalEpisode",
    "parse_scene_header",
    "parse_unit",
    "split_episodes",
    "characters_from_episodes",
]
