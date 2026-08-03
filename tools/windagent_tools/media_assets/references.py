"""
Reference builders (plan 02 §21.4) — identity and likeness safety.

Rules:
- a character reference builder never merges identity on display name — the
  reference master binds to a stable character ID + revision;
- generated variants trace back to their source reference and prompt
  (prompt_version + prompt_hash recorded);
- real-person likeness requires human approval + usage evidence
  (enforced in the provenance service).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from windagent_core.domain.video_production.ids import CharacterId, LocationId


@dataclass(frozen=True)
class CharacterReference:
    """Reference master bound to a stable character identity."""

    character_id: CharacterId
    character_name: str
    revision_id: str
    asset_id: str
    content_hash: str
    prompt_version: str = ""
    prompt_hash: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LocationReference:
    """Reference master bound to a stable location identity."""

    location_id: LocationId
    location_name: str
    revision_id: str
    asset_id: str
    content_hash: str
    prompt_version: str = ""
    prompt_hash: str = ""
    metadata: dict = field(default_factory=dict)


class IdentityReferenceBuilder:
    """Builds character references keyed by stable character_id + revision."""

    def __init__(self, *, seed: str = "windagent-identity-ref") -> None:
        self._seed = seed

    def build_character(
        self,
        *,
        character_id: CharacterId,
        character_name: str,
        revision_id: str,
        asset_id: str,
        content_hash: str,
        prompt_version: str = "",
        prompt_hash: str = "",
    ) -> CharacterReference:
        # Identity is bound via character_id — display name is metadata only
        # and never merges two records (fixes DEF-003-style name-collision).
        return CharacterReference(
            character_id=character_id,
            character_name=character_name,
            revision_id=revision_id,
            asset_id=asset_id,
            content_hash=content_hash,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
        )

    def trace_variant(
        self,
        reference: CharacterReference,
        *,
        variant_asset_id: str,
        variant_hash: str,
        prompt_version: str,
        prompt_hash: str,
    ) -> CharacterReference:
        """A generated variant traces back to the source reference + prompt."""
        return CharacterReference(
            character_id=reference.character_id,
            character_name=reference.character_name,
            revision_id=reference.revision_id,
            asset_id=variant_asset_id,
            content_hash=variant_hash,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            metadata={**reference.metadata, "source_asset_id": reference.asset_id},
        )


class LocationReferenceBuilder:
    """Builds location references keyed by stable location_id + revision."""

    def build_location(
        self,
        *,
        location_id: LocationId,
        location_name: str,
        revision_id: str,
        asset_id: str,
        content_hash: str,
        prompt_version: str = "",
        prompt_hash: str = "",
    ) -> LocationReference:
        return LocationReference(
            location_id=location_id,
            location_name=location_name,
            revision_id=revision_id,
            asset_id=asset_id,
            content_hash=content_hash,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
        )


__all__ = [
    "CharacterReference",
    "LocationReference",
    "IdentityReferenceBuilder",
    "LocationReferenceBuilder",
]
