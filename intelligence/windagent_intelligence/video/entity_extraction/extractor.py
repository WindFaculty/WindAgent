"""
EntityExtractor (Phase 6 slice 5) — character / location / prop extraction.

Extracts canonical CharacterBible[], LocationBible[] and PropBible[] from a
screenplay + a provider meta response. Identity is bound by stable canonical
IDs — duplicate display names with distinct identities get distinct IDs
(fixes DEF-003) and name lists are fully sorted (fixes NONDET-005).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.enums import CharacterRole
from windagent_core.domain.video_production.ids import (
    CharacterId,
    LocationId,
    PropId,
)
from windagent_core.domain.video_production.location import (
    LocationBible,
    PropBible,
)
from windagent_core.domain.video_production.screenplay import Screenplay

from windagent_intelligence.video.errors import ResponseParseError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import parse_json_contract


class EntityExtractor:
    """Deterministically builds bibles from a screenplay + meta JSON."""

    def __init__(self, *, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def extract(
        self,
        screenplay: Screenplay,
        meta_response: str,
        *,
        character_id_map: Optional[Dict[str, CharacterId]] = None,
        location_id_map: Optional[Dict[str, LocationId]] = None,
    ) -> dict:
        """Return {characters, locations, props, prompt_version, capability}.

        `character_id_map` / `location_id_map` bind bible identity to the
        SAME stable IDs the ScreenplayWriter assigned for matching names, so
        dialogue lines reference existing bible character IDs (fixes the
        package-validation identity binding; DEF-003). Names absent from the
        map get fresh deterministic IDs.
        """
        meta = parse_json_contract(meta_response)
        characters = self._characters(
            self._require_characters(meta),
            character_id_map or {},
        )
        locations = self._locations(
            meta.get("settings") or meta.get("locations") or [],
            screenplay=screenplay,
            location_id_map=location_id_map or {},
        )
        props = self._props(meta.get("props") or [])
        return {
            "characters": characters,
            "locations": locations,
            "props": props,
            "prompt_version": "1.0.0",
            "capability": "entity_extraction",
        }

    # ------------------------------------------------------------------
    def _characters(
        self,
        raw: List[Any],
        id_map: Dict[str, CharacterId],
    ) -> List[CharacterBible]:
        """Stable per-record identity; duplicate display names stay distinct."""
        bibles: List[CharacterBible] = []
        for seq, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            role_raw = str(item.get("role") or "").upper()
            role = CharacterRole.LEAD if role_raw == "主角" or role_raw == "LEAD" else (
                CharacterRole.SUPPORTING if role_raw == "配角" or role_raw == "SUPPORTING"
                else CharacterRole.SUPPORTING
            )
            traits = item.get("visual_traits") or {}
            if not isinstance(traits, dict):
                traits = {"description": str(traits)}
            if "description" not in traits and item.get("description"):
                traits = {"description": str(item["description"])}
            bibles.append(
                CharacterBible(
                    character_id=id_map.get(name) or CharacterId(
                        self.id_factory.character_id(name, seq)
                    ),
                    name=name,
                    role=role,
                    visual_traits=traits,
                    costume_descriptions=[
                        str(c) for c in (item.get("costume_descriptions") or []) if str(c).strip()
                    ],
                    metadata={"identity_seq": seq},
                )
            )
        # Deterministic full ordering by name then seq (NONDET-005)
        return sorted(bibles, key=lambda b: (b.name, str(b.character_id)))

    def _locations(
        self,
        raw: List[Any],
        *,
        screenplay: Screenplay,
        location_id_map: Optional[Dict[str, LocationId]] = None,
    ) -> List[LocationBible]:
        """Location bibles from meta settings + screenplay scene locations."""
        id_map = location_id_map or {}
        merged: Dict[str, dict] = {}
        for seq, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            merged.setdefault(name, {"name": name, "description": str(item.get("description") or ""), "seq": seq})
        # Fold in locations seen in the screenplay that meta omitted. Uses the
        # canonical scene_location metadata (never the synthetic fallback title
        # "Scene N"), so location-less scenes create no bogus LocationBible.
        for scene in screenplay.scenes:
            loc_name = str(scene.metadata.get("scene_location") or "").strip() or (
                scene.title if not scene.title.startswith("Scene ") else ""
            )
            if loc_name and loc_name not in merged:
                merged[loc_name] = {"name": loc_name, "description": "", "seq": len(merged)}
        bibles: List[LocationBible] = []
        for name, item in sorted(merged.items(), key=lambda kv: (kv[0], kv[1]["seq"])):
            bibles.append(
                LocationBible(
                    location_id=id_map.get(name) or LocationId(
                        self.id_factory.location_id(name, item["seq"])
                    ),
                    name=name,
                    visual_description=item["description"],
                    lighting_profile="",
                    atmosphere_tags=[],
                    metadata={"identity_seq": item["seq"]},
                )
            )
        return bibles

    def _props(self, raw: List[Any]) -> List[PropBible]:
        bibles: List[PropBible] = []
        for seq, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            bibles.append(
                PropBible(
                    prop_id=PropId(self.id_factory.prop_id(name, seq)),
                    name=name,
                    description=str(item.get("description") or ""),
                    metadata={"identity_seq": seq},
                )
            )
        return sorted(bibles, key=lambda p: (p.name, str(p.prop_id)))

    @staticmethod
    def _require_characters(meta: Dict[str, Any]) -> List[Any]:
        """Typed failure when characters are entirely absent (fixes BM-025)."""
        characters = meta.get("characters")
        if not isinstance(characters, list) or not characters:
            raise ResponseParseError(
                "Entity extraction meta is missing 'characters'.",
                details={"keys": sorted(meta.keys())},
            )
        return characters


__all__ = ["EntityExtractor"]
